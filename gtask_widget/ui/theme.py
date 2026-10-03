"""Colors and the Qt stylesheet. Two palettes (dark glass, light glass)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette


def _c(r, g, b, a=255) -> QColor:
    return QColor(r, g, b, a)


@dataclass(frozen=True)
class Palette:
    dark: bool
    tint: QColor
    edge: QColor          # 1px glass edge
    text: QColor
    text2: QColor
    text3: QColor
    hover: QColor
    press: QColor
    divider: QColor
    field: QColor
    field_focus: QColor
    accent: QColor
    on_accent: QColor
    danger: QColor
    chip: QColor
    chip_on: QColor
    chip_on_text: QColor
    menu: QColor
    menu_edge: QColor
    scroll: QColor


DARK = Palette(
    dark=True,
    tint=_c(18, 20, 26),
    edge=_c(255, 255, 255, 34),
    text=_c(255, 255, 255, 236),
    text2=_c(255, 255, 255, 158),
    text3=_c(255, 255, 255, 105),
    hover=_c(255, 255, 255, 20),
    press=_c(255, 255, 255, 32),
    divider=_c(255, 255, 255, 22),
    field=_c(255, 255, 255, 16),
    field_focus=_c(255, 255, 255, 24),
    accent=_c(138, 180, 248),
    on_accent=_c(14, 20, 32),
    danger=_c(242, 139, 130),
    chip=_c(255, 255, 255, 16),
    chip_on=_c(138, 180, 248, 60),
    chip_on_text=_c(200, 222, 255),
    menu=_c(36, 38, 46, 250),
    menu_edge=_c(255, 255, 255, 30),
    scroll=_c(255, 255, 255, 42),
)

LIGHT = Palette(
    dark=False,
    tint=_c(248, 249, 252),
    edge=_c(255, 255, 255, 150),
    text=_c(18, 20, 26, 236),
    text2=_c(18, 20, 26, 160),
    text3=_c(18, 20, 26, 110),
    hover=_c(0, 0, 0, 14),
    press=_c(0, 0, 0, 24),
    divider=_c(0, 0, 0, 22),
    field=_c(0, 0, 0, 10),
    field_focus=_c(255, 255, 255, 170),
    accent=_c(26, 115, 232),
    on_accent=_c(255, 255, 255),
    danger=_c(197, 34, 31),
    chip=_c(0, 0, 0, 12),
    chip_on=_c(26, 115, 232, 40),
    chip_on_text=_c(16, 82, 180),
    menu=_c(250, 250, 252, 252),
    menu_edge=_c(0, 0, 0, 30),
    scroll=_c(0, 0, 0, 45),
)

# Tint opacity per glass level, (with blur, without blur).
GLASS = {
    "clear": (60, 140),
    "balanced": (120, 190),
    "solid": (190, 230),
}
GLASS_LABELS = [("clear", "Clear"), ("balanced", "Balanced"), ("solid", "Frosted")]


def system_prefers_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return True


def palette_for(theme: str) -> Palette:
    if theme == "light":
        return LIGHT
    if theme == "system":
        return DARK if system_prefers_dark() else LIGHT
    return DARK


def css(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


def blend(top: QColor, bottom: QColor) -> QColor:
    """`top` composited over an opaque `bottom`."""
    a = top.alphaF()
    return QColor(round(top.red() * a + bottom.red() * (1 - a)),
                  round(top.green() * a + bottom.green() * (1 - a)),
                  round(top.blue() * a + bottom.blue() * (1 - a)))


def dialog_stylesheet(p: Palette) -> str:
    """Inputs inside opaque popups get opaque fills (translucent fills show through)."""
    base = QColor(p.menu)
    base.setAlpha(255)
    return (f"QLineEdit, QPlainTextEdit {{ background: {css(blend(p.field, base))}; }}"
            f"QLineEdit:focus, QPlainTextEdit:focus {{ background: {css(blend(p.field_focus, base))}; }}")


def qpalette(p: Palette) -> QPalette:
    """Qt palette so natively drawn bits (menu arrows, checks, carets) match."""
    qp = QPalette()
    solid_menu = QColor(p.menu)
    solid_menu.setAlpha(255)
    for role, color in [
        (QPalette.Window, solid_menu), (QPalette.Base, solid_menu), (QPalette.AlternateBase, solid_menu),
        (QPalette.WindowText, p.text), (QPalette.Text, p.text), (QPalette.ButtonText, p.text),
        (QPalette.Button, solid_menu), (QPalette.Highlight, p.accent),
        (QPalette.HighlightedText, p.on_accent), (QPalette.ToolTipBase, solid_menu),
        (QPalette.ToolTipText, p.text), (QPalette.PlaceholderText, p.text3), (QPalette.Link, p.accent),
    ]:
        qp.setColor(role, color)
    qp.setColor(QPalette.Disabled, QPalette.Text, p.text3)
    qp.setColor(QPalette.Disabled, QPalette.WindowText, p.text3)
    return qp


def stylesheet(p: Palette) -> str:
    accent_soft = QColor(p.accent)
    accent_soft.setAlpha(140)
    accent_hover = p.accent.lighter(110) if p.dark else p.accent.darker(110)
    solid_menu = QColor(p.menu)
    solid_menu.setAlpha(255)
    return f"""
