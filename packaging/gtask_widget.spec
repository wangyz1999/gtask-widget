# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/gtask_widget.spec --noconfirm
# Output: dist/GTaskWidget/GTaskWidget.exe (one-folder build: fast startup, no temp extraction)

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "gtask_widget" / "__init__.py").read_text()).group(1)
NUMS = tuple((list(map(int, re.findall(r"\d+", VERSION)[:3])) + [0, 0, 0])[:3]) + (0,)

# Official releases bundle the project's OAuth client (injected by CI, never committed).
datas = []
bundled = ROOT / "gtask_widget" / "_bundled_client.json"
if bundled.exists():
    datas.append((str(bundled), "gtask_widget"))
    print("Bundling OAuth client config")
else:
    print("No bundled OAuth client: users will be asked for a client_secret.json")

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    excludes=["tkinter", "unittest", "pydoc", "doctest", "pytest", "PIL",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtOpenGLWidgets"],
)

# Trim Qt pieces a widgets-only app never loads (software OpenGL alone is ~20 MB).
DROP = ("opengl32sw", "qt6pdf", "qt6quick", "qt6qml", "qt6virtualkeyboard", "qt6designer", "qdirect2d",
        "qopensslbackend", "qschannelbackend", "qcertonlybackend", "qjpeg", "qwebp", "qtiff", "qtga",
        "qwbmp", "qicns", "qpdf")
a.binaries = [b for b in a.binaries if not any(k in Path(b[0]).name.lower() for k in DROP)]
a.datas = [d for d in a.datas if "/translations/" not in d[0].replace("\\", "/").lower()]

version_file = ROOT / "build" / "version_info.txt"
version_file.parent.mkdir(exist_ok=True)
version_file.write_text(str(VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "GTask Widget contributors"),
            StringStruct("FileDescription", "GTask Widget"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "GTaskWidget"),
            StringStruct("LegalCopyright", "MIT License"),
            StringStruct("OriginalFilename", "GTaskWidget.exe"),
            StringStruct("ProductName", "GTask Widget"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)), encoding="utf-8")

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GTaskWidget",
    icon=str(ROOT / "assets" / "icon.ico"),
    version=str(version_file),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GTaskWidget", upx=False)
