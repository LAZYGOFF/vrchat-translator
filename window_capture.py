"""Снимок содержимого окна VRChat, даже если его перекрывают другие окна (PrintWindow)."""
import ctypes
import ctypes.wintypes as wt

import numpy as np

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 0x2  # нужен для DirectX-окон (Unity), иначе будет чёрный кадр

# 64-битные дескрипторы: без явных типов ctypes обрезает их до int
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wt.UINT]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def find_vrchat_hwnd():
    hwnd = user32.FindWindowW("UnityWndClass", "VRChat") or user32.FindWindowW(None, "VRChat")
    if not hwnd or user32.IsIconic(hwnd):
        return None
    return hwnd


def capture_window(hwnd):
    """Клиентская область окна как BGR-массив или None, если не вышло."""
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w < 100 or h < 100:
        return None
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        # 0x1 = только клиентская область
        if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT | 0x1):
            return None
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = np.empty((h, w, 4), np.uint8)
        if not gdi32.GetDIBits(mem, bmp, 0, h, buf.ctypes.data, ctypes.byref(bih), 0):
            return None
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)
    img = np.ascontiguousarray(buf[:, :, :3])
    if img.max() < 8:  # чёрный кадр — PrintWindow не поддерживается для этого окна
        return None
    return img
