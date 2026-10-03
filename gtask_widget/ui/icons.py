"""Line icons (drawn as inline SVG so they recolor with the theme) and the app icon."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtSvg import QSvgRenderer

# 24x24 viewBox, stroked with the current color.
_PATHS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "refresh": '<path d="M20 11.5A8 8 0 1 1 17.7 6"/><path d="M20 4v5h-5"/>',
    "filter": '<path d="M4 7h16M7 12h10M10 17h4"/>',
    "more": '<circle cx="5.5" cy="12" r="1.3" fill="{c}"/><circle cx="12" cy="12" r="1.3" fill="{c}"/>'
            '<circle cx="18.5" cy="12" r="1.3" fill="{c}"/>',
    "chevron-down": '<path d="M7 10l5 5 5-5"/>',
    "chevron-right": '<path d="M10 7l5 5-5 5"/>',
    "chevron-left": '<path d="M14 7l-5 5 5 5"/>',
    "trash": '<path d="M5 7h14M10 11v6M14 11v6M6.5 7l.9 12.1A1.5 1.5 0 0 0 8.9 20.5h6.2a1.5 1.5 0 0 0 1.5-1.4L17.5 7'
             'M9.5 7V4.5h5V7"/>',
    "calendar": '<rect x="4" y="5.5" width="16" height="14.5" rx="2.5"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "sort": '<path d="M8 5v14M4.5 8.5L8 5l3.5 3.5M16 19V5M12.5 15.5L16 19l3.5-3.5"/>',
    "edit": '<path d="M4.5 19.5h4l10-10a2.1 2.1 0 0 0-4-4l-10 10v4z"/><path d="M13.5 6.5l4 4"/>',
    "subtask": '<path d="M7 4.5v8a3 3 0 0 0 3 3h9"/><path d="M15.5 12l3.5 3.5-3.5 3.5"/>',
    "external": '<path d="M14 4.5h5.5V10M19.5 4.5l-8.5 8.5"/>'
                '<path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    "list": '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><circle cx="4.75" cy="6.5" r="1" fill="{c}"/>'
            '<circle cx="4.75" cy="12" r="1" fill="{c}"/><circle cx="4.75" cy="17.5" r="1" fill="{c}"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    "power": '<path d="M12 4v8"/><path d="M7.2 7a7 7 0 1 0 9.6 0"/>',
    "logout": '<path d="M10 5H6.5A1.5 1.5 0 0 0 5 6.5v11A1.5 1.5 0 0 0 6.5 19H10"/><path d="M14.5 8l4 4-4 4M18.5 12H9.5"/>',
    "info": '<circle cx="12" cy="12" r="8"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".6" fill="{c}"/>',
    "palette": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z" fill="{c}"/>',
    "layers": '<path d="M12 4l8 4.5-8 4.5-8-4.5z"/><path d="M4 12.5l8 4.5 8-4.5"/>',
    "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
    "glass": '<rect x="4.5" y="4.5" width="15" height="15" rx="3.5"/><path d="M8 15.5l7.5-7.5M8 10.5L10.5 8"/>',
    "blank": "",
}


def _svg(name: str, color: QColor, stroke: float) -> bytes:
    c = color.name(QColor.HexRgb)
    body = _PATHS[name].replace("{c}", c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" '
            f'stroke-opacity="{color.alphaF():.3f}" fill-opacity="{color.alphaF():.3f}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def _dpr() -> float:
    app = QGuiApplication.instance()
    if app is None:
        return 1.0
    return max((s.devicePixelRatio() for s in QGuiApplication.screens()), default=1.0)


@lru_cache(maxsize=512)
def _pixmap(name: str, rgba: int, size: int, stroke: float, dpr: float) -> QPixmap:
    color = QColor.fromRgba(rgba)
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.fill(Qt.transparent)
    if _PATHS[name]:
        r = QSvgRenderer(QByteArray(_svg(name, color, stroke)))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def pixmap(name: str, color: QColor, size: int = 16, stroke: float = 1.8) -> QPixmap:
    return _pixmap(name, color.rgba(), size, stroke, _dpr())


def icon(name: str, color: QColor, size: int = 16, stroke: float = 1.8) -> QIcon:
    return QIcon(pixmap(name, color, size, stroke))


# --------------------------------------------------------------------------- app icon

def paint_app_icon(p: QPainter, size: float) -> None:
    """A glassy blue-violet tile with a check mark. Shared by the tray, window and .ico."""
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    r = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0.0, QColor(84, 148, 255))
    g.setColorAt(1.0, QColor(132, 88, 246))
    path = QPainterPath()
    path.addRoundedRect(r, s * 0.24, s * 0.24)
    p.fillPath(path, g)
    # soft top highlight
    hl = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
    hl.setColorAt(0, QColor(255, 255, 255, 70))
    hl.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, hl)
    pen = QPen(QColor(255, 255, 255), max(1.6, s * 0.105), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    check = QPainterPath(QPointF(s * 0.29, s * 0.52))
    check.lineTo(QPointF(s * 0.44, s * 0.67))
    check.lineTo(QPointF(s * 0.72, s * 0.37))
    p.drawPath(check)


def app_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_app_icon(p, size)
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(s))
    return ic
