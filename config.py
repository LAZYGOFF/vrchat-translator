import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "config.json")

DEFAULTS = {
    # Распознавание речи
    # small: ~1.2 с на фразу на GTX 1660 Super; large-v3-turbo точнее, но ~3.8 с и больше видеопамяти
    "whisper_model": "small",
    "device": "auto",                   # auto / cuda / cpu
    "their_langs": "zh+en",             # языки собеседников: zh / en / zh+en / auto (голос и чат)
    "output_device": "",                # имя loopback-устройства, "" = вывод по умолчанию
    "vad_threshold_db": -42,            # громкость, с которой начинается фраза
    # Перевод: только бесплатные сервисы по очереди (DeepL -> Gemini -> Groq -> Google -> MyMemory -> офлайн)
    "translator": "auto",               # auto — все по очереди, offline — только офлайн
    "deepl_key": "",                    # DeepL API Free: 500 000 символов/мес
    "mymemory_email": "",               # с почтой лимит MyMemory 50 000 символов/день вместо 5 000
    "gemini_key": "",                   # бесплатно без карты: aistudio.google.com/apikey
    "groq_key": "",                     # бесплатно без карты: console.groq.com/keys
    "gemini_model": "",                 # "" — свежая бесплатная Flash-модель (выбирается сама)
    "groq_model": "",                   # "" — лучшая из доступных (сейчас Qwen, сильна в китайском)
    "llm_for_theirs": True,             # Gemini/Groq и для чужой речи (у них лимит в запросах)
    # свой порядок сервисов (первый — главный, следующие — если он недоступен) и выключенные
    "translator_order": ["deepl", "gemini", "groq", "google", "mymemory", "offline"],
    "translator_off": [],
    "keys_for_mine_only": True,         # ключи тратить только на мои сообщения
    "deepl_month_limit": 495000,
    "offline_device": "auto",           # офлайн-перевод: auto / cuda / cpu (cpu — если VRChat тормозит)
    "target_lang": "ru",                # на какой язык переводить собеседников
    # Мой микрофон и текст -> чатбокс VRChat
    "my_lang": "ru",                    # на каком языке я говорю в микрофон
    "out_lang": "en",                   # на какой язык переводить меня
    "mic_device": "",                   # "" = микрофон по умолчанию
    "send_to_chatbox": True,
    "mic_auto": False,                  # True — микрофон без F8: сам ловит фразы и отправляет
    "mic_vad_threshold_db": -45,        # громкость, с которой начинается фраза в микрофоне
    "mic_only_unmuted": True,           # авто-перевод речи только когда микрофон в VRChat включён
    "review_before_send": False,        # распознанную фразу сначала в строку ввода, отправка по Enter
    "tts_on": False,                    # озвучивать мой перевод
    "tts_device": "Line 1 (Virtual Audio Cable)",  # куда озвучивать (микрофон, который слушает VRChat)
    "voice_passthrough": True,          # мой микрофон тоже в tts_device: VRChat слышит и меня, и озвучку
    "mic_gain": 1.0,                    # громкость моего голоса в tts_device
    "tts_voices": {},                   # свои голоса Piper, например {"en": "en/en_US/ryan/medium/en_US-ryan-medium"}
    "osc_port": 9000,
    "hotkey": "F8",                     # F1..F12, PAUSE, SCROLLLOCK, INSERT, HOME, END
    # Музыка в чатбоксе: «♪ Исполнитель — Трек»
    "music_status": False,
    "music_interval": 1.6,              # раз в сколько секунд обновлять (меньше 1.6 VRChat режет)
    "music_pause_s": 20,                # на сколько секунд прятать после моего сообщения
    "music_prefix": "♪",
    "vrchat_chat_keys": ["H"],          # клавиша, которой вы открываете чат в VRChat (пауза музыки)
    # Чатбоксы на экране
    "ocr_interval": 2.5,                # раз в сколько секунд читать экран
    "ocr_min_score": 0.6,
    "ocr_threads": 2,                   # больше — быстрее, но меньше CPU остаётся VRChat
    "ocr_only_chatboxes": True,         # только тёмные плашки чатбоксов; False — любой текст
    # Окно
    "always_on_top": True,
    "hide_from_capture": False,         # True — окно не видно на скриншотах, в OBS и стримах
    "opacity": 1.0,                     # прозрачность всего окна (вместе с текстом)
    "bg_opacity": 1.0,                  # непрозрачность только фона: текст и кнопки остаются чёткими
    "theme_preset": "Тёмная",           # готовая тема: Тёмная, Полночь, Графит, Неон, Сакура, Светлая
    "theme": {},                        # свои цвета поверх темы, например {"bg": "#101010", "me": "#00ff88"}
    "font_size": 15,
    "show_original": True,
    "geometry": "860x600",
}


def path(name):
    """Файл рядом с программой (usage.json и т.п.)."""
    return os.path.join(HERE, name)


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg["translator"] in ("google", "mymemory"):  # старые настройки: теперь все сервисы по очереди
        cfg["translator"] = "auto"
    cfg.pop("show_settings", None)
    for old in ("gcloud_key", "gcloud_month_limit"):  # Google Cloud платный — из программы убран
        cfg.pop(old, None)
    if cfg.get("groq_model") == "llama-3.3-70b-versatile":  # эту модель Groq убрал
        cfg["groq_model"] = ""
    if cfg.get("opacity") == 0.96 and "bg_opacity" not in cfg:  # старое умолчание: окно чуть просвечивало целиком
        cfg["opacity"] = 1.0
    return cfg


def fit_geometry(geometry, min_w, min_h):
    """Сохранённый размер окна, но не меньше нужного для нового интерфейса."""
    m = re.match(r"(\d+)x(\d+)(.*)", geometry or "")
    if not m:
        return f"{min_w}x{min_h}"
    w, h, rest = int(m.group(1)), int(m.group(2)), m.group(3)
    return f"{max(w, min_w)}x{max(h, min_h)}{rest}"


def save(cfg):
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
