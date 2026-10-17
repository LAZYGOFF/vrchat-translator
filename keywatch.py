import ctypes
import ctypes.wintypes as wt
import threading
import time

from window_capture import find_vrchat_hwnd

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
VK_RETURN, VK_ESCAPE = 0x0D, 0x1B
TYPING_TIMEOUT = 90

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.GetForegroundWindow.restype = wt.HWND
kernel32.GetModuleHandleW.restype = wt.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


def key_code(name):
    name = name.strip().upper()
    if len(name) == 1 and name.isalnum():
        return ord(name)
    if name.startswith("F") and name[1:].isdigit():
        return 0x6F + int(name[1:])
    raise ValueError(f"неизвестная клавиша {name!r}")


class VRChatTypingWatcher:
    def __init__(self, chat_keys, on_open, on_send, on_cancel, is_vrchat_front=None):
        self.chat_keys = {key_code(k) for k in chat_keys}
        self.on_open, self.on_send, self.on_cancel = on_open, on_send, on_cancel
        self.is_vrchat_front = is_vrchat_front or self._vrchat_front
        self.typing_since = None
        self._proc = HOOKPROC(self._hook)

    @property
    def typing(self):
        if self.typing_since and time.monotonic() - self.typing_since > TYPING_TIMEOUT:
            self.typing_since = None
        return self.typing_since is not None

    def start(self):
        ready = threading.Event()
        self.ok = False

        def run():
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
            self.ok = bool(hook)
            ready.set()
            if not hook:
                return
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass

        threading.Thread(target=run, daemon=True).start()
        ready.wait(2)
        return self.ok

    @staticmethod
    def _vrchat_front():
        hwnd = find_vrchat_hwnd()
        return bool(hwnd) and user32.GetForegroundWindow() == hwnd

    def handle_key(self, vk):
        if vk not in self.chat_keys and vk not in (VK_RETURN, VK_ESCAPE):
            return
        if not self.is_vrchat_front():
            return
        if not self.typing:
            if vk in self.chat_keys:
                self.typing_since = time.monotonic()
                self.on_open()
        elif vk == VK_RETURN:
            self.typing_since = None
            self.on_send()
        elif vk == VK_ESCAPE:
            self.typing_since = None
            self.on_cancel()

    def _hook(self, n_code, w_param, l_param):
        try:
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self.handle_key(ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode)
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
