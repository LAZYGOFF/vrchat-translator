import ctypes
import ctypes.wintypes as wt
import difflib
import os
import re
import threading
import time

import mss
import numpy as np

from textfilter import detect_latin, is_noise
from window_capture import capture_window, find_vrchat_hwnd

CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯豈-﫿]")
HANZI = re.compile(r"[㐀-鿿豈-﫿]")
KANA = re.compile(r"[぀-ヿ]")
HANGUL = re.compile(r"[가-힯]")
LATIN_LANGS = {"en", "es", "de", "fr"}
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
user32 = ctypes.windll.user32
DEBUG_KEEP = 40
BG_MAX_LUM = 135
FPS_COUNTER = re.compile(r"\b\d{1,3}\s*FPS\b", re.I)


def find_vrchat_rect():
    hwnd = user32.FindWindowW("UnityWndClass", "VRChat") or user32.FindWindowW(None, "VRChat")
    if not hwnd or user32.IsIconic(hwnd):
        return None
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    if rect.right < 100 or rect.bottom < 100:
        return None
    return {"left": pt.x, "top": pt.y, "width": rect.right, "height": rect.bottom}


def make_engine(threads=2):
    from rapidocr import RapidOCR
    return RapidOCR(params={
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })


def group_lines(lines):
    groups = []
    for text, x0, y0, x1, y1 in sorted(lines, key=lambda l: l[2]):
        h = y1 - y0
        for g in groups:
            gx0, gx1, gy1 = g["x0"], g["x1"], g["y1"]
            gap = y0 - gy1
            overlap = min(x1, gx1) - max(x0, gx0)
            if -0.5 * h <= gap <= 1.2 * h and overlap > 0.3 * min(x1 - x0, gx1 - gx0):
                g["texts"].append(text)
                g["x0"], g["x1"], g["y1"] = min(gx0, x0), max(gx1, x1), max(gy1, y1)
                break
        else:
            groups.append({"texts": [text], "x0": x0, "x1": x1, "y1": y1})
    return [_join(g["texts"]) for g in groups]


def _join(texts):
    out = texts[0]
    for t in texts[1:]:
        out += (" " if out[-1:].isascii() and t[:1].isascii() else "") + t
    return out


NAMEPLATE_JUNK = re.compile(
    r"^[a-z]{2,8}\s*/\s*[a-z]{2,8}$|instantiating|loading|downloading|"
    r"^(visitor|new user|user|known user|trusted user|friend|muted|blocked)$", re.I)


def looks_like_chatbox(img, x0, y0, x1, y1):
    return chatbox_check(img, x0, y0, x1, y1)[0]


def chatbox_check(img, x0, y0, x1, y1):
    h_img, w_img = img.shape[:2]
    pad = max(4, int((y1 - y0) * 0.35))
    patch = img[max(0, int(y0) - pad):min(h_img, int(y1) + pad),
                max(0, int(x0) - pad):min(w_img, int(x1) + pad)].astype(np.float32)
    if patch.size == 0:
        return False, "пустая область"
    b, g, r = patch[..., 0], patch[..., 1], patch[..., 2]
    lum = 0.114 * b + 0.587 * g + 0.299 * r
    text = lum > 160
    if text.mean() < 0.02 or text.mean() > 0.6:
        return False, f"доля светлого {text.mean():.2f} (нужно 0.02–0.6)"
    bg = patch[~text]
    bg_lum = np.median(lum[~text])
    sat = np.median((bg.max(axis=1) - bg.min(axis=1)) / (bg.max(axis=1) + 1))
    why = f"фон: яркость {bg_lum:.0f} (нужно <{BG_MAX_LUM}), цветность {sat:.2f} (нужно <0.45)"
    return bool(bg_lum < BG_MAX_LUM and sat < 0.45), why


def clean_message(msg):
    return re.sub(r"\s{2,}", " ", FPS_COUNTER.sub(" ", msg)).strip()


def wanted(msg, langs):
    inner = re.sub(r"^[(（\[【](.*)[)）\]】]$", r"\1", msg.strip())
    if CYRILLIC.search(msg) or (is_noise(msg) and is_noise(inner)):
        return False
    words = LATIN_WORD.findall(msg)
    latin = not CJK.search(msg) and len(words) >= 2 and sum(map(len, words)) >= 6
    cjk = len(CJK.findall(msg)) >= 2
    if langs is None:
        return cjk or latin
    zh = len(HANZI.findall(msg)) >= 2 and not KANA.search(msg)
    ja = bool(KANA.search(msg)) and cjk
    ko = len(HANGUL.findall(msg)) >= 2
    latin_langs = langs & LATIN_LANGS
    if latin and latin_langs:
        guess = detect_latin(msg)
        latin = guess is None or guess in latin_langs
    else:
        latin = False
    return ("zh" in langs and zh) or ("ja" in langs and ja) or ("ko" in langs and ko) or latin


def same_message(a, b):
    short, long_ = sorted((a, b), key=len)
    if short in long_ and len(short) >= 0.6 * len(long_):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.8


