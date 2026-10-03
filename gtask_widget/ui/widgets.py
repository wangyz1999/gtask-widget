"""Small building blocks: icon buttons, the round checkbox, menus, toasts, date picker."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from PySide6.QtCore import (QDate, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextCharFormat
from PySide6.QtWidgets import (QAbstractButton, QCalendarWidget, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QToolButton, QWidget, QWidgetAction)

from ..models import next_weekday
from . import icons
from .theme import Palette


class IconButton(QAbstractButton):
    """Round, flat icon button with hover state, optional dot badge and spin."""

    def __init__(self, name: str, tooltip: str = "", size: int = 28, icon_size: int = 16, parent=None):
        super().__init__(parent)
        self.name = name
        self.pal: Palette | None = None
        self._icon_size = icon_size
        self._badge = False
        self._angle = 0.0
        self._spin = QTimer(self, interval=16, timeout=self._tick)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def set_badge(self, on: bool) -> None:
        if on != self._badge:
            self._badge = on
            self.update()

    def set_spinning(self, on: bool) -> None:
        if on and not self._spin.isActive():
            self._spin.start()
        elif not on and self._spin.isActive():
            self._spin.stop()
            self._angle = 0
            self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + 9) % 360
        self.update()

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, _e) -> None:
        if not self.pal:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isDown():
            p.setBrush(self.pal.press)
        elif self.underMouse() or self.isChecked():
            p.setBrush(self.pal.hover)
        else:
            p.setBrush(Qt.NoBrush)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        color = self.pal.accent if self.isChecked() else (self.pal.text if self.underMouse() else self.pal.text2)
        pm = icons.pixmap(self.name, color, self._icon_size)
        s = self._icon_size
        p.translate(self.width() / 2, self.height() / 2)
        if self._angle:
            p.rotate(self._angle)
        p.drawPixmap(int(-s / 2), int(-s / 2), pm)
        p.resetTransform()
        if self._badge:
            p.setBrush(self.pal.accent)
            p.drawEllipse(QRectF(self.width() - 9, 5, 5, 5))


class CheckCircle(QAbstractButton):
    """Google-Tasks-style round checkbox."""

    def __init__(self, done: bool, pal: Palette, parent=None):
        super().__init__(parent)
        self.pal = pal
        self.setCheckable(True)
        self.setChecked(done)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("Mark not done" if done else "Mark done")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, 16, 16)
        hover = self.underMouse()
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(self.pal.accent)
            p.drawEllipse(r)
            self._check(p, self.pal.on_accent)
        else:
            p.setPen(QPen(self.pal.accent if hover else self.pal.text2, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))
            if hover:
                self._check(p, self.pal.accent)

    @staticmethod
    def _check(p: QPainter, color: QColor) -> None:
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        path.moveTo(7.2, 11.2)
        path.lineTo(9.9, 13.8)
        path.lineTo(14.9, 8.6)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


class ElidedLabel(QLabel):
    """Single-line label that ends with … when it doesn't fit."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setMinimumWidth(10)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt API)
        self._full = text
        super().setText(text)
        self.setToolTip(text if len(text) > 40 else "")

    def minimumSizeHint(self) -> QSize:
        return QSize(10, super().minimumSizeHint().height())

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self._full, Qt.ElideRight, self.width())
        p.drawText(self.rect(), int(self.alignment() | Qt.AlignVCenter), text)


