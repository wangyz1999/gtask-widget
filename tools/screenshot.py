"""Render README screenshots: the demo widget over a generated "wallpaper".

    python tools/screenshot.py [out_dir] [--theme dark|light] [--filter] [--wallpaper dusk|light|photo]

Uses sample data only, so no personal tasks end up in images.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GTASK_WIDGET_HOME", tempfile.mkdtemp(prefix="gtask-shot-"))

from PySide6.QtCore import QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

WALLPAPERS = {
    "dusk": (["#1e3c72", "#7b2ff7", "#f857a6"], [(0.15, 0.25, "#00c6ff"), (0.8, 0.3, "#ffb347"), (0.55, 0.8, "#43e97b")]),
    "light": (["#fdf6e3", "#e8f1fb", "#fbe3ea"], [(0.2, 0.3, "#ffd166"), (0.7, 0.6, "#a0e7e5"), (0.45, 0.85, "#ffadad")]),
    "forest": (["#0f2027", "#203a43", "#2c5364"], [(0.25, 0.7, "#56ab2f"), (0.75, 0.2, "#a8e063"), (0.6, 0.65, "#f7b733")]),
}


class Backdrop(QWidget):
    def __init__(self, style: str):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.style_name = style

    def paintEvent(self, _e):
        stops, blobs = WALLPAPERS[self.style_name]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h)
        for i, c in enumerate(stops):
            g.setColorAt(i / (len(stops) - 1), QColor(c))
        p.fillRect(self.rect(), g)
        r0 = min(w, h) * 0.45
        for fx, fy, c in blobs:
            rg = QRadialGradient(QPointF(w * fx, h * fy), r0)
            col = QColor(c)
            rg.setColorAt(0, col)
            col.setAlpha(0)
            rg.setColorAt(1, col)
            p.setBrush(rg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(w * fx, h * fy), r0, r0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="assets/screenshot.png")
    ap.add_argument("--theme", default="dark")
    ap.add_argument("--glass", default="balanced")
    ap.add_argument("--wallpaper", default="dusk")
    ap.add_argument("--filter", action="store_true")
    ap.add_argument("--list", default="__all__")
    ap.add_argument("--completed", action="store_true")
    ap.add_argument("--signin", action="store_true")
    ap.add_argument("--x", type=int, default=120)
    ap.add_argument("--y", type=int, default=120)
    ap.add_argument("--w", type=int, default=360)
    ap.add_argument("--h", type=int, default=560)
    ap.add_argument("--pad", type=int, default=48)
    args = ap.parse_args()

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSizeF(9.75)
    app.setFont(font)

    from gtask_widget.backend import Backend
    from gtask_widget.storage import Settings
    from gtask_widget.ui.window import TaskWidget

    pad = args.pad
    bd = Backdrop(args.wallpaper)
    bd.setGeometry(args.x - pad, args.y - pad, args.w + 2 * pad, args.h + 2 * pad)
    bd.show()

    s = Settings(x=args.x, y=args.y, width=args.w, height=args.h, theme=args.theme, glass=args.glass,
                 layer="top", filter_open=args.filter, current_list=args.list, completed_open=args.completed)
    backend = Backend(demo=True)
    if args.signin:
        backend.state = "signed_out"
    win = TaskWidget(backend, s, persist=False)
    win.show()
    backend.refresh()

    def grab():
        win.raise_()
        scr = QGuiApplication.screenAt(bd.geometry().center())
        pm = scr.grabWindow(0, bd.x() - scr.geometry().x(), bd.y() - scr.geometry().y(), bd.width(), bd.height())
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pm.save(args.out)
        print("saved", args.out, pm.size().width(), "x", pm.size().height())
        app.quit()

    QTimer.singleShot(1800, grab)
    app.exec()


if __name__ == "__main__":
    main()
