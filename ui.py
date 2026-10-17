"""Внешний вид: главное окно (кнопки, субтитры, строка ввода) и окно настроек с вкладками.

Логика программы — в app.py; здесь только виджеты и то, как они вызывают методы App.
"""
import os
import tkinter as tk
from tkinter import colorchooser

import customtkinter as ctk

import theme

# ---------- палитра (берётся из настроек: set_palette) ----------
BG = CARD = CARD2 = HOVER = BORDER = FG = DIM = ACCENT = ""
VOICE = CHAT = ME = MUSIC = ""
REC, ERR = "#ef4444", "#ff6b6b"
LABELS = {}

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"
FONT_CJK = "Microsoft YaHei UI"


def set_palette(cfg):
    """Цвета из настроек (тема + свои цвета) — в глобальные константы этого модуля."""
    global BG, CARD, CARD2, HOVER, BORDER, FG, DIM, ACCENT, VOICE, CHAT, ME, MUSIC, LABELS
    c = theme.resolve(cfg)
    BG, CARD, CARD2, FG, DIM, ACCENT = c["bg"], c["card"], c["card2"], c["fg"], c["dim"], c["accent"]
    VOICE, CHAT, ME, MUSIC = c["voice"], c["chat"], c["me"], c["music"]
    HOVER = theme.mix(CARD2, FG, 0.12)
    BORDER = theme.mix(CARD2, FG, 0.07)
    LABELS = {"voice": ("ГОЛОС", VOICE), "chat": ("ЧАТ", CHAT), "me": ("Я", ME)}


set_palette({})


def see_through(app):
    """Фон окна полупрозрачный (подложка), а текст и кнопки — нет."""
    return app.cfg["bg_opacity"] < 0.995
HINT = ("Здесь появятся переводы.\n\n"
        "🎧 Голос — переводит, что говорят в игре\n"
        "💬 Чат — переводит чатбоксы над головами\n"
        "🎤 Микрофон (F8) — ваша речь → перевод → ваш чатбокс\n\n"
        "Или напишите по-русски в строке внизу.")


ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


def set_icon(window):
    """Своя иконка окна. customtkinter через ~200 мс ставит свою — поэтому ставим после него."""
    if os.path.exists(ICON):
        window.after(300, lambda: window.iconbitmap(ICON))
    window.after(300, lambda: style_titlebar(window))


def style_titlebar(window):
    """Заголовок окна — цветом фона темы, а не синим цветом акцента Windows (Windows 11)."""
    import ctypes

    def colorref(color):
        r, g, b = theme.rgb(color)
        return ctypes.c_uint(r | (g << 8) | (b << 16))
    try:
        hwnd = int(window.wm_frame(), 16)
        dwm = ctypes.windll.dwmapi
        for attr, color in ((35, BG), (36, FG), (34, BORDER)):  # заголовок, его текст, рамка
            value = colorref(color)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass  # Windows 10 так не умеет — останется как есть


def pill(parent, text, command, width=0):
    return ctk.CTkButton(parent, text=text, command=command, height=36, width=width, corner_radius=18,
                         fg_color=CARD2, hover_color=HOVER, text_color=FG, font=(FONT_BOLD, 13))


def icon_button(parent, text, command):
    return ctk.CTkButton(parent, text=text, command=command, width=36, height=36, corner_radius=18,
                         fg_color="transparent", hover_color=HOVER, text_color=DIM, font=(FONT, 16))


# =====================================================================
# Главное окно
# =====================================================================

