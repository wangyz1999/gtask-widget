"""Render assets/icon.ico and assets/icon.png from the same painter the app uses.

    python packaging/make_icon.py
"""

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
from gtask_widget.ui.icons import app_pixmap  # noqa: E402


def to_pil(size: int) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    app_pixmap(size).save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


assets = ROOT / "assets"
assets.mkdir(exist_ok=True)
big = to_pil(256)
big.save(assets / "icon.png")
sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
big.save(assets / "icon.ico", sizes=[(s, s) for s in sizes],
         append_images=[to_pil(s) for s in sizes[:-1]])
print("wrote", assets / "icon.ico", assets / "icon.png")