QWidget {{ color: {css(p.text)}; }}
QLabel {{ background: transparent; }}
QLabel[role="secondary"] {{ color: {css(p.text2)}; }}
QLabel[role="muted"] {{ color: {css(p.text3)}; }}
QLabel#sectionLabel {{ color: {css(p.text3)}; font-size: 8pt; font-weight: 600; letter-spacing: 0.6px; }}
QLabel#taskTitle[done="true"] {{ color: {css(p.text3)}; }}
QLabel#emptyTitle {{ font-size: 11pt; font-weight: 600; }}
QLabel#signInTitle {{ font-size: 12.5pt; font-weight: 600; }}

QLineEdit, QPlainTextEdit {{
    background: {css(p.field)}; border: 1px solid transparent; border-radius: 8px;
    padding: 6px 9px; color: {css(p.text)};
    selection-background-color: {css(accent_soft)}; selection-color: {css(p.text)};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ background: {css(p.field_focus)}; border: 1px solid {css(accent_soft)}; }}
QLineEdit#addInput {{ background: transparent; border: 1px solid transparent; padding: 7px 6px 7px 2px; }}
QLineEdit#addInput:focus {{ background: transparent; border: 1px solid transparent; }}
QLineEdit#inlineEdit {{ padding: 2px 6px; border-radius: 6px; }}

QPushButton {{ border: 1px solid transparent; background: transparent; color: {css(p.text)}; }}
QPushButton#chip {{
    background: {css(p.chip)}; color: {css(p.text2)}; border-radius: 11px;
    padding: 3px 9px; font-size: 8.5pt;
}}
QPushButton#chip:hover {{ background: {css(p.press)}; color: {css(p.text)}; }}
QPushButton#chip:checked {{ background: {css(p.chip_on)}; color: {css(p.chip_on_text)}; font-weight: 600; }}
QPushButton#primary {{
    background: {css(p.accent)}; color: {css(p.on_accent)}; border-radius: 16px;
    padding: 7px 18px; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {css(accent_hover)}; }}
QPushButton#ghost {{ color: {css(p.text2)}; border-radius: 8px; padding: 6px 12px; }}
QPushButton#ghost:hover {{ background: {css(p.hover)}; color: {css(p.text)}; }}
QPushButton#danger {{ color: {css(p.danger)}; border-radius: 8px; padding: 6px 12px; }}
QPushButton#danger:hover {{ background: {css(p.hover)}; }}
QPushButton#section {{ color: {css(p.text2)}; text-align: left; padding: 6px 10px; border-radius: 8px; font-weight: 600; font-size: 9pt; }}
QPushButton#section:hover {{ background: {css(p.hover)}; color: {css(p.text)}; }}
QPushButton#listButton {{ text-align: left; padding: 2px 4px; border-radius: 6px; font-size: 12.5pt; font-weight: 600; }}
QPushButton#listButton:hover {{ background: {css(p.hover)}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 1px 2px 0; }}
QScrollBar::handle:vertical {{ background: {css(p.scroll)}; border-radius: 3px; min-height: 28px; margin: 0 1px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QMenu {{
    background: {css(p.menu)}; border: 1px solid {css(p.menu_edge)}; border-radius: 10px;
    padding: 5px; color: {css(p.text)};
}}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 6px; background: transparent; }}
QMenu::item:selected {{ background: {css(p.hover)}; }}
QMenu::item:disabled {{ color: {css(p.text3)}; }}
QMenu::separator {{ height: 1px; background: {css(p.divider)}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::indicator {{ width: 0px; }}

QToolTip {{
    background: {css(p.menu)}; color: {css(p.text)}; border: 1px solid {css(p.menu_edge)};
    border-radius: 6px; padding: 4px 8px;
}}

QDialog#editDialog {{ background: transparent; }}

QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: transparent; }}
QCalendarWidget QToolButton {{
    color: {css(p.text)}; background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 4px 6px; font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{ background: {css(p.hover)}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
QCalendarWidget QAbstractItemView {{
    background: {css(solid_menu)}; alternate-background-color: {css(solid_menu)};
    color: {css(p.text)}; outline: 0; border: none;
    selection-background-color: {css(p.accent)}; selection-color: {css(p.on_accent)};
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {css(p.text3)}; }}
QCalendarWidget QSpinBox {{ background: {css(p.field)}; border: 1px solid transparent; border-radius: 6px; padding: 2px 4px; color: {css(p.text)}; }}
"""