def build_main(app):
    """Создаёт виджеты главного окна и кладёт нужные ссылки в app. Цвета — в restyle_main."""
    root = app.root
    w = app.widgets = {}

    # --- верхняя панель: переключатели ---
    top = w["top"] = ctk.CTkFrame(root, corner_radius=18)
    top.pack(fill="x", padx=12, pady=(12, 8))
    app.voice_btn = pill(top, "🎧  Голос", app.toggle_voice)
    app.chat_btn = pill(top, "💬  Чат", app.toggle_chat)
    app.mic_btn = pill(top, "🎤  Микрофон", app.toggle_mic)
    app.music_btn = pill(top, "♪  Музыка", app.toggle_music)
    for i, b in enumerate((app.voice_btn, app.chat_btn, app.mic_btn, app.music_btn)):
        b.pack(side="left", padx=(10 if i == 0 else 6, 0), pady=10)
    w["icons"] = [icon_button(top, "⚙", app.open_settings), icon_button(top, "🗑", app._clear)]
    w["icons"][0].pack(side="right", padx=(0, 8))
    w["icons"][1].pack(side="right")
    app.meter = tk.Canvas(top, width=70, height=8, highlightthickness=0)
    app.meter.pack(side="right", padx=10)

    # --- низ: статус и строка ввода (пакуются раньше субтитров, чтобы те их не вытеснили) ---
    footer = ctk.CTkFrame(root, fg_color="transparent")
    footer.pack(side="bottom", fill="x", padx=16, pady=(2, 10))
    app.status_var = tk.StringVar()
    app.music_var = tk.StringVar()
    app.provider_var = tk.StringVar()
    w["provider"] = ctk.CTkLabel(footer, textvariable=app.provider_var, font=(FONT, 11))
    w["provider"].pack(side="right")
    w["music"] = ctk.CTkLabel(footer, textvariable=app.music_var, font=(FONT, 11))
    w["music"].pack(side="right", padx=(0, 14))
    w["status"] = ctk.CTkLabel(footer, textvariable=app.status_var, font=(FONT, 11), anchor="w", justify="left")
    w["status"].pack(side="left", fill="x", expand=True)

    bottom = ctk.CTkFrame(root, fg_color="transparent")
    bottom.pack(side="bottom", fill="x", padx=12, pady=(0, 6))
    app.entry = ctk.CTkEntry(bottom, height=42, corner_radius=21, border_width=1, font=(FONT, 14),
                             placeholder_text="Напишите по-русски — переведу и отправлю в чат VRChat…")
    app.entry.pack(side="left", fill="x", expand=True)
    app.entry.bind("<Return>", app._send_typed)
    w["send"] = ctk.CTkButton(bottom, text="➤", command=app._send_typed, width=42, height=42, corner_radius=21,
                              font=(FONT_BOLD, 16))
    w["send"].pack(side="left", padx=(8, 0))

    # --- субтитры ---
    box = w["box"] = ctk.CTkTextbox(root, corner_radius=18, wrap="word", border_width=0)
    box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
    app.text = box._textbox  # обычный tk.Text: у него можно задавать шрифты тегам
    app.text.configure(padx=14, pady=10, cursor="xterm", spacing1=0)
    restyle_main(app)
    show_hint(app)


def restyle_main(app):
    """Перекрасить главное окно под текущую палитру (после смены темы — без перезапуска)."""
    w = app.widgets
    # при полупрозрачном фоне окно и субтитры красятся «ключевым» цветом — он становится дырой,
    # сквозь которую видна полупрозрачная подложка (см. backdrop.py)
    surface = theme.key_color(BG) if see_through(app) else BG
    box_color = surface if see_through(app) else CARD
    app.root.configure(fg_color=surface)
    w["top"].configure(fg_color=CARD)
    app.meter.configure(bg=CARD)
    for b in w["icons"]:
        b.configure(hover_color=HOVER, text_color=DIM)
    w["provider"].configure(text_color=DIM)
    w["music"].configure(text_color=MUSIC)
    w["status"].configure(text_color=DIM)
    app.entry.configure(fg_color=CARD2, border_color=BORDER, text_color=FG, placeholder_text_color=DIM)
    w["send"].configure(fg_color=ME, hover_color=theme.mix(ME, "#000000", 0.15), text_color=theme.on(ME))
    w["box"].configure(fg_color=box_color, scrollbar_button_color=CARD2, scrollbar_button_hover_color=HOVER)
    app.text.configure(bg=box_color, fg=FG, insertbackground=FG, selectbackground=HOVER,
                       inactiveselectbackground=HOVER)
    apply_fonts(app)
    update_buttons(app)


def apply_fonts(app):
    size = int(app.cfg["font_size"])
    t = app.text
    for kind, (_, color) in LABELS.items():
        t.tag_configure(f"lbl_{kind}", foreground=color, font=(FONT_BOLD, max(8, size - 5)), spacing1=12)
    t.tag_configure("time", foreground=DIM, font=(FONT, max(8, size - 5)))
    t.tag_configure("orig", foreground=DIM, font=(FONT_CJK, max(8, size - 3)), spacing1=2)
    t.tag_configure("trans", foreground=FG, font=(FONT, size), spacing1=2, spacing3=4)
    t.tag_configure("note", foreground=ME, font=(FONT, max(8, size - 6)))
    t.tag_configure("err", foreground=ERR, font=(FONT, max(8, size - 4)))
    t.tag_configure("right", justify="right", rmargin=4)  # мои сообщения — справа, как в мессенджере
    t.tag_configure("hint", foreground=DIM, font=(FONT, max(9, size - 3)), justify="center", spacing1=4)


