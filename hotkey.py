import ctypes
import ctypes.wintypes as wt
import threading

user32 = ctypes.windll.user32
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

KEYS = {f"F{i}": 0x6F + i for i in range(1, 13)}
KEYS.update({"PAUSE": 0x13, "SCROLLLOCK": 0x91, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23})


class GlobalHotkey:
    def __init__(self, key_name, callback):
        self.key_name = key_name.upper()
        self.callback = callback
        self.ok = False
        self._ready = threading.Event()

    def start(self):
        if self.key_name not in KEYS:
            return False
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(2)
        return self.ok

    def _run(self):
        self.ok = bool(user32.RegisterHotKey(None, 1, MOD_NOREPEAT, KEYS[self.key_name]))
        self._ready.set()
        if not self.ok:
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.callback()