class ChatOCR:
    def __init__(self, on_text, on_status, get_interval, get_min_score, threads=2,
                 get_own_rect=lambda: None, get_langs=lambda: {"zh"}):
        self.threads = threads
        self.get_langs = get_langs
        self.only_chatboxes = True
        self._lock = threading.Lock()
        self.get_own_rect = get_own_rect
        self.on_text = on_text
        self.on_status = on_status
        self.get_interval = get_interval
        self.get_min_score = get_min_score
        self._seen = {}
        self._running = False
        self.debug_dir = None
        self._debug_last = -1e9
        self._report = []

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def mark_seen(self, text):
        norm = re.sub(r"\W", "", text).lower()
        with self._lock:
            self._seen[norm] = time.monotonic()

    def _is_new(self, text):
        now = time.monotonic()
        norm = re.sub(r"\W", "", text).lower()
        if len(norm) < 2:
            return False
        with self._lock:
            self._seen = {t: ts for t, ts in self._seen.items() if now - ts < 90}
            for t in self._seen:
                if same_message(norm, t):
                    self._seen[t] = now
                    return False
            self._seen[norm] = now
        return True

    def _run(self):
        self.on_status("Чат: загрузка OCR...")
        try:
            engine = make_engine(self.threads)
        except Exception as e:
            self.on_status(f"Чат: OCR не загрузился: {e}")
            self._running = False
            return

        last_state = None
        with mss.MSS() as sct:
            while self._running:
                t0 = time.monotonic()
                try:
                    img, state = self._grab(sct)
                    if state != last_state:
                        last_state = state
                        self.on_status(state)
                    if img is not None:
                        emitted = []
                        for msg in self._recognize(engine, img):
                            if self._is_new(msg):
                                self.on_text(msg)
                                emitted.append((msg, "ПЕРЕВЕДЕНО"))
                            else:
                                emitted.append((msg, "уже было (повтор того же чатбокса или своё сообщение)"))
                        if self.debug_dir:
                            self._save_debug(img, emitted)
                except Exception as e:
                    self.on_status(f"Чат: ошибка OCR: {e}")
                time.sleep(max(0.2, self.get_interval() - (time.monotonic() - t0)))

    def _grab(self, sct):
        hwnd = find_vrchat_hwnd()
        if hwnd is None:
            return None, "Чат: VRChat не найден или свёрнут — жду"
        img = capture_window(hwnd)
        if img is not None:
            return img, "Чат: читаю окно VRChat"
        region = find_vrchat_rect()
        if region is None:
            return None, "Чат: VRChat не найден или свёрнут — жду"
        img = np.ascontiguousarray(np.array(sct.grab(region))[:, :, :3])
        self._mask_own_window(img, region)
        return img, "Чат: читаю экран (окно VRChat не должно быть перекрыто)"

    def _mask_own_window(self, img, region):
        own = self.get_own_rect()
        if not own:
            return
        x0, y0 = max(own[0] - region["left"], 0), max(own[1] - region["top"], 0)
        x1, y1 = min(own[2] - region["left"], img.shape[1]), min(own[3] - region["top"], img.shape[0])
        if x0 < x1 and y0 < y1:
            img[y0:y1, x0:x1] = 0

    def _recognize(self, engine, img):
        self._report = []
        res = engine(img)
        if res.boxes is None or res.txts is None:
            return []
        min_score = self.get_min_score()
        lines = []
        for box, text, score in zip(res.boxes, res.txts, res.scores):
            text = text.strip()
            if score < min_score:
                self._report.append((text, f"отброшено: уверенность OCR {score:.2f} < {min_score}"))
                continue
            if NAMEPLATE_JUNK.search(text):
                self._report.append((text, "отброшено: служебная строка таблички ника"))
                continue
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            if self.only_chatboxes:
                ok, why = chatbox_check(img, x0, y0, x1, y1)
                if not ok:
                    self._report.append((text, f"отброшено: не похоже на чатбокс — {why}"))
                    continue
            lines.append((text, x0, y0, x1, y1))
        langs = self.get_langs()
        out = []
        for m in map(clean_message, group_lines(lines)):
            if wanted(m, langs):
                out.append(m)
            else:
                self._report.append((m, "отброшено: не нужный язык / ник / смех"))
        return out

    def _save_debug(self, img, emitted):
        interesting = [(t, v) for t, v in self._report if CJK.search(t) or len(LATIN_WORD.findall(t)) >= 2]
        now = time.monotonic()
        if not interesting or now - self._debug_last < 15:
            return
        self._debug_last = now
        os.makedirs(self.debug_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        from PIL import Image
        Image.fromarray(img[:, :, ::-1]).save(os.path.join(self.debug_dir, stamp + ".jpg"), quality=85)
        with open(os.path.join(self.debug_dir, stamp + ".txt"), "w", encoding="utf-8") as f:
            for t, v in self._report:
                f.write(f"{t}\n    {v}\n")
            for t, v in emitted:
                f.write(f"{t}\n    {v}\n")
        files = sorted(os.listdir(self.debug_dir))
        for old in files[:-2 * DEBUG_KEEP]:
            try:
                os.remove(os.path.join(self.debug_dir, old))
            except OSError:
                pass
