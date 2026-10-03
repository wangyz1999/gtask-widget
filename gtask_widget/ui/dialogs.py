"""Frameless glass dialogs: edit task details, and a one-line prompt."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..models import Task
from . import icons
from .theme import Palette, dialog_stylesheet
from .widgets import DateMenu, IconButton


class GlassDialog(QDialog):
    def __init__(self, pal: Palette, parent: QWidget | None = None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.pal = pal
        self.setObjectName("editDialog")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(dialog_stylesheet(pal))
        self._drag: QPoint | None = None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self.pal.menu)
        p.setPen(QPen(self.pal.menu_edge, 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

    def center_on(self, w: QWidget) -> None:
        self.adjustSize()
        g = w.frameGeometry()
        self.move(g.center().x() - self.width() // 2, max(g.top() + 40, g.center().y() - self.height() // 2))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None


class EditDialog(GlassDialog):
    """Edit title, notes and due date. After exec(): .deleted or .values."""

    def __init__(self, task: Task, pal: Palette, list_name: str, parent: QWidget | None = None):
        super().__init__(pal, parent)
        self.task = task
        self.due: date | None = task.due
        self.deleted = False
        self.setFixedWidth(340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        cap = QLabel(list_name.upper() if list_name else "TASK")
        cap.setObjectName("sectionLabel")
        top.addWidget(cap, 1)
        close = IconButton("close", "Close (Esc)", 26, 14)
        close.set_palette(pal)
        close.clicked.connect(self.reject)
        top.addWidget(close)
        lay.addLayout(top)

        self.title = QLineEdit(task.title)
        self.title.setPlaceholderText("Title")
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() * 1.12)
        self.title.setFont(f)
        lay.addWidget(self.title)

        self.notes = QPlainTextEdit(task.notes)
        self.notes.setPlaceholderText("Add details")
        self.notes.setFixedHeight(96)
        self.notes.setTabChangesFocus(True)
        lay.addWidget(self.notes)

        due_row = QHBoxLayout()
        due_row.setSpacing(4)
        self.due_btn = QPushButton()
        self.due_btn.setObjectName("ghost")
        self.due_btn.setCursor(Qt.PointingHandCursor)
        self.due_btn.setIcon(icons.icon("calendar", pal.text2))
        self.due_btn.clicked.connect(self._pick_due)
        due_row.addWidget(self.due_btn)
        self.clear_due = IconButton("close", "Remove date", 26, 12)
        self.clear_due.set_palette(pal)
        self.clear_due.clicked.connect(lambda: self._set_due(None))
        due_row.addWidget(self.clear_due)
        due_row.addStretch(1)
        lay.addLayout(due_row)
        self._set_due(task.due)

        btns = QHBoxLayout()
        delete = QPushButton("Delete")
        delete.setObjectName("danger")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(self._delete)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btns.addWidget(delete)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addSpacing(4)
        lay.addLayout(btns)
        self.title.returnPressed.connect(self.accept)

    def _set_due(self, d: date | None) -> None:
        self.due = d
        self.due_btn.setText(f"  {d.strftime('%a')}, {d.strftime('%b')} {d.day}, {d.year}" if d else "  Add due date")
        self.clear_due.setVisible(d is not None)

    def _pick_due(self) -> None:
        m = DateMenu(self.pal, self.due, self, allow_clear=False)
        m.picked.connect(self._set_due)
        m.exec(self.due_btn.mapToGlobal(QPoint(0, self.due_btn.height())))

    def _delete(self) -> None:
        self.deleted = True
        self.accept()

    @property
    def values(self) -> tuple[str, str, date | None]:
        return self.title.text().strip(), self.notes.toPlainText(), self.due


class PromptDialog(GlassDialog):
    """Ask for one line of text (e.g. a new list name)."""

    def __init__(self, title: str, placeholder: str, ok_text: str, pal: Palette, parent: QWidget | None = None):
        super().__init__(pal, parent)
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        head = QLabel(title)
        head.setObjectName("emptyTitle")
        lay.addWidget(head)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(ok_text)
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self.edit.returnPressed.connect(self.accept)

    @property
    def text(self) -> str:
        return self.edit.text().strip()
