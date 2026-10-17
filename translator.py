import calendar
import json
import os
import re
import threading
import time
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from textfilter import detect_latin

GOOGLE_URL = "https://translate.google.com/m"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
TIMEOUT = (3, 5)
GOOGLE_PAUSE = 0.3
COOLDOWN = 600
GOOGLE_SLOW = 4.0

GOOGLE_LANG = {"zh": "zh-CN"}
MYMEMORY_LANG = {"zh": "zh-CN", "zh-CN": "zh-CN", "ja": "ja-JP", "ko": "ko-KR", "en": "en-GB",
                 "ru": "ru-RU", "es": "es-ES", "de": "de-DE", "fr": "fr-FR"}
DEEPL_TARGET = {"en": "EN-US", "zh": "ZH-HANS", "zh-CN": "ZH-HANS", "ja": "JA", "ko": "KO",
                "ru": "RU", "es": "ES", "de": "DE", "fr": "FR"}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_TIMEOUT = (3, 8)
GEMINI_PREFERRED = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
LANG_NAMES = {"ru": "Russian", "en": "English", "zh": "Simplified Chinese", "zh-CN": "Simplified Chinese",
              "ja": "Japanese", "ko": "Korean", "es": "Spanish", "de": "German", "fr": "French"}
LLM_PROMPT = ("You translate short chat messages in the social VR game VRChat. "
              "Translate the message from {src} to {dst}. Keep the tone, slang and emojis natural, "
              "as a native speaker would write in a game chat; keep it about as short as the original. "
              "Reply with the translation only: no quotes, no explanations, no transliteration.")

NAMES = {"deepl": "DeepL", "gemini": "Gemini", "groq": "Groq",
         "google": "Google", "mymemory": "MyMemory", "offline": "офлайн"}
ORDER = ["deepl", "gemini", "groq", "google", "mymemory", "offline"]
ABOUT = {
    "deepl": "лучшее качество · лимит в символах",
    "gemini": "ИИ, понимает сленг и контекст",
    "groq": "ИИ, очень быстрый",
    "google": "без ключа · иногда временно ограничивает",
    "mymemory": "без ключа · дневной лимит",
    "offline": "на вашей видеокарте · работает всегда",
}
KEYED = {"deepl"}
LLM = {"gemini", "groq"}


class RateLimited(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class Overloaded(Exception):
    pass


class BadKey(Exception):
    pass


def guess_lang(text, unsure="en"):
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    if re.search(r"[가-힯]", text):
        return "ko"
    if re.search(r"[㐀-鿿]", text):
        return "zh-CN"
    if re.search(r"[Ѐ-ӿ]", text):
        return "ru"
    return detect_latin(text) or unsure


class Usage:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self._roll()

    def _roll(self):
        today, month = date.today().isoformat(), date.today().strftime("%Y-%m")
        if self.data.get("day") != today:
            self.data["day"], self.data["d"] = today, {}
        if self.data.get("month") != month:
            self.data["month"], self.data["m"] = month, {}

    def add(self, name, chars):
        with self._lock:
            self._roll()
            for period in ("d", "m"):
                self.data[period][name] = self.data[period].get(name, 0) + chars
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f)
            except OSError:
                pass

    def today(self, name):
        self._roll()
        return self.data["d"].get(name, 0)

    def month(self, name):
        self._roll()
        return self.data["m"].get(name, 0)