def show_hint(app):
    t = app.text
    t.configure(state="normal")
    t.insert("end", "\n\n" + HINT, "hint")
    t.configure(state="disabled")
    app._hint_shown = True


def add_result(app, kind, orig, trans, err, note):
    t = app.text
    at_bottom = t.yview()[1] > 0.98
    t.configure(state="normal")
    if getattr(app, "_hint_shown", False):
        t.delete("1.0", "end")
        app._hint_shown = False
    side = ("right",) if kind == "me" else ()
    label, _ = LABELS[kind]
    import time
    t.insert("end", label, (f"lbl_{kind}",) + side)
    t.insert("end", "  " + time.strftime("%H:%M"), ("time",) + side)
    if note:
        t.insert("end", "   " + note, ("note",) + side)
    t.insert("end", "\n", side)
    if orig and (app.cfg["show_original"] or kind == "me"):
        t.insert("end", orig + "\n", ("orig",) + side)
    if trans:
        t.insert("end", trans + "\n", ("trans",) + side)
    else:
        t.insert("end", f"{err}\n", ("err",) + side)
    if int(t.index("end-1c").split(".")[0]) > 900:
        t.delete("1.0", "300.0")
    t.configure(state="disabled")
    if at_bottom:
        t.see("end")


def update_buttons(app):
    def style(btn, on, color, text):
        btn.configure(text=text, fg_color=color if on else CARD2,
                      hover_color=color if on else HOVER, text_color=theme.on(color) if on else FG)
    key = app.cfg["hotkey"]
    style(app.voice_btn, app.voice_on, VOICE, "🎧  Голос")
    style(app.chat_btn, app.chat_on, CHAT, "💬  Чат")
    if app.cfg["mic_auto"]:
        on = app.mic_listener is not None
        paused = on and getattr(app, "vrc_state", None) is not None and app._vrc_muted()
        if paused:  # в VRChat микрофон выключен — не переводим, пока не включите
            style(app.mic_btn, False, ME, f"🔇  Пауза: микрофон VRChat выкл · {key}")
        else:
            style(app.mic_btn, on, ME, f"●  Слушаю · {key}" if on else f"🎤  Авто-микрофон · {key}")
    else:
        style(app.mic_btn, app.mic_on, REC, f"●  Запись… · {key}" if app.mic_on else f"🎤  Микрофон · {key}")
    style(app.music_btn, app.music_on, MUSIC, "♪  Музыка")


def draw_meter(app):
    w, h = 70, 8
    lo, hi = -70.0, -10.0
    pos = lambda db: int((min(max(db, lo), hi) - lo) / (hi - lo) * w)
    thr = app.effective_thr if app.voice_on else app.cfg["vad_threshold_db"]
    m = app.meter
    m.delete("all")
    m.create_rectangle(0, 0, w, h, fill=CARD2, width=0)
    if app.voice_on:
        m.create_rectangle(0, 0, pos(app.level_db), h, fill=VOICE if app.level_db > thr else HOVER, width=0)
        x = pos(thr)
        m.create_line(x, 0, x, h, fill=CHAT, width=2)


