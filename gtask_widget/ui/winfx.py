"""Windows-specific window effects: acrylic blur, rounded corners, desktop pinning,
and the "start with Windows" setting. Every function is a safe no-op elsewhere."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
WIN11 = IS_WINDOWS and sys.getwindowsversion().build >= 22000

if IS_WINDOWS:
    import ctypes
    import winreg
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi")

    class _AccentPolicy(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

    class _CompositionData(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p),
                    ("SizeOfData", ctypes.c_size_t)]

    _user32.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.POINTER(_CompositionData)]
    _user32.SetWindowCompositionAttribute.restype = wintypes.BOOL
    _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowW.restype = wintypes.HWND
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    _WCA_ACCENT_POLICY = 19
    _ACCENT_DISABLED = 0
    _ACCENT_BLURBEHIND = 3
    _ACCENT_ACRYLIC = 4
    _DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    _DWMWA_WINDOW_CORNER_PREFERENCE = 33
    _DWMWA_BORDER_COLOR = 34
    _DWMWCP_DEFAULT, _DWMWCP_ROUND = 0, 2
    _DWMWA_COLOR_NONE = 0xFFFFFFFE
    _GWLP_HWNDPARENT = -8


def _dwm_set(hwnd: int, attr: int, value: int) -> None:
    v = ctypes.c_uint(value & 0xFFFFFFFF)
    _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))


def transparency_enabled() -> bool:
    """Windows Settings > Personalization > Colors > Transparency effects."""
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "EnableTransparency")[0] != 0
    except OSError:
        return True


def set_backdrop(hwnd: int, blur: bool) -> bool:
    """Blur whatever is behind the window. Returns True if blur is active."""
    if not IS_WINDOWS:
        return False
    # With transparency effects off, Windows won't blur; fall back to a denser tint.
    blur = blur and transparency_enabled()
    # Acrylic on Windows 11; plain blur on Windows 10, where acrylic lags while dragging.
    state = (_ACCENT_ACRYLIC if WIN11 else _ACCENT_BLURBEHIND) if blur else _ACCENT_DISABLED
    accent = _AccentPolicy(state, 0, 0x01000000 if blur else 0, 0)
    data = _CompositionData(_WCA_ACCENT_POLICY, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                            ctypes.sizeof(accent))
    ok = bool(_user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))
    if not ok:
        log.info("Blur unavailable on this system")
    return blur and ok


def style_frame(hwnd: int, dark: bool, rounded: bool) -> None:
    """Windows 11: native rounded corners, no system border, dark/light hint."""
    if not WIN11:
        return
    _dwm_set(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND if rounded else _DWMWCP_DEFAULT)
    _dwm_set(hwnd, _DWMWA_BORDER_COLOR, _DWMWA_COLOR_NONE)
    _dwm_set(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def _desktop_window() -> int:
    return _user32.FindWindowW("Progman", None) or 0


def pin_to_desktop(hwnd: int, pinned: bool) -> None:
    """Make the desktop own the window so it stays visible on "Show desktop" (Win+D)."""
    if not IS_WINDOWS:
        return
    owner = _desktop_window() if pinned else 0
    _user32.SetWindowLongPtrW(hwnd, _GWLP_HWNDPARENT, owner)


def is_pinned(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return True
    owner = _user32.GetWindowLongPtrW(hwnd, _GWLP_HWNDPARENT)
    return bool(owner) and bool(_user32.IsWindow(owner)) and owner == _desktop_window()


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def primary_button_down() -> bool:
    """Whether the primary mouse button is physically held (respects swapped buttons)."""
    if not IS_WINDOWS:
        return False
    vk = 0x02 if _user32.GetSystemMetrics(23) else 0x01  # SM_SWAPBUTTON -> VK_RBUTTON / VK_LBUTTON
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def set_app_id(app_id: str) -> None:
    if IS_WINDOWS:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except (AttributeError, OSError):
            pass


# --------------------------------------------------------------------------- start with Windows

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "GTaskWidget"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" -m gtask_widget'


def startup_supported() -> bool:
    return IS_WINDOWS


def startup_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_VALUE)
            return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, _RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, _RUN_VALUE)
            except FileNotFoundError:
                pass