class Translator:
    def __init__(self, mode="auto", target="ru", on_notice=print, offline_device="auto", keys=None,
                 limits=None, keys_for_mine_only=True, usage_path="usage.json", models=None,
                 llm_for_theirs=True, order=None, off=()):
        from offline import OfflineTranslator
        self.mode = mode
        self.set_order(order, off)
        self.target = target
        self.on_notice = on_notice
        self.keys = {"deepl": "", "gemini": "", "groq": "", "mymemory_email": "",
                     **(keys or {})}
        self.limits = {"deepl": 495_000, **(limits or {})}
        self.keys_for_mine_only = keys_for_mine_only
        self.llm_for_theirs = llm_for_theirs
        self.models = {"gemini": "", "groq": "", **(models or {})}
        self._gemini_auto = not self.models["gemini"]
        self._groq_auto = not self.models["groq"]
        self.offline = OfflineTranslator(offline_device, log=on_notice)
        self.usage = Usage(usage_path)
        self.last_backend = ""
        self._cache = {}
        self._rest_until = {}
        self._disabled = set()
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36")
        self._google_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._last_google = 0.0
        self.deepl_quota = None
        self._deepl_quota_time = 0.0
        self.refresh_deepl_quota()

    def set_order(self, order=None, off=()):
        order = [n for n in (order or ORDER) if n in ORDER]
        self.order = list(dict.fromkeys(order)) + [n for n in ORDER if n not in order]
        self.off = set(off) & set(ORDER) - {"offline"}

    def set_keys(self, **keys):
        self.keys.update(keys)
        self._disabled -= {k for k in keys if keys[k]}
        for k in keys:
            self._rest_until.pop(k, None)
        if "deepl" in keys:
            self.deepl_quota = None
            self.refresh_deepl_quota()
        if "gemini" in keys and self._gemini_auto:
            self.models["gemini"] = ""
        if "groq" in keys and self._groq_auto:
            self.models["groq"] = ""

    def refresh_deepl_quota(self):
        if self.keys["deepl"]:
            self._deepl_quota_time = time.monotonic()
            threading.Thread(target=self._fetch_deepl_quota, daemon=True).start()

    def _fetch_deepl_quota(self):
        try:
            r = self._session.get(f"https://{self._deepl_host()}/v2/usage", timeout=TIMEOUT,
                                  headers={"Authorization": f"DeepL-Auth-Key {self.keys['deepl']}"})
            if r.status_code in (401, 403):
                self._disabled.add("deepl")
                self.on_notice("Ключ DeepL не подходит — проверьте его в настройках.")
                return
            r.raise_for_status()
            data = r.json()
            self.deepl_quota = [int(data["character_count"]), int(data["character_limit"])]
        except Exception as e:
            self.on_notice(f"DeepL: не удалось узнать остаток ({e}).")

    def _deepl_host(self):
        return "api-free.deepl.com" if self.keys["deepl"].endswith(":fx") else "api.deepl.com"

    def _mymemory_limit(self):
        return 49_000 if self.keys["mymemory_email"] else 4_900

    def available(self, name, chars, mine):
        if self.mode == "offline" and name != "offline":
            return False, "выбран только офлайн"
        if name in self.off:
            return False, "выключен"
        if name in KEYED:
            if not self.keys[name]:
                return False, "нет ключа"
            if name in self._disabled:
                return False, "ключ не подошёл"
            if self.keys_for_mine_only and not mine:
                return False, "только для моих сообщений"
            if name == "deepl" and self.deepl_quota:
                used, limit = self.deepl_quota
                if used + chars > limit - 1000:
                    return False, "лимит тарифа исчерпан"
            elif self.usage.month(name) + chars > self.limits[name]:
                return False, "месячный лимит"
        if name in LLM:
            if not self.keys[name]:
                return False, "нет ключа"
            if name in self._disabled:
                return False, "ключ не подошёл"
            if not mine and not self.llm_for_theirs:
                return False, "только для моих сообщений"
        if name == "mymemory" and self.usage.today(name) + chars > self._mymemory_limit():
            return False, "дневной лимит"
        if time.monotonic() < self._rest_until.get(name, 0):
            return False, "отдыхает после отказа"
        return True, ""

    def translate(self, text, source="auto", target=None, mine=False):
        target = target or self.target
        key = (text, source, target)
        if key in self._cache:
            self.last_backend = "кэш"
            return self._cache[key]
        src = GOOGLE_LANG.get(source, source)
        chars = len(text)
        errors = []
        for name in self.order:
            ok, why = self.available(name, chars, mine)
            if not ok:
                continue
            if name == "offline" and not self.offline.ready:
                self.offline.load_in_background()
                errors.append("офлайн: модель ещё загружается")
                continue
            started = time.monotonic()
            try:
                result = self._call(name, text, src, target)
                if name == "google" and time.monotonic() - started > GOOGLE_SLOW:
                    self._rest(name, COOLDOWN, "отвечает медленно")
            except Overloaded:
                self._rest_until[name] = time.monotonic() + 60
                errors.append(f"{NAMES[name]}: перегружен")
                continue
            except RateLimited:
                self._rest(name, COOLDOWN, "временно ограничил запросы")
                errors.append(f"{NAMES[name]}: лимит запросов")
                continue
            except QuotaExceeded:
                self._rest(name, self._until_period_end(name), "исчерпал лимит")
                errors.append(f"{NAMES[name]}: лимит исчерпан")
                continue
            except BadKey:
                self._disabled.add(name)
                self.on_notice(f"Ключ {NAMES[name]} не подходит — проверьте его в настройках.")
                errors.append(f"{NAMES[name]}: ключ не подходит")
                continue
            except Exception as e:
                errors.append(f"{NAMES[name]}: {e}")
                continue
            result = (result or "").strip().lstrip(",.;:，。；： ")
            if result:
                if name != "offline":
                    self.usage.add(name, chars)
                if name == "deepl":
                    if self.deepl_quota:
                        self.deepl_quota[0] += chars
                    if time.monotonic() - self._deepl_quota_time > 600:
                        self.refresh_deepl_quota()
                if len(self._cache) > 2000:
                    self._cache.clear()
                self._cache[key] = result
                self.last_backend = NAMES[name]
                return result
        raise RuntimeError("перевод недоступен: " + "; ".join(errors))

    def _rest(self, name, seconds, why):
        self._rest_until[name] = time.monotonic() + seconds
        minutes = int(seconds // 60)
        span = f"{minutes} мин" if minutes < 120 else "до конца периода"
        self.on_notice(f"{NAMES[name]} {why} — {span} перевожу через другие сервисы.")

    @staticmethod
    def _until_period_end(name):
        now = datetime.now()
        if name in ("mymemory", "gemini", "groq"):
            end = now.replace(hour=23, minute=59, second=59)
        else:
            last = calendar.monthrange(now.year, now.month)[1]
            end = now.replace(day=last, hour=23, minute=59, second=59)
        return max(60, (end - now).total_seconds())

    def status(self):
        rows = []
        for name in self.order:
            ok, why = self.available(name, 1, mine=True)
            if why == "выключен":
                rows.append((NAMES[name], why, False))
                continue
            if name == "deepl" and self.deepl_quota:
                used = f"{self.deepl_quota[0]:,} / {self.deepl_quota[1]:,} по тарифу".replace(",", " ")
                rows.append((NAMES[name], used if ok or why == "только для моих сообщений" else why,
                             ok or why == "только для моих сообщений"))
            elif name in KEYED:
                used = f"{self.usage.month(name):,} / {self.limits[name]:,} за месяц".replace(",", " ")
                rows.append((NAMES[name], used if self.keys[name] else "нет ключа",
                             ok or why == "только для моих сообщений"))
            elif name == "mymemory":
                rows.append((NAMES[name], f"{self.usage.today(name):,} / {self._mymemory_limit():,} сегодня"
                             .replace(",", " "), ok))
            elif name in LLM:
                if not self.keys[name]:
                    rows.append((NAMES[name], "нет ключа", False))
                else:
                    model = self.models.get(name) or "модель выберется при первом переводе"
                    state = f"{self.usage.today(name):,} симв. сегодня · {model}".replace(",", " ")
                    rows.append((NAMES[name], state if ok else why, ok))
            elif name == "google":
                rows.append((NAMES[name], "работает" if ok else why, ok))
            else:
                rows.append((NAMES[name], "готов" if self.offline.ready else "загружается", True))
        return rows

    def states(self):
        return {name: (state, ok) for name, (_, state, ok) in zip(self.order, self.status())}

    def _call(self, name, text, src, target):
        if name == "offline":
            return self.offline.translate(text, guess_lang(text) if src == "auto" else src, target)
        return {"deepl": self._deepl, "gemini": self._gemini, "groq": self._groq,
                "google": self._google, "mymemory": self._mymemory}[name](text, src, target)

    @staticmethod
    def _llm_prompt(src, target):
        src_name = "the original language" if src == "auto" else LANG_NAMES.get(src, src)
        return LLM_PROMPT.format(src=src_name, dst=LANG_NAMES.get(target, target))

    @staticmethod
    def _clean_llm(out):
        out = out.strip()
        out = re.sub(r"^(translation|перевод)\s*:\s*", "", out, flags=re.I)
        if len(out) > 1 and out[0] + out[-1] in ('""', "''", "«»", "“”"):
            out = out[1:-1].strip()
        return out

    def warm_up(self):
        for name in ("gemini", "groq"):
            if self.keys[name] and self.mode != "offline":
                threading.Thread(target=self._warm, args=(name,), daemon=True).start()

    def _warm(self, name):
        try:
            self._call(name, "hi", "en", "ru")
        except Exception:
            pass

    def _gemini_model(self):
        if self.models["gemini"]:
            return self.models["gemini"]
        with self._model_lock:
            if not self.models["gemini"]:
                self._pick_gemini_model()
        return self.models["gemini"]

    def _pick_gemini_model(self):
        r = self._session.get(f"{GEMINI_URL}/models", params={"pageSize": 200}, timeout=TIMEOUT,
                              headers=self._gemini_headers())
        self._gemini_check(r)
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        model = next((n for n in GEMINI_PREFERRED if n in names), None)
        if model is None:
            version = lambda n: float(re.search(r"\d+(?:\.\d+)?", n).group())
            lite = [n for n in names if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash-lite", n)]
            flash = [n for n in names if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash", n)]
            if not (lite or flash):
                raise RuntimeError("нет подходящей модели Gemini")
            model = max(lite or flash, key=version)
        self.models["gemini"] = model
        self.on_notice(f"Gemini: перевожу моделью {model}.")
        return model

    def _gemini_headers(self):
        return {"x-goog-api-key": self.keys["gemini"]}

    def _gemini_check(self, r):
        if r.status_code == 503:
            raise Overloaded()
        if r.status_code == 429:
            raise QuotaExceeded() if "PerDay" in r.text else RateLimited()
        if r.status_code in (400, 401, 403):
            low = r.text.lower()
            if "location is not supported" in low:
                self.on_notice("Gemini недоступен в вашей стране — пропускаю его.")
                raise BadKey()
            if "api key" in low or "api_key" in low or r.status_code in (401, 403):
                raise BadKey()
        r.raise_for_status()

    def _gemini(self, text, src, target):
        model = self._gemini_model()
        config = {"temperature": 0.3, "maxOutputTokens": 1024}
        if re.fullmatch(r"gemini-2\.5-flash", model):
            config["thinkingConfig"] = {"thinkingBudget": 0}
        elif re.fullmatch(r"gemini-[3-9][\d.]*-flash", model):
            config["thinkingConfig"] = {"thinkingLevel": "low"}
        body = {"systemInstruction": {"parts": [{"text": self._llm_prompt(src, target)}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "generationConfig": config}
        r = self._session.post(f"{GEMINI_URL}/models/{model}:generateContent",
                               headers=self._gemini_headers(), json=body, timeout=LLM_TIMEOUT)
        if r.status_code == 404:
            self.models["gemini"], self._gemini_auto = "", True
        self._gemini_check(r)
        parts = r.json()["candidates"][0]["content"]["parts"]
        return self._clean_llm("".join(p.get("text", "") for p in parts if not p.get("thought")))

    def _groq_model(self):
        if self.models["groq"]:
            return self.models["groq"]
        with self._model_lock:
            if not self.models["groq"]:
                self._pick_groq_model()
        return self.models["groq"]

    def _pick_groq_model(self):
        r = self._session.get(GROQ_URL.replace("/chat/completions", "/models"), timeout=TIMEOUT,
                              headers={"Authorization": f"Bearer {self.keys['groq']}"})
        if r.status_code == 401:
            raise BadKey()
        r.raise_for_status()
        ids = {m["id"] for m in r.json().get("data", []) if m.get("active", True)}
        qwen = sorted((i for i in ids if i.startswith("qwen/")), reverse=True)
        model = next((m for m in qwen + ["openai/gpt-oss-120b", "openai/gpt-oss-20b"] if m in ids), None)
        if model is None:
            raise RuntimeError("нет подходящей модели Groq")
        self.models["groq"] = model
        self.on_notice(f"Groq: перевожу моделью {model}.")
        return model

    def _groq(self, text, src, target, retry=True):
        model = self._groq_model()
        body = {"model": model, "temperature": 0.3, "max_tokens": 800,
                "messages": [{"role": "system", "content": self._llm_prompt(src, target)},
                             {"role": "user", "content": text}]}
        if model.startswith("qwen/"):
            body["reasoning_effort"] = "none"
        elif model.startswith("openai/gpt-oss"):
            body.update(reasoning_effort="low", include_reasoning=False)
        r = self._session.post(GROQ_URL, timeout=LLM_TIMEOUT, json=body,
                               headers={"Authorization": f"Bearer {self.keys['groq']}"})
        if r.status_code == 404 and "model" in r.text:
            self.models["groq"], self._groq_auto = "", True
            if retry:
                return self._groq(text, src, target, retry=False)
        if r.status_code == 401:
            raise BadKey()
        if r.status_code == 403:
            self.on_notice("Groq отказал в доступе (возможно, недоступен в вашей стране) — пропускаю его.")
            raise BadKey()
        if r.status_code == 503:
            raise Overloaded()
        if r.status_code == 429:
            low = r.text.lower()
            raise QuotaExceeded() if ("per day" in low or "(rpd)" in low or "(tpd)" in low) else RateLimited()
        r.raise_for_status()
        return self._clean_llm(r.json()["choices"][0]["message"]["content"])

    def _deepl(self, text, src, target):
        key = self.keys["deepl"]
        host = self._deepl_host()
        data = {"text": text, "target_lang": DEEPL_TARGET.get(target, target.upper())}
        if src != "auto":
            data["source_lang"] = src.split("-")[0].upper()
        r = self._session.post(f"https://{host}/v2/translate", data=data, timeout=TIMEOUT,
                               headers={"Authorization": f"DeepL-Auth-Key {key}"})
        if r.status_code == 456:
            raise QuotaExceeded()
        if r.status_code in (401, 403):
            raise BadKey()
        if r.status_code == 429:
            raise RateLimited()
        r.raise_for_status()
        return r.json()["translations"][0]["text"]

    def _google(self, text, src, target):
        with self._google_lock:
            wait = self._last_google + GOOGLE_PAUSE - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                r = self._session.get(GOOGLE_URL, params={"sl": src, "tl": target, "q": text},
                                      timeout=TIMEOUT, allow_redirects=False)
            finally:
                self._last_google = time.monotonic()
        if r.status_code == 429 or "/sorry" in r.headers.get("location", ""):
            raise RateLimited()
        r.raise_for_status()
        el = BeautifulSoup(r.text, "html.parser").find("div", class_="result-container")
        if el is None:
            raise RuntimeError("непонятный ответ Google")
        return el.get_text().strip()

    def _mymemory(self, text, src, target):
        if src == "auto":
            src = guess_lang(text)
        params = {"q": text, "langpair": f"{MYMEMORY_LANG.get(src, src)}|{MYMEMORY_LANG.get(target, target)}"}
        if self.keys["mymemory_email"]:
            params["de"] = self.keys["mymemory_email"]
        r = self._session.get(MYMEMORY_URL, params=params, timeout=TIMEOUT)
        if r.status_code == 429:
            raise QuotaExceeded()
        r.raise_for_status()
        data = r.json()
        out = (data.get("responseData") or {}).get("translatedText", "").strip()
        if out.upper().startswith("MYMEMORY WARNING") or int(data.get("responseStatus", 200)) == 429:
            raise QuotaExceeded()
        if int(data.get("responseStatus", 200)) != 200:
            raise RuntimeError(str(data.get("responseDetails", "ошибка MyMemory"))[:80])
        return out
