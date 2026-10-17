import ctypes
import itertools
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winsound

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import customtkinter as ctk

import netcache

netcache.install()
netcache.prewarm()

import config
import osc
import theme
import ui
from backdrop import Backdrop
from textfilter import is_noise, not_worth_showing
from translator import Translator, guess_lang, NAMES, ORDER

MODELS = ["small", "medium", "large-v3-turbo"]
THEIR_LANGS = {"zh": "Китайский", "en": "Английский", "ja": "Японский", "ko": "Корейский",
               "es": "Испанский", "de": "Немецкий", "fr": "Французский"}
MY_LANGS = {"Русский": "ru", "Английский": "en", "Китайский": "zh"}
OUT_LANGS = {"Английский": "en", "Китайский": "zh-CN", "Японский": "ja", "Корейский": "ko",
             "Испанский": "es", "Немецкий": "de", "Французский": "fr", "Русский": "ru"}
DEFAULT_DEVICE = "По умолчанию"
SR = 16000


def parse_langs(code):
    return None if code == "auto" else code.split("+")


def label_of(mapping, value):
    return {v: k for k, v in mapping.items()}.get(value, next(iter(mapping)))


def beep(freq):
    threading.Thread(target=winsound.Beep, args=(freq, 90), daemon=True).start()


class App:
    def __init__(self):
        self.cfg = config.load()
        self.ui_q = queue.Queue()
        self.asr_q = queue.PriorityQueue()
        self._seq = itertools.count()
        self.tr_q = queue.Queue()
        self.translator = Translator(
            self.cfg["translator"], self.cfg["target_lang"], on_notice=lambda m: self._status(m),
            offline_device=self.cfg["offline_device"],
            keys={"deepl": self.cfg["deepl_key"],
                  "gemini": self.cfg["gemini_key"], "groq": self.cfg["groq_key"],
                  "mymemory_email": self.cfg["mymemory_email"]},
            limits={"deepl": self.cfg["deepl_month_limit"]},
            keys_for_mine_only=self.cfg["keys_for_mine_only"],
            models={"gemini": self.cfg["gemini_model"], "groq": self.cfg["groq_model"]},
            llm_for_theirs=self.cfg["llm_for_theirs"],
            order=self.cfg["translator_order"], off=self.cfg["translator_off"],
            usage_path=config.path("usage.json"))
        self.settings_win = None
        self._mic_asr_s = 0.0
        self.recognizer, self._rec_key = None, None
        self._rec_lock = threading.Lock()
        self._voice_lock = threading.Lock()
        self.capture, self.ocr, self.recorder = None, None, None
        self.mic_listener = None
        self.speaker = None
        self.mixer = None
        self._mixer_lock = threading.Lock()
        self.voice_on = self.chat_on = self.mic_on = False
        self.music_on = self.cfg["music_status"]
        self._music_pause_until = 0.0
        self._music_shown = False
        self.vrc_typing = None
        self.level_db = -90.0
        self.effective_thr = float(self.cfg["vad_threshold_db"])
        self._own_rect = None

        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("VRChat переводчик")
        self.root.geometry(config.fit_geometry(self.cfg["geometry"], 860, 600))
        self.root.minsize(640, 420)
        ui.set_icon(self.root)
        ui.set_palette(self.cfg)
        ui.build_main(self)
        self.backdrop = Backdrop(self.root, on_wheel=lambda e: self.text.yview_scroll(int(-e.delta / 120), "units"))
        self.root.bind("<Configure>", self.backdrop.sync, add="+")
        self._setup_clipboard()
        self._apply_window_opts()

        threading.Thread(target=self._asr_worker, daemon=True).start()
        threading.Thread(target=self._tr_worker, daemon=True).start()
        threading.Thread(target=self._warm_up_translator, daemon=True).start()
        threading.Thread(target=self._music_worker, daemon=True).start()
        threading.Thread(target=lambda: (self._restart_mixer(), self._preload_voice()), daemon=True).start()
        self.vrc_state = osc.VRChatState(on_change=lambda muted: self.ui_q.put(("vrc_mute", muted)))
        self.vrc_state.start()
        if self.cfg["mic_auto"]:
            self.root.after(1500, lambda: self.mic_listener is None and self._toggle_mic_listener())
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.after(50, self._poll)
        self.root.after(300, self._exclude_from_capture)

        from hotkey import GlobalHotkey
        key = self.cfg["hotkey"]
        if GlobalHotkey(key, lambda: self.ui_q.put(("mic_toggle",))).start():
            self._status(f"Готово. {key} (даже в игре) — начать/закончить фразу в микрофон.")
        else:
            self._status(f"Готово. Горячая клавиша {key} недоступна — пользуйтесь кнопкой «Микрофон».")

        from keywatch import VRChatTypingWatcher
        try:
            watcher = VRChatTypingWatcher(self.cfg["vrchat_chat_keys"], self._vrc_chat_opened,
                                          self._vrc_chat_sent, self._vrc_chat_cancelled)
            if watcher.start():
                self.vrc_typing = watcher
        except ValueError as e:
            self._status(f"vrchat_chat_keys в config.json: {e}")

    def _setup_clipboard(self):
        self.text.bind("<Button-1>", lambda e: self.text.focus_set(), add="+")
        self.root.bind_all("<Control-KeyPress>", self._ctrl_key)

        menu = dict(tearoff=0, bg=ui.CARD2, fg=ui.FG, activebackground=ui.HOVER, activeforeground=ui.FG, bd=0,
                    font=(ui.FONT, 11))
        self.text_menu = tk.Menu(self.root, **menu)
        self.text_menu.add_command(label="Копировать", command=lambda: self.text.event_generate("<<Copy>>"))
        self.text_menu.add_command(label="Копировать эту строку", command=self._copy_clicked_line)
        self.text_menu.add_command(label="Копировать всё", command=lambda: self._to_clipboard(
            self.text.get("1.0", "end-1c")))
        self.text.bind("<Button-3>", self._text_context)

        self.entry_menu = tk.Menu(self.root, **menu)
        for label, ev in (("Вырезать", "<<Cut>>"), ("Копировать", "<<Copy>>"), ("Вставить", "<<Paste>>")):
            self.entry_menu.add_command(label=label, command=lambda ev=ev: self.entry._entry.event_generate(ev))
        self.entry_menu.add_command(label="Выделить всё", command=lambda: self._select_all(self.entry._entry))
        self.entry.bind("<Button-3>", lambda e: (self.entry.focus_set(),
                                                 self.entry_menu.tk_popup(e.x_root, e.y_root)))

    def _ctrl_key(self, e):
        if e.keycode == 65:
            self._select_all(e.widget)
            return "break"
        if e.keysym.lower() in ("c", "v", "x"):
            return None
        event = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}.get(e.keycode)
        if event:
            e.widget.event_generate(event)
            return "break"
        return None

    def _select_all(self, w):
        if isinstance(w, tk.Entry):
            w.select_range(0, "end")
            w.icursor("end")
        elif isinstance(w, tk.Text):
            w.tag_add("sel", "1.0", "end-1c")

    def _text_context(self, e):
        self.text.focus_set()
        self._clicked_index = self.text.index(f"@{e.x},{e.y}")
        self.text_menu.tk_popup(e.x_root, e.y_root)

    def _copy_clicked_line(self):
        i = self._clicked_index
        self._to_clipboard(self.text.get(f"{i} linestart", f"{i} lineend").strip())

    def _to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _apply_window_opts(self):
        cfg, root = self.cfg, self.root
        root.attributes("-topmost", cfg["always_on_top"], "-alpha", cfg["opacity"])
        if ui.see_through(self):
            root.attributes("-transparentcolor", theme.key_color(ui.BG))
            self.backdrop.apply(ui.BG, cfg["bg_opacity"] * cfg["opacity"], cfg["always_on_top"],
                                cfg["hide_from_capture"])
        else:
            root.attributes("-transparentcolor", "")
            self.backdrop.disable()

    def _set_bg_opacity(self, value):
        was = ui.see_through(self)
        self._set("bg_opacity", round(min(max(value, 0.0), 1.0), 2))
        if ui.see_through(self) != was:
            ui.restyle_main(self)
        self._apply_window_opts()

    def _set_theme_preset(self, name):
        self._set("theme_preset", name)
        self._set("theme", {})
        self._apply_theme()

    def _set_color(self, key, color):
        self._set("theme", {**self.cfg.get("theme", {}), key: color})
        self._apply_theme()

    def _apply_theme(self):
        ui.set_palette(self.cfg)
        ui.restyle_main(self)
        ui.style_titlebar(self.root)
        self._apply_window_opts()
        win = self.settings_win
        if win is not None and win.winfo_exists():
            tab, geometry = win.tabs.get(), win.geometry()
            win.withdraw()
            win.after(1500, win.destroy)
            self.settings_win = ui.SettingsWindow(self, tab=tab, geometry=geometry)

    def _exclude_from_capture(self):
        if not self.cfg["hide_from_capture"]:
            return
        try:
            hwnd = int(self.root.wm_frame(), 16)
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
        except Exception:
            pass

    def open_settings(self, tab=None):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.focus_force()
            return
        self.settings_win = ui.SettingsWindow(self, tab=tab)

    def _clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        ui.show_hint(self)

    def _update_buttons(self):
        ui.update_buttons(self)

    def _set(self, key, value):
        self.cfg[key] = value

    def _set_restart(self, key, value):
        self._set(key, value)
        if self.voice_on:
            self.toggle_voice()
            self.toggle_voice()

    def _set_translator_mode(self, mode):
        self._set("translator", mode)
        self.translator.mode = mode

    def _set_key(self, key, value):
        if self.cfg.get(key) == value:
            return
        self._set(key, value)
        config.save(self.cfg)
        name = {"deepl_key": "deepl", "gemini_key": "gemini", "groq_key": "groq",
                "mymemory_email": "mymemory_email"}[key]
        self.translator.set_keys(**{name: value})
        if value and key != "mymemory_email":
            self._status(f"Ключ {NAMES[name]} сохранён — будет использоваться для перевода.")

    def _set_keys_mine_only(self, on):
        self._set("keys_for_mine_only", on)
        self.translator.keys_for_mine_only = on

    def _set_llm_for_theirs(self, on):
        self._set("llm_for_theirs", on)
        self.translator.llm_for_theirs = on

    def _set_translator_order(self, order, off):
        self.translator.set_order(order, off)
        self._set("translator_order", list(self.translator.order))
        self._set("translator_off", sorted(self.translator.off))
        config.save(self.cfg)

    def _set_only_chatboxes(self, on):
        self._set("ocr_only_chatboxes", on)
        if self.ocr:
            self.ocr.only_chatboxes = on

    def _provider_summary(self):
        def best(mine):
            for name in self.translator.order:
                if self.translator.available(name, 1, mine)[0]:
                    return NAMES[name]
            return "—"
        return f"Перевод: мои → {best(True)} · чужие → {best(False)}"

    def _ensure_recognizer(self):
        with self._rec_lock:
            key = (self.cfg["whisper_model"], self.cfg["device"])
            if self.recognizer is None or self._rec_key != key:
                from speech import Recognizer
                self._status(f"Загрузка модели {key[0]}... Первый раз она скачивается, подождите.")
                rec = Recognizer(key[0], key[1], log=self._status)
                rec.load()
                self.recognizer, self._rec_key = rec, key
                self._status(f"Модель {key[0]} загружена ({rec.backend}).")
            return self.recognizer

    def _queue_asr(self, kind, audio, auto=False):
        if (kind == "voice" or auto) and self.speaker is not None and self.speaker.busy():
            return
        if auto and self._vrc_muted():
            return
        self.asr_q.put((0 if kind == "mic" else 1, next(self._seq), kind, audio, time.monotonic()))

    def _asr_worker(self):
        while True:
            _, _, kind, audio, t = self.asr_q.get()
            if kind == "voice" and (not self.voice_on or time.monotonic() - t > 10):
                continue
            try:
                rec = self._ensure_recognizer()
                if kind == "mic":
                    t0 = time.monotonic()
                    text, lang = rec.transcribe(audio, [self.cfg["my_lang"]], detect=False)
                    self._mic_asr_s = time.monotonic() - t0
                else:
                    text, lang = rec.transcribe(audio, parse_langs(self.cfg["their_langs"]))
            except Exception as e:
                self._status(f"Ошибка распознавания: {e}")
                continue
            if kind == "mic":
                if text and is_noise(text):
                    text = ""
                if not text:
                    if not self.cfg["mic_auto"]:
                        self._status("Не расслышал — попробуйте ещё раз.")
                    self._typing(False)
                elif self.cfg["review_before_send"]:
                    self._typing(False)
                    self.ui_q.put(("review", text))
                else:
                    self.tr_q.put(("me", text, lang))
            elif text and lang != self.cfg["target_lang"]:
                self.tr_q.put(("voice", text, lang))

    def toggle_voice(self):
        if self.voice_on:
            self.voice_on = False
            if self.capture:
                self.capture.stop()
                self.capture = None
            self._status("Голос выключен.")
        else:
            self.voice_on = True
            threading.Thread(target=self._start_voice, daemon=True).start()
        self._update_buttons()

    def _start_voice(self):
        with self._voice_lock:
            try:
                rec = self._ensure_recognizer()
                if not self.voice_on or self.capture:
                    return
                from audio_capture import SpeechCapture
                cap = SpeechCapture(self.cfg["output_device"], lambda a: self._queue_asr("voice", a),
                                    lambda db, thr: self.ui_q.put(("level", db, thr)),
                                    lambda: self.cfg["vad_threshold_db"])
                cap.start()
                self.capture = cap
                self._status(f"Голос: слушаю «{cap.device_label}», распознавание: {rec.backend}")
            except Exception as e:
                self._status(f"Голос: ошибка — {e}")
                self.ui_q.put(("voice_off",))

    def toggle_chat(self):
        if self.chat_on:
            self.chat_on = False
            if self.ocr:
                self.ocr.stop()
                self.ocr = None
            self._status("Чат выключен.")
        else:
            from chat_ocr import ChatOCR
            self.chat_on = True
            self.ocr = ChatOCR(lambda t: self.tr_q.put(("chat", t, guess_lang(t, unsure="auto"))), self._status,
                               lambda: self.cfg["ocr_interval"], lambda: self.cfg["ocr_min_score"],
                               self.cfg["ocr_threads"], lambda: self._own_rect,
                               lambda: (set(parse_langs(self.cfg["their_langs"]))
                                        if self.cfg["their_langs"] != "auto" else None))
            self.ocr.only_chatboxes = self.cfg["ocr_only_chatboxes"]
            debug_dir = config.path("chat_debug")
            if os.path.isdir(debug_dir):
                self.ocr.debug_dir = debug_dir
                self._status("Чат: отладка включена — непрочитанные чатбоксы сохраняются в папку chat_debug.")
            self.ocr.start()
        self._update_buttons()

    def toggle_mic(self):
        if self.cfg["mic_auto"]:
            self._toggle_mic_listener()
            return
        if not self.mic_on:
            from audio_capture import MicRecorder
            try:
                rec = MicRecorder(self.cfg["mic_device"])
                rec.start()
            except Exception as e:
                self._status(f"Микрофон: ошибка — {e}")
                return
            self.recorder, self.mic_on = rec, True
            beep(880)
            self._typing(True)
            self._status(f"Говорите... Ещё раз {self.cfg['hotkey']} или кнопка — отправить. "
                         f"Микрофон: {rec.device_label}")
            if self.recognizer is None:
                threading.Thread(target=self._ensure_recognizer, daemon=True).start()
        else:
            self.mic_on = False
            audio = self.recorder.stop()
            self.recorder = None
            beep(440)
            if len(audio) < SR * 0.3:
                self._status("Слишком коротко.")
                self._typing(False)
            else:
                self._status("Распознаю и перевожу...")
                self._queue_asr("mic", audio)
        self._update_buttons()

    def _toggle_mic_listener(self):
        if self.mic_listener:
            self.mic_listener.stop()
            self.mic_listener = None
            beep(440)
            self._status("Авто-микрофон выключен.")
        else:
            from audio_capture import SpeechCapture
            try:
                listener = SpeechCapture(self.cfg["mic_device"], lambda a: self._queue_asr("mic", a, auto=True),
                                         lambda db, thr: None, lambda: self.cfg["mic_vad_threshold_db"],
                                         mic=True, end_silence=0.9)
                listener.start()
            except Exception as e:
                self._status(f"Микрофон: ошибка — {e}")
                return
            self.mic_listener = listener
            beep(880)
            self._status(f"Авто-микрофон: говорите — каждая фраза переводится сама. "
                         f"{self.cfg['hotkey']} — выключить. Микрофон: {listener.device_label}")
            if self.recognizer is None:
                threading.Thread(target=self._ensure_recognizer, daemon=True).start()
        self._update_buttons()

    def _vrc_muted(self):
        return bool(self.cfg["mic_only_unmuted"] and self.vrc_state.muted)

    def _set_mic_auto(self, on):
        self._set("mic_auto", on)
        if bool(self.mic_listener) != on:
            self._toggle_mic_listener()
        self._update_buttons()

    def _get_speaker(self):
        if self.speaker is None:
            from tts import Speaker
            self.speaker = Speaker(log=self._status, voices=self.cfg["tts_voices"])
        self.speaker.mixer = self.mixer
        return self.speaker

    def _speak(self, text):
        self._get_speaker().say_async(text, self.cfg["out_lang"], self.cfg["tts_device"])

    def _preload_voice(self):
        if self.cfg["tts_on"]:
            self._get_speaker().preload(self.cfg["out_lang"])

    def _restart_mixer(self):
        with self._mixer_lock:
            self._restart_mixer_locked()

    def _restart_mixer_locked(self):
        if self.mixer is not None:
            self.mixer.stop()
            self.mixer = None
        if self.cfg["voice_passthrough"]:
            from mixer import VoiceMixer
            error = None
            for attempt in range(3):
                mixer = VoiceMixer(self.cfg["mic_device"], self.cfg["tts_device"], mic_gain=self.cfg["mic_gain"])
                try:
                    mixer.start()
                    self.mixer = mixer
                    self._status(f"Ваш голос и озвучка идут в «{self.cfg['tts_device']}». "
                                 "В VRChat выберите этот микрофон.")
                    self._check_vrchat_mic(mixer)
                    break
                except Exception as e:
                    error = e
                    time.sleep(1)
            else:
                self._status(f"Голос в VRChat через переводчик не запустился: {error}")
        if self.speaker is not None:
            self.speaker.mixer = self.mixer

    def _check_vrchat_mic(self, mixer):
        from mixer import vrchat_mics
        mics = vrchat_mics(mixer.default_in)
        out = self.cfg["tts_device"].split(" (")[0]
        if mics and not any(name.split(" (")[0] == out for name in mics.values()):
            chosen = ", ".join(f"{mode}: «{name}»" for mode, name in mics.items())
            self._status(f"⚠ В VRChat выбран микрофон {chosen} — озвучку там не слышно. "
                         f"VRChat → Settings → Audio → Microphone → «{self.cfg['tts_device']}».")

    def _set_audio(self, key, value):
        self._set(key, value)
        threading.Thread(target=self._restart_mixer, daemon=True).start()

    def _send_typed(self, event=None):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.tr_q.put(("me", text, "auto"))

    def toggle_music(self):
        self.music_on = not self.music_on
        self._set("music_status", self.music_on)
        if not self.music_on:
            self.music_var.set("")
        self._update_buttons()

    def _music_paused(self):
        typing_in_vrchat = self.vrc_typing is not None and self.vrc_typing.typing
        speaking_auto = self.mic_listener is not None and self.mic_listener.in_speech
        return (self.mic_on or typing_in_vrchat or speaking_auto
                or time.monotonic() < self._music_pause_until)

    def _vrc_chat_opened(self):
        if self.music_on:
            self.ui_q.put(("music", "♪ пауза: вы пишете в чат VRChat"))

    def _vrc_chat_sent(self):
        self._music_pause_until = time.monotonic() + self.cfg["music_pause_s"]
        self._music_shown = False

    def _vrc_chat_cancelled(self):
        self._music_pause_until = time.monotonic() + 1

    def _music_worker(self):
        now_playing, last_update = None, 0.0
        while True:
            time.sleep(0.1)
            if not self.music_on:
                if self._music_shown:
                    self._send_music("")
                continue
            interval = max(osc.MIN_GAP, self.cfg["music_interval"])
            if self._music_paused() or time.monotonic() - last_update < interval:
                continue
            last_update = time.monotonic()
            try:
                if now_playing is None:
                    from media import NowPlaying
                    now_playing = NowPlaying()
                track = now_playing.get()
            except Exception as e:
                self.ui_q.put(("music", f"♪ ошибка: {e}"[:60]))
                continue
            if track:
                from media import format_track
                text = format_track(track, self.cfg["music_prefix"])
                self._send_music(text)
                self.ui_q.put(("music", text[:70]))
            else:
                self.ui_q.put(("music", "♪ ничего не играет"))
                if self._music_shown:
                    self._send_music("")

    def _send_music(self, text):
        if not self.cfg["send_to_chatbox"]:
            self._music_shown = False
            return
        try:
            osc.send_chatbox(text, self.cfg["osc_port"], notify=False)
        except OSError:
            return
        self._music_shown = bool(text)
        if text and self.ocr:
            self.ocr.mark_seen(text)

    def _typing(self, on):
        if self.cfg["send_to_chatbox"]:
            try:
                osc.set_typing(on, self.cfg["osc_port"])
            except OSError:
                pass

    def _tr_worker(self):
        while True:
            kind, text, lang = self.tr_q.get()
            try:
                if kind == "me":
                    t0 = time.monotonic()
                    out = self.translator.translate(text, lang, self.cfg["out_lang"], mine=True)
                    timing = f"перевод {time.monotonic() - t0:.1f} с ({self.translator.last_backend})"
                    if lang != "auto":
                        timing = f"распознано {self._mic_asr_s:.1f} с, " + timing
                    note = None
                    if self.cfg["send_to_chatbox"]:
                        self._music_pause_until = time.monotonic() + self.cfg["music_pause_s"]
                        osc.send_chatbox(out, self.cfg["osc_port"])
                        self._music_shown = False
                        if self.ocr:
                            self.ocr.mark_seen(out)
                        note = "→ отправлено в чат VRChat"
                    if self.cfg["tts_on"]:
                        self._speak(out)
                        note = (note + ", " if note else "→ ") + "озвучено"
                    self.ui_q.put(("result", kind, text, out, None, note))
                    self._status(("Отправлено: " if note else "Переведено (отправка в чат выключена): ")
                                 + timing)
                else:
                    if is_noise(text):
                        continue
                    out = self.translator.translate(text, lang)
                    if not_worth_showing(text, out, self.cfg["target_lang"]):
                        continue
                    self.ui_q.put(("result", kind, text, out, None, None))
            except Exception as e:
                if kind == "me":
                    self._typing(False)
                self.ui_q.put(("result", kind, text, None, str(e), None))

    def _warm_up_translator(self):
        self.translator.offline.load_in_background()
        self.translator.warm_up()
        try:
            self.translator.translate("hi", "en", "ru")
        except Exception:
            pass

    def _add_result(self, kind, orig, trans, err, note):
        ui.add_result(self, kind, orig, trans, err, note)

    def _status(self, msg):
        print(time.strftime("%H:%M:%S"), msg, flush=True)
        self.ui_q.put(("status", msg))

    def _poll(self):
        try:
            while True:
                msg = self.ui_q.get_nowait()
                if msg[0] == "status":
                    self.status_var.set(msg[1])
                elif msg[0] == "level":
                    self.level_db, self.effective_thr = msg[1], msg[2]
                elif msg[0] == "result":
                    self._add_result(*msg[1:])
                elif msg[0] == "voice_off":
                    self.voice_on = False
                    self._update_buttons()
                elif msg[0] == "mic_toggle":
                    self.toggle_mic()
                elif msg[0] == "vrc_mute":
                    self._update_buttons()
                    if self.mic_listener and self.cfg["mic_only_unmuted"]:
                        self._status("Микрофон в VRChat выключен — перевод речи на паузе." if msg[1]
                                     else "Микрофон в VRChat включён — перевожу вашу речь.")
                elif msg[0] == "review":
                    current = self.entry.get().strip()
                    self.entry.delete(0, "end")
                    self.entry.insert(0, f"{current} {msg[1]}".strip())
                    self.entry.icursor("end")
                    self.entry.focus_set()
                    self._status("Проверьте фразу в строке внизу и нажмите Enter (можно исправить).")
                elif msg[0] == "music":
                    self.music_var.set(msg[1] if self.music_on else "")
        except queue.Empty:
            pass
        r = self.root
        x, y = r.winfo_rootx(), r.winfo_rooty()
        self._own_rect = (x - 10, y - 40, x + r.winfo_width() + 10, y + r.winfo_height() + 10)
        ui.draw_meter(self)
        now = time.monotonic()
        if now - getattr(self, "_provider_shown", 0) > 1:
            self._provider_shown = now
            self.provider_var.set(self._provider_summary())
        self.root.after(50, self._poll)

    def _quit(self):
        self.voice_on = False
        if self.capture:
            self.capture.stop()
        if self.ocr:
            self.ocr.stop()
        if self.recorder:
            self.recorder.stop()
        if self.mic_listener:
            self.mic_listener.stop()
        if self.mixer:
            self.mixer.stop()
        self.cfg["geometry"] = self.root.geometry()
        config.save(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def already_running():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    already_running.mutex = kernel32.CreateMutexW(None, False, "VRChatTranslator.SingleInstance")
    return kernel32.GetLastError() == 183


def log_to_file():
    windowless = os.path.basename(sys.executable).lower() == "pythonw.exe"
    if not windowless and sys.stdout is not None and sys.stderr is not None:
        return
    path = config.path("app.log")
    try:
        if os.path.getsize(path) > 2_000_000:
            os.remove(path)
    except OSError:
        pass
    log = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n===== запуск {time.strftime('%Y-%m-%d %H:%M:%S')} =====")


def show_error(title, text):
    from tkinter import messagebox
    r = tk.Tk()
    r.withdraw()
    messagebox.showerror(title, text) if title.startswith("Ошибка") else messagebox.showinfo(title, text)
    r.destroy()


if __name__ == "__main__":
    log_to_file()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VRChatTranslator.App")
    if already_running():
        show_error("VRChat переводчик", "Переводчик уже запущен — его окно открыто.")
        sys.exit(0)
    try:
        App().run()
    except Exception:
        import traceback
        traceback.print_exc()
        show_error("Ошибка — VRChat переводчик",
                   f"Программа не смогла запуститься:\n\n{traceback.format_exc(limit=3)}\n"
                   f"Подробности в файле {config.path('app.log')}")
        sys.exit(1)
    sys.exit(0)
