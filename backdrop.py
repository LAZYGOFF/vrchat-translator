"""Полупрозрачный фон окна, при котором текст и кнопки остаются полностью непрозрачными.

Windows не умеет делать полупрозрачным только фон обычного окна: «-alpha» просвечивает всё сразу,
вместе с текстом. Поэтому так: в самом окне фон помечается «ключевым» цветом и становится дырой
(-transparentcolor), а прямо под окном лежит вторая, пустая полупрозрачная «подложка» того же цвета.
Подложка ходит за окном, прячется вместе с ним и всегда остаётся под ним.
"""
import ctypes
import ctypes.wintypes as wt
import tkinter as tk

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
user32.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
gdi32.CreateRoundRectRgn.restype = wt.HANDLE

SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040
WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11
CORNER = 8  # радиус скругления окна в Windows 11 (при масштабе 100 %)


def _hwnd(window):
    return int(window.wm_frame(), 16)


class Backdrop:
    def __init__(self, root, on_wheel=None):
        self.root = root
        self.on_wheel = on_wheel  # колесо мыши над прозрачной частью — прокрутка субтитров
        self.win = None
        self._rect = None
        self._hidden_capture = False

    @property
    def active(self):
        return self.win is not None

    def apply(self, color, alpha, topmost, hide_from_capture=False):
        """alpha < 1 — включить подложку (цвет color), иначе убрать её."""
        if alpha >= 0.995:
            self.disable()
            return
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)  # без рамки и без кнопки на панели задач
            self.win.bind("<Button>", lambda e: self.root.focus_force())
            if self.on_wheel:
                self.win.bind("<MouseWheel>", self.on_wheel)
            self._rect = None
            self._tick()
        self.win.configure(bg=color)
        self.win.attributes("-alpha", alpha, "-topmost", topmost)
        self._hidden_capture = hide_from_capture
        self.win.after_idle(self._capture_affinity)
        self.sync()

    def disable(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def _capture_affinity(self):
        try:
            user32.SetWindowDisplayAffinity(_hwnd(self.win), WDA_EXCLUDEFROMCAPTURE if self._hidden_capture
                                            else WDA_NONE)
        except Exception:
            pass

    def _tick(self):
        if self.win is None:
            return
        self.sync()
        self.win.after(100, self._tick)

    def sync(self, *_):
        """Подложка — ровно под клиентской частью окна и сразу под ним по глубине."""
        if self.win is None:
            return
        root = self.root
        try:
            state = root.state()
        except tk.TclError:
            return
        if state in ("iconic", "withdrawn"):
            if self.win.state() != "withdrawn":
                self.win.withdraw()
            return
        if self.win.state() == "withdrawn":
            self.win.deiconify()
            self._rect = None
        rect = (root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height())
        try:
            hwnd, root_hwnd = _hwnd(self.win), _hwnd(root)
        except (tk.TclError, ValueError):
            return
        # SetWindowPos со «вставить после окна программы» кладёт подложку прямо под него
        user32.SetWindowPos(hwnd, root_hwnd, *rect, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        if rect != self._rect:
            self._rect = rect
            self._round_bottom(hwnd, rect[2], rect[3], state == "zoomed")

    def _round_bottom(self, hwnd, w, h, zoomed):
        """Нижние углы окна Windows 11 скруглены — скругляем и подложку, чтобы не торчала."""
        r = 0 if zoomed else round(CORNER * self.root.winfo_fpixels("1i") / 96)
        if r <= 0:
            user32.SetWindowRgn(hwnd, None, True)
            return
        # прямоугольник со скруглёнными углами, верх которого спрятан выше окна: скруглён только низ
        rgn = gdi32.CreateRoundRectRgn(0, -2 * r, w + 1, h + 1, 2 * r, 2 * r)
        user32.SetWindowRgn(hwnd, rgn, True)  # регион теперь принадлежит окну, удалять не нужно
