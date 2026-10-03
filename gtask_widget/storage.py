"""Where the widget keeps its files, plus DPAPI-protected JSON for secrets.

Tokens and the task cache are encrypted with Windows DPAPI, so only the
signed-in Windows user can read them. On other platforms they fall back to
plain files with user-only permissions.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import APP_ID

_MAGIC = b"GTW1"


def data_dir() -> Path:
    override = os.environ.get("GTASK_WIDGET_HOME")
    if override:
        d = Path(override)
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_ID
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_ID
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "gtask-widget"
    d.mkdir(parents=True, exist_ok=True)
    return d


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def _dpapi(data: bytes, encrypt: bool) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        fn = _crypt32.CryptProtectData if encrypt else _crypt32.CryptUnprotectData
        desc = APP_ID if encrypt else None
        if not fn(ctypes.byref(blob_in), desc, None, None, None,
                  _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
            raise OSError(ctypes.get_last_error(), "DPAPI call failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    def protect(data: bytes) -> bytes:
        return _MAGIC + _dpapi(data, True)

    def unprotect(data: bytes) -> bytes:
        if data.startswith(_MAGIC):
            return _dpapi(data[len(_MAGIC):], False)
        return data

else:

    def protect(data: bytes) -> bytes:
        return data

    def unprotect(data: bytes) -> bytes:
        return data


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def write_secure_json(path: Path, obj) -> None:
    _atomic_write(path, protect(json.dumps(obj).encode("utf-8")))


def read_secure_json(path: Path):
    """Return the decoded object, or None if missing or unreadable."""
    try:
        return json.loads(unprotect(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return None


ALL_LISTS = "__all__"


@dataclass
class Settings:
    x: int | None = None
    y: int | None = None
    width: int = 340
    height: int = 500
    theme: str = "dark"            # dark | light | system
    glass: str = "balanced"        # clear | balanced | solid
    blur: bool = True
    layer: str = "desktop"         # desktop | top
    locked: bool = False
    refresh_minutes: int = 5
    current_list: str = ALL_LISTS
    chip: str = "all"              # see models.CHIPS
    sort: str = "my"               # my | date
    completed_open: bool = False
    filter_open: bool = False

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        s = cls()
        for k, v in raw.items():
            if k in known and (v is None or isinstance(v, type(getattr(s, k))) or getattr(s, k) is None):
                setattr(s, k, v)
        return s

    def save(self) -> None:
        _atomic_write(self.path(), json.dumps(asdict(self), indent=2).encode("utf-8"))