# =====================================================================
# Окно настроек
# =====================================================================

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app, tab=None, geometry="600x560"):
        super().__init__(app.root)
        self.app = app
        self.title("Настройки")
        self.geometry(geometry)
        self.configure(fg_color=BG)
        self.attributes("-topmost", app.cfg["always_on_top"])
        self.after(100, self.lift)
        set_icon(self)
        self.tabs = tabs = ctk.CTkTabview(
            self, fg_color=CARD, corner_radius=18, segmented_button_fg_color=CARD2,
            segmented_button_selected_color=ACCENT, segmented_button_selected_hover_color=ACCENT,
            segmented_button_unselected_color=CARD2, segmented_button_unselected_hover_color=HOVER,
            text_color=FG, text_color_disabled=DIM)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)
        for name, build in (("Собеседники", self._tab_them), ("Мой голос", self._tab_me),
                            ("Озвучка", self._tab_tts), ("Перевод", self._tab_translate),
                            ("Музыка", self._tab_music), ("Вид", self._tab_look)):
            # вкладка прокручивается, если строк больше, чем помещается в окно
            frame = ctk.CTkScrollableFrame(tabs.add(name), fg_color="transparent",
                                           scrollbar_button_color=CARD2, scrollbar_button_hover_color=HOVER)
            frame.pack(fill="both", expand=True)
            frame.grid_columnconfigure(1, weight=1)
            self._row = 0
            build(frame)
        if tab:
            tabs.set(tab)
        self._refresh_status()

    # ---- конструкторы строк ----

    def _label(self, parent, text, hint=None):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=self._row, column=0, sticky="nw", padx=(8, 16), pady=(10, 0))
        ctk.CTkLabel(cell, text=text, text_color=FG, font=(FONT, 13), anchor="w").pack(anchor="w")
        if hint:
            ctk.CTkLabel(cell, text=hint, text_color=DIM, font=(FONT, 11), anchor="w", justify="left",
                         wraplength=230).pack(anchor="w")

    def option(self, parent, text, values, current, command, hint=None):
        self._label(parent, text, hint)
        menu = ctk.CTkOptionMenu(parent, values=values, command=command, fg_color=CARD2, button_color=CARD2,
                                 button_hover_color=HOVER, dropdown_fg_color=CARD2, dropdown_hover_color=HOVER,
                                 text_color=FG, font=(FONT, 13), dynamic_resizing=False, width=260)
        menu.set(current)
        menu.grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        self._row += 1
        return menu

    def switch(self, parent, text, value, command, hint=None):
        self._label(parent, text, hint)
        var = tk.BooleanVar(value=value)
        sw = ctk.CTkSwitch(parent, text="", width=46, variable=var, command=lambda: command(var.get()),
                           progress_color=ACCENT, button_color=FG, button_hover_color=FG, fg_color=CARD2)
        sw.grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        self._row += 1
        return var

    def slider(self, parent, text, lo, hi, value, command, fmt="{:.0f}", steps=None, hint=None):
        self._label(parent, text, hint)
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        shown = ctk.CTkLabel(cell, text=fmt.format(value), text_color=DIM, font=(FONT, 12), width=44)
        def changed(v):
            shown.configure(text=fmt.format(v))
            command(v)
        s = ctk.CTkSlider(cell, from_=lo, to=hi, number_of_steps=steps, command=changed, width=200,
                          progress_color=ACCENT, button_color=FG, button_hover_color=FG, fg_color=CARD2)
        s.set(value)
        s.pack(side="left")
        shown.pack(side="left", padx=(8, 0))
        self._row += 1

    def entry(self, parent, text, value, command, secret=False, hint=None, placeholder="", link=None):
        """Поле ввода; link — адрес, где получить ключ: пока поле пустое, рядом кнопка «Создать ключ»."""
        self._label(parent, text, hint)
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        e = ctk.CTkEntry(cell, width=260, fg_color=CARD2, border_color=BORDER, text_color=FG,
                         font=(FONT, 12), show="•" if secret else "", placeholder_text=placeholder,
                         placeholder_text_color=DIM)
        if value:
            e.insert(0, value)
        e.pack(side="left")
        save = lambda *_: command(e.get().strip())
        if link:
            import webbrowser
            button = ctk.CTkButton(cell, text="Создать ключ", command=lambda: webbrowser.open(link), width=114,
                                   height=28, corner_radius=8, fg_color=ACCENT,
                                   hover_color=theme.mix(ACCENT, "#000000", 0.15), text_color=theme.on(ACCENT),
                                   font=(FONT, 12))

            def show_button(*_):
                """Ключ уже есть — кнопка не нужна; стёрли ключ — кнопка вернётся."""
                need, shown = not e.get().strip(), bool(button.winfo_manager())
                if need and not shown:
                    e.configure(width=140)
                    button.pack(side="left", padx=(6, 0))
                elif not need and shown:
                    button.pack_forget()
                    e.configure(width=260)
            e.bind("<KeyRelease>", show_button, add="+")
            e.bind("<<Paste>>", lambda *_: e.after(10, show_button), add="+")
            if not value:
                e.configure(width=140)
                button.pack(side="left", padx=(6, 0))
            save_key = save
            save = lambda *_: (save_key(), show_button())  # вставили ключ мышкой и ушли из поля
        e.bind("<Return>", save)
        e.bind("<FocusOut>", save)
        self._row += 1
        return e

    def note(self, parent, text, color=DIM):
        lbl = ctk.CTkLabel(parent, text=text, text_color=color, font=(FONT, 11), justify="left", anchor="w",
                           wraplength=490)
        lbl.grid(row=self._row, column=0, columnspan=2, sticky="w", padx=8, pady=(14, 0))
        self._row += 1
        return lbl

    # ---- вкладки ----

    def _tab_them(self, f):
        a = self.app
        from app import MODELS, DEFAULT_DEVICE
        from audio_capture import list_output_devices
        self._lang_picker(f)
        self.option(f, "Звук игры", [DEFAULT_DEVICE] + list_output_devices(), a.cfg["output_device"] or DEFAULT_DEVICE,
                    lambda v: a._set_restart("output_device", "" if v == DEFAULT_DEVICE else v),
                    "Куда VRChat выводит звук (наушники).")
        self.option(f, "Модель распознавания", MODELS, a.cfg["whisper_model"],
                    lambda v: a._set_restart("whisper_model", v), "small — быстрее, large-v3-turbo — точнее.")
        self.slider(f, "Порог громкости речи", -70, -15, a.cfg["vad_threshold_db"],
                    lambda v: a._set("vad_threshold_db", int(v)), "{:.0f} дБ", steps=55,
                    hint="Не ловит фразы — левее. Ловит шум — правее.")
        self.switch(f, "Чат: только чатбоксы", a.cfg["ocr_only_chatboxes"], a._set_only_chatboxes,
                    "Выключите, если настоящие чатбоксы не ловятся.")

    def _lang_picker(self, f):
        """Языки собеседников галочками: любые вместе или «любой язык»."""
        a = self.app
        from app import THEIR_LANGS
        self._label(f, "Языки собеседников", "Для голоса и для чата. Остальное не переводится.")
        self._row += 1
        box = ctk.CTkFrame(f, fg_color=CARD2, corner_radius=12)
        box.grid(row=self._row, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        self._row += 1
        current = a.cfg["their_langs"]
        chosen = set() if current == "auto" else set(current.split("+"))
        any_var = tk.BooleanVar(value=current == "auto")
        boxes = {}

        def save(clicked=None):
            picked = [code for code in THEIR_LANGS if boxes[code][0].get()]
            if any_var.get():
                a._set("their_langs", "auto")
            elif picked:
                a._set("their_langs", "+".join(picked))
            else:  # ни одного — нельзя: возвращаем галочку, которую сняли
                boxes[clicked][0].set(True)
                return
            for code, (var, cb) in boxes.items():
                cb.configure(state="disabled" if any_var.get() else "normal")

        style = dict(font=(FONT, 13), text_color=FG, fg_color=ACCENT, hover_color=ACCENT, border_color=DIM,
                     checkmark_color=theme.on(ACCENT), text_color_disabled=DIM, checkbox_width=20, checkbox_height=20)
        for i, (code, title) in enumerate(THEIR_LANGS.items()):
            var = tk.BooleanVar(value=code in chosen)
            cb = ctk.CTkCheckBox(box, text=title, variable=var, command=lambda c=code: save(c), **style)
            cb.grid(row=i // 4, column=i % 4, sticky="w", padx=(12, 4), pady=6)
            boxes[code] = (var, cb)
        ctk.CTkCheckBox(box, text="Любой язык (кроме русского)", variable=any_var, command=save, **style).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=12, pady=(2, 8))
        if any_var.get():
            for var, cb in boxes.values():
                cb.configure(state="disabled")

    def _tab_me(self, f):
        a = self.app
        from app import MY_LANGS, OUT_LANGS, DEFAULT_DEVICE, label_of
        from audio_capture import list_input_devices
        self.option(f, "Микрофон", [DEFAULT_DEVICE] + list_input_devices(), a.cfg["mic_device"] or DEFAULT_DEVICE,
                    lambda v: a._set_audio("mic_device", "" if v == DEFAULT_DEVICE else v))
        self.option(f, "Я говорю на", list(MY_LANGS), label_of(MY_LANGS, a.cfg["my_lang"]),
                    lambda v: a._set("my_lang", MY_LANGS[v]))
        self.option(f, "Переводить меня на", list(OUT_LANGS), label_of(OUT_LANGS, a.cfg["out_lang"]),
                    lambda v: (a._set("out_lang", OUT_LANGS[v]), a._preload_voice()))
        self.switch(f, "Отправлять в чат VRChat", a.cfg["send_to_chatbox"], lambda v: a._set("send_to_chatbox", v))
        self.switch(f, "Переводить речь сам (без кнопки)", a.cfg["mic_auto"], a._set_mic_auto,
                    "Просто говорите в VRChat — каждая фраза сама переводится и появляется над головой. "
                    "Слушает с запуска программы; F8 — пауза.")
        self.switch(f, "Только когда в VRChat включён микрофон", a.cfg["mic_only_unmuted"],
                    lambda v: (a._set("mic_only_unmuted", v), a._update_buttons()),
                    "Выключили микрофон в игре (красный значок) — перевод на паузе. VRChat сообщает это "
                    "сам по OSC; если после запуска не сработало — один раз включите/выключите микрофон в игре.")
        self.switch(f, "Проверять фразу перед отправкой", a.cfg["review_before_send"],
                    lambda v: a._set("review_before_send", v), "Фраза попадёт в строку ввода, отправка — Enter.")
        self.note(f, f"Горячая клавиша микрофона: {a.cfg['hotkey']} (работает и в игре).")

    def _tab_tts(self, f):
        a = self.app
        from tts import list_output_devices
        self.switch(f, "Озвучивать мой перевод", a.cfg["tts_on"],
                    lambda v: (a._set("tts_on", v), a._preload_voice()),
                    "Офлайн-голоса: английский, китайский, японский, корейский и др.")
        self.option(f, "Куда озвучивать", list_output_devices(), a.cfg["tts_device"],
                    lambda v: a._set_audio("tts_device", v),
                    "Line 1 (Virtual Audio Cable) — виртуальный провод: что в него играет, "
                    "выходит из микрофона «Line 1». Наушники сюда не выбирайте.")
        self.switch(f, "Мой голос тоже туда", a.cfg["voice_passthrough"],
                    lambda v: a._set_audio("voice_passthrough", v),
                    "Тогда в игре слышно и вас, и озвучку. Работает, пока программа открыта.")
        self.note(f, "Путь звука: микрофон (вкладка «Мой голос») + озвучка → Line 1 → VRChat.\n"
                     "Чтобы озвучку слышали в игре: VRChat → Settings → Audio → Microphone → "
                     "Line 1 (Virtual Audio Cable).", CHAT)

    def _tab_translate(self, f):
        a = self.app
        self._label(f, "Каким переводчиком", "«Все по очереди» — лучший доступный, кончился лимит — следующий.")
        seg = ctk.CTkSegmentedButton(f, values=["Все по очереди", "Только офлайн"],
                                     command=lambda v: a._set_translator_mode("offline" if v == "Только офлайн" else "auto"),
                                     selected_color=ACCENT, selected_hover_color=ACCENT, unselected_color=CARD2,
                                     unselected_hover_color=HOVER, fg_color=CARD2, text_color=FG, font=(FONT, 12))
        seg.set("Только офлайн" if a.cfg["translator"] == "offline" else "Все по очереди")
        seg.grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        self._row += 1
        self.entry(f, "Ключ DeepL", a.cfg["deepl_key"], lambda v: a._set_key("deepl_key", v), secret=True,
                   hint="Бесплатный API-тариф (Free / Developer). Остаток программа узнаёт у DeepL сама.",
                   placeholder="необязательно", link="https://www.deepl.com/your-account/keys")
        self.entry(f, "Ключ Gemini", a.cfg["gemini_key"], lambda v: a._set_key("gemini_key", v), secret=True,
                   hint="Бесплатно, без карты: aistudio.google.com → Get API key. Лучше всех понимает сленг.",
                   placeholder="необязательно", link="https://aistudio.google.com/apikey")
        self.entry(f, "Ключ Groq", a.cfg["groq_key"], lambda v: a._set_key("groq_key", v), secret=True,
                   hint="Бесплатно, без карты: console.groq.com → API Keys. Очень быстрый.",
                   placeholder="необязательно", link="https://console.groq.com/keys")
        self.entry(f, "Почта для MyMemory", a.cfg["mymemory_email"], lambda v: a._set_key("mymemory_email", v),
                   hint="Необязательно: с почтой лимит 50 000 вместо 5 000 символов в день.",
                   placeholder="необязательно")
        self.switch(f, "DeepL — только для моих", a.cfg["keys_for_mine_only"], a._set_keys_mine_only,
                    "У них лимит в символах — бережём его для ваших сообщений.")
        self.switch(f, "Gemini / Groq — и для чужой речи", a.cfg["llm_for_theirs"], a._set_llm_for_theirs,
                    "У них лимит в запросах в день, хватает и на собеседников.")
        self.note(f, "Порядок переводчиков — перетащите мышкой за ⠿ (или ▲▼). Переводит первый доступный; "
                     "кончился лимит или нет ключа — следующий. Выключатель справа убирает сервис совсем.")
        self.priority = PriorityList(f, a)
        self.priority.grid(row=self._row, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 12))
        self._row += 1

    def _tab_music(self, f):
        a = self.app
        self.music_var = self.switch(f, "Музыка в чатбоксе", a.music_on, lambda v: a.toggle_music() if v != a.music_on else None,
                                     "«♪ Исполнитель — Трек» над головой, обновление раз в 1,6 с.")
        self.slider(f, "Прятать после моего сообщения", 5, 60, a.cfg["music_pause_s"],
                    lambda v: a._set("music_pause_s", int(v)), "{:.0f} с", steps=55)
        self.note(f, f"Клавиша чата VRChat: {', '.join(a.cfg['vrchat_chat_keys'])} — пока вы в нём пишете, "
                     "музыка ждёт (меняется в config.json: vrchat_chat_keys).")

    def _tab_look(self, f):
        a = self.app
        self.switch(f, "Поверх всех окон", a.cfg["always_on_top"],
                    lambda v: (a._set("always_on_top", v), a._apply_window_opts()))
        self.switch(f, "Показывать оригинал", a.cfg["show_original"], lambda v: a._set("show_original", v))
        self.slider(f, "Размер шрифта", 10, 28, a.cfg["font_size"],
                    lambda v: (a._set("font_size", int(v)), apply_fonts(a)), steps=18)
        self.slider(f, "Прозрачность фона", 0.0, 100.0, round((1 - a.cfg["bg_opacity"]) * 100),
                    lambda v: a._set_bg_opacity(1 - v / 100), "{:.0f} %", steps=20,
                    hint="Фон просвечивает, а текст и кнопки остаются чёткими.")
        self.slider(f, "Прозрачность всего окна", 0.0, 60.0, round((1 - a.cfg["opacity"]) * 100),
                    lambda v: (a._set("opacity", round(1 - v / 100, 2)), a._apply_window_opts()), "{:.0f} %",
                    steps=12, hint="Просвечивает всё, вместе с текстом.")

        own = bool(a.cfg.get("theme"))
        self.option(f, "Тема", list(theme.PRESETS) + ([theme.CUSTOM] if own else []),
                    theme.CUSTOM if own else a.cfg["theme_preset"],
                    lambda v: a._set_theme_preset(v) if v != theme.CUSTOM else None,
                    "Готовые цвета. Любой цвет ниже можно поменять — тема станет «Своя».")
        colors = theme.resolve(a.cfg)
        for key, title in theme.FIELDS:
            self._color_row(f, title, key, colors[key])
        reset = ctk.CTkButton(f, text="Сбросить цвета", command=lambda: a._set_theme_preset(theme.DEFAULT),
                              fg_color=CARD2, hover_color=HOVER, text_color=FG, font=(FONT, 12), width=160)
        reset.grid(row=self._row, column=1, sticky="e", padx=8, pady=(14, 10))
        self._row += 1

    def _color_row(self, parent, title, key, color):
        """Строка «название — образец цвета»: клик открывает выбор цвета Windows."""
        self._label(parent, title)

        def pick():
            chosen = colorchooser.askcolor(color=color, parent=self, title=title)[1]
            if chosen:
                self.app._set_color(key, chosen)
        ctk.CTkButton(parent, text=color.upper(), command=pick, width=120, height=28, corner_radius=8,
                      fg_color=color, hover_color=theme.mix(color, FG, 0.15), text_color=theme.on(color),
                      border_width=1, border_color=BORDER, font=(FONT, 12)
                      ).grid(row=self._row, column=1, sticky="e", padx=8, pady=(10, 0))
        self._row += 1

    def _refresh_status(self):
        if not self.winfo_exists():
            return
        self.priority.show_states(self.app.translator.states())
        self.after(1000, self._refresh_status)


