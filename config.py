import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "config.json")

DEFAULTS = {
    "whisper_model": "small",
    "device": "auto",
    "their_langs": "zh+en",
    "output_device": "",
    "vad_threshold_db": -42,
    "translator": "auto",
    "deepl_key": "",
    "mymemory_email": "",
    "gemini_key": "",
    "groq_key": "",
    "gemini_model": "",
    "groq_model": "",
    "llm_for_theirs": True,
    "translator_order": ["deepl", "gemini", "groq", "google", "mymemory", "offline"],
    "translator_off": [],
    "keys_for_mine_only": True,
    "deepl_month_limit": 495000,
    "offline_device": "auto",
    "target_lang": "ru",
    "my_lang": "ru",
    "out_lang": "en",
    "mic_device": "",
    "send_to_chatbox": True,
    "mic_auto": False,
    "mic_vad_threshold_db": -45,
    "mic_only_unmuted": True,
    "review_before_send": False,
    "tts_on": False,
    "tts_device": "Line 1 (Virtual Audio Cable)",
    "voice_passthrough": True,
    "mic_gain": 1.0,
    "tts_voices": {},
    "osc_port": 9000,
    "hotkey": "F8",
    "music_status": False,
    "music_interval": 1.6,
    "music_pause_s": 20,
    "music_prefix": "♪",
    "vrchat_chat_keys": ["H"],
    "ocr_interval": 2.5,
    "ocr_min_score": 0.6,
    "ocr_threads": 2,
    "ocr_only_chatboxes": True,
    "always_on_top": True,
    "hide_from_capture": False,
    "opacity": 1.0,
    "bg_opacity": 1.0,
    "theme_preset": "Тёмная",
    "theme": {},
    "font_size": 15,
    "show_original": True,
    "geometry": "860x600",
}


def path(name):
    return os.path.join(HERE, name)


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg["translator"] in ("google", "mymemory"):
        cfg["translator"] = "auto"
    cfg.pop("show_settings", None)
    for old in ("gcloud_key", "gcloud_month_limit"):
        cfg.pop(old, None)
    if cfg.get("groq_model") == "llama-3.3-70b-versatile":
        cfg["groq_model"] = ""
    if cfg.get("opacity") == 0.96 and "bg_opacity" not in cfg:
        cfg["opacity"] = 1.0
    return cfg


def fit_geometry(geometry, min_w, min_h):
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