class Menu(QMenu):
    """QMenu with real rounded corners."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def submenu(self, title: str, icon_name: str | None = None, pal: Palette | None = None) -> "Menu":
        m = Menu(title, self)
        if icon_name and pal:
            m.setIcon(icons.icon(icon_name, pal.text2))
        self.addMenu(m)
        return m

    def item(self, text: str, fn: Callable, icon_name: str | None = None, pal: Palette | None = None,
             enabled: bool = True):
        a = self.addAction(text)
        if icon_name and pal:
            a.setIcon(icons.icon(icon_name, pal.text2))
        a.triggered.connect(lambda _=False: fn())
        a.setEnabled(enabled)
        return a

    def option(self, text: str, checked: bool, fn: Callable, pal: Palette):
        """A choice shown with a check mark icon instead of a native indicator."""
        a = self.addAction(text)
        a.setIcon(icons.icon("check" if checked else "blank", pal.accent))
        a.triggered.connect(lambda _=False: fn())
        return a


class DateMenu(Menu):
    """Quick due-date choices plus an inline calendar."""

    picked = Signal(object)  # date | None

    def __init__(self, pal: Palette, current: date | None, parent=None, allow_clear: bool = True):
        super().__init__("Due date", parent)
        today = date.today()
        self.item("Today", lambda: self.picked.emit(today), "calendar", pal)
        self.item("Tomorrow", lambda: self.picked.emit(today + timedelta(days=1)), "blank", pal)
        mon = next_weekday(today, 0)
        self.item(f"Next week ({mon.strftime('%a')}, {mon.strftime('%b')} {mon.day})",
                  lambda: self.picked.emit(mon), "blank", pal)
        self.addSeparator()
        cal = QCalendarWidget()
        cal.setGridVisible(False)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)
        cal.setFirstDayOfWeek(Qt.Sunday)
        fmt = QTextCharFormat()
        fmt.setForeground(pal.text)
        for day in (Qt.Saturday, Qt.Sunday):
            cal.setWeekdayTextFormat(day, fmt)
        head = QTextCharFormat()
        head.setForeground(pal.text3)
        cal.setHeaderTextFormat(head)
        if current:
            cal.setSelectedDate(QDate(current.year, current.month, current.day))
        for name, obj in (("chevron-left", "qt_calendar_prevmonth"), ("chevron-right", "qt_calendar_nextmonth")):
            btn = cal.findChild(QToolButton, obj)
            if btn:
                btn.setIcon(icons.icon(name, pal.text2))
        cal.setFixedSize(236, 200)
        cal.clicked.connect(lambda qd: self.picked.emit(date(qd.year(), qd.month(), qd.day())))
        wa = QWidgetAction(self)
        wa.setDefaultWidget(cal)
        self.addAction(wa)
        if allow_clear and current:
            self.addSeparator()
            self.item("Remove date", lambda: self.picked.emit(None), "close", pal)
        self.picked.connect(lambda _d: self.close())


class Toast(QWidget):
    """Small pill message at the bottom of the widget, with an optional action."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.pal: Palette | None = None
        self.setAttribute(Qt.WA_StyledBackground, False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 7, 8, 7)
        lay.setSpacing(6)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.action = QPushButton()
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.setObjectName("ghost")
        lay.addWidget(self.label, 1)
        lay.addWidget(self.action)
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self, singleShot=True, timeout=self.dismiss)
        self._cb: Callable | None = None
        self.action.clicked.connect(self._act)
        self.hide()

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def show_message(self, text: str, kind: str = "info", action: str | None = None,
                     callback: Callable | None = None, ms: int = 4500) -> None:
        self.label.setText(text)
        color = self.pal.danger if (kind == "error" and self.pal) else (self.pal.text if self.pal else None)
        if color is not None:
            self.label.setStyleSheet(f"color: rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});")
        self.action.setVisible(bool(action))
        self.action.setText(action or "")
        self._cb = callback
        was_visible = self.isVisible()
        self.reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity() if was_visible else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def _act(self) -> None:
        cb, self._cb = self._cb, None
        self.dismiss()
        if cb:
            cb()

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()

    def reposition(self) -> None:
        parent = self.parentWidget()
        w = min(parent.width() - 24, 300)
        self.setFixedWidth(w)
        self.adjustSize()
        self.move((parent.width() - w) // 2, parent.height() - self.height() - 14)

    def paintEvent(self, _e) -> None:
        if not self.pal:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(self.pal.menu)
        bg.setAlpha(245)
        p.setBrush(bg)
        p.setPen(QPen(self.pal.menu_edge, 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