class PriorityList(ctk.CTkFrame):
    """Сервисы перевода по приоритету: перетаскивание мышкой, ▲▼ и выключатель у каждого."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        from translator import NAMES, ABOUT
        self.app = app
        self.order = list(app.translator.order)
        self.off = set(app.translator.off)
        self.rows = {}
        self._drag = None
        for name in self.order:
            self.rows[name] = self._make_row(name, NAMES[name], ABOUT[name])
        self._layout()

    def _make_row(self, name, title, about):
        row = ctk.CTkFrame(self, fg_color=CARD2, corner_radius=12, border_width=1, border_color=CARD2)
        row.grid_columnconfigure(2, weight=1)
        handle = ctk.CTkLabel(row, text="⠿", text_color=DIM, font=(FONT, 18), width=26, cursor="fleur")
        handle.grid(row=0, column=0, rowspan=2, padx=(10, 2), pady=6)
        num = ctk.CTkLabel(row, text="", text_color=ACCENT, font=(FONT_BOLD, 14), width=22, cursor="fleur")
        num.grid(row=0, column=1, rowspan=2, padx=(0, 6))
        ctk.CTkLabel(row, text=title, text_color=FG, font=(FONT_BOLD, 13), anchor="w").grid(
            row=0, column=2, sticky="sw", pady=(6, 0))
        ctk.CTkLabel(row, text=about, text_color=DIM, font=(FONT, 11), anchor="w").grid(
            row=1, column=2, sticky="nw", pady=(0, 6))
        state = ctk.CTkLabel(row, text="", text_color=DIM, font=(FONT, 11), anchor="e", wraplength=190,
                             justify="right")
        state.grid(row=0, column=3, rowspan=2, padx=6)
        arrows = ctk.CTkFrame(row, fg_color="transparent")
        arrows.grid(row=0, column=4, rowspan=2)
        for text, step in (("▲", -1), ("▼", 1)):
            ctk.CTkButton(arrows, text=text, width=24, height=18, corner_radius=6, fg_color="transparent",
                          hover_color=HOVER, text_color=DIM, font=(FONT, 10),
                          command=lambda s=step: self._move(name, s)).pack()
        var = tk.BooleanVar(value=name not in self.off)
        sw = ctk.CTkSwitch(row, text="", width=46, variable=var, progress_color=ACCENT, button_color=FG,
                           button_hover_color=FG, fg_color=HOVER, command=lambda: self._toggle(name, var.get()))
        sw.grid(row=0, column=5, rowspan=2, padx=(4, 6))
        if name == "offline":  # запасной на любой случай — выключить нельзя
            sw.configure(state="disabled")
        for w in (row, handle, num):
            w.bind("<ButtonPress-1>", lambda e, n=name: self._start(n))
            w.bind("<B1-Motion>", self._motion)
            w.bind("<ButtonRelease-1>", self._drop)
        return {"frame": row, "num": num, "state": state}

    def _layout(self):
        for i, name in enumerate(self.order):
            r = self.rows[name]
            r["frame"].grid(row=i, column=0, sticky="ew", pady=3)
            r["num"].configure(text=f"{i + 1}")
        self.grid_columnconfigure(0, weight=1)

    # ---- перетаскивание ----

    def _start(self, name):
        self._drag = name
        self.rows[name]["frame"].configure(border_color=ACCENT)

    def _motion(self, event):
        if not self._drag:
            return
        frames = [self.rows[n]["frame"] for n in self.order]
        y = event.y_root - self.winfo_rooty()
        # куда встать: перед первой строкой, середина которой ниже курсора
        target = len(self.order) - 1
        for i, fr in enumerate(frames):
            if y < fr.winfo_y() + fr.winfo_height() / 2:
                target = i
                break
        current = self.order.index(self._drag)
        if target != current:
            self.order.insert(target, self.order.pop(current))
            self._layout()

    def _drop(self, _event=None):
        if self._drag:
            self.rows[self._drag]["frame"].configure(border_color=CARD2)
            self._drag = None
            self._save()

    def _move(self, name, step):
        i = self.order.index(name)
        j = min(max(i + step, 0), len(self.order) - 1)
        if i != j:
            self.order.insert(j, self.order.pop(i))
            self._layout()
            self._save()

    def _toggle(self, name, on):
        (self.off.discard if on else self.off.add)(name)
        self._save()

    def _save(self):
        self.app._set_translator_order(self.order, self.off)
        self.show_states(self.app.translator.states())

    def show_states(self, states):
        for name, r in self.rows.items():
            text, ok = states.get(name, ("", False))
            r["state"].configure(text=text, text_color=ME if ok else DIM)
