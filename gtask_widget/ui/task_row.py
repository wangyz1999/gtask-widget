"""One task in the list: round checkbox, title, due date / notes line, hover actions."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..models import Task, due_label
from . import icons
from .theme import Palette, css
from .widgets import CheckCircle, ElidedLabel, IconButton

INDENT = 26


class TaskRow(QWidget):
    toggled = Signal(object, bool)
    renamed = Signal(object, str)
    deleteRequested = Signal(object)
    dueRequested = Signal(object, QPoint)
    menuRequested = Signal(object, QPoint)
    editingChanged = Signal(bool)

    def __init__(self, task: Task, depth: int, pal: Palette, today: date,
                 list_name: str | None = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.pal = pal
        self._hover = False
        self._editor: QLineEdit | None = None
        self.setAttribute(Qt.WA_Hover)

        row = QHBoxLayout(self)
        row.setContentsMargins(8 + depth * INDENT, 5, 4, 5)
        row.setSpacing(8)

        self.check = CheckCircle(task.done, pal)
        self.check.clicked.connect(lambda: self.toggled.emit(self.task, self.check.isChecked()))
        row.addWidget(self.check, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setContentsMargins(0, 1, 0, 0)
        col.setSpacing(1)
        self.col = col
        self.title = QLabel(task.title or "Untitled")
        self.title.setObjectName("taskTitle")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.NoTextInteraction)
        self.title.setProperty("done", task.done)
        if task.done:
            f = self.title.font()
            f.setStrikeOut(True)
            self.title.setFont(f)
        col.addWidget(self.title)

        meta = self._meta(task, pal, today, list_name)
        if meta is not None:
            col.addWidget(meta)
        row.addLayout(col, 1)

        self.actions = QWidget()
        act = QHBoxLayout(self.actions)
        act.setContentsMargins(0, 0, 0, 0)
        act.setSpacing(0)
        self._buttons = []
        if not task.done:
            due_btn = IconButton("calendar", "Set due date", 24, 14)
            due_btn.clicked.connect(lambda: self.dueRequested.emit(
                self.task, due_btn.mapToGlobal(QPoint(0, due_btn.height()))))
            self._buttons.append(due_btn)
        del_btn = IconButton("trash", "Delete", 24, 14)
        del_btn.clicked.connect(lambda: self.deleteRequested.emit(self.task))
        self._buttons.append(del_btn)
        for b in self._buttons:
            b.set_palette(pal)
            b.setVisible(False)
            act.addWidget(b)
        self.actions.setFixedWidth(48)
        row.addWidget(self.actions, 0, Qt.AlignTop)

    # -- pieces ------------------------------------------------------------
    def _meta(self, task: Task, pal: Palette, today: date, list_name: str | None) -> QWidget | None:
        notes = task.notes.strip().splitlines()[0] if task.notes.strip() else ""
        if task.done:
            due = None
        else:
            due = task.due
        if not (due or notes or list_name):
            return None
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        small = self.font()
        small.setPointSizeF(small.pointSizeF() * 0.86)
        if due:
            text, kind = due_label(due, today)
            color = {"overdue": pal.danger, "today": pal.accent}.get(kind, pal.text2)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("calendar", color, 12, 2.0))
            lb = QLabel(text)
            lb.setFont(small)
            lb.setStyleSheet(f"color: {css(color)};")
            lay.addWidget(ic)
            lay.addWidget(lb)
        extra = " · ".join(x for x in (list_name, notes) if x)
        if extra:
            if due:
                dot = QLabel("·")
                dot.setProperty("role", "muted")
                lay.addWidget(dot)
            n = ElidedLabel(extra)
            n.setFont(small)
            n.setProperty("role", "muted")
            lay.addWidget(n, 1)
        else:
            lay.addStretch(1)
        return w

    # -- hover / paint -------------------------------------------------------
    def event(self, e):
        if e.type() == QEvent.HoverEnter:
            self._set_hover(True)
        elif e.type() == QEvent.HoverLeave:
            self._set_hover(False)
        return super().event(e)

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        for b in self._buttons:
            b.setVisible(on)
        self.update()

    def paintEvent(self, _e) -> None:
        if self._hover or self._editor:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(self.pal.hover)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 0, -2, 0), 8, 8)

    # -- interaction ---------------------------------------------------------
    def contextMenuEvent(self, e) -> None:
        self.menuRequested.emit(self.task, e.globalPos())

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and not self.task.done:
            self.start_rename()

    def start_rename(self) -> None:
        if self._editor:
            return
        ed = QLineEdit(self.task.title)
        ed.setObjectName("inlineEdit")
        ed.installEventFilter(self)
        self._editor = ed
        self.title.hide()
        self.col.insertWidget(0, ed)
        ed.setFocus()
        ed.selectAll()
        ed.editingFinished.connect(self._finish_rename)
        self.editingChanged.emit(True)

    def _finish_rename(self, commit: bool = True) -> None:
        ed, self._editor = self._editor, None
        if ed is None:
            return
        text = ed.text().strip()
        ed.removeEventFilter(self)
        ed.deleteLater()
        self.title.show()
        if commit and text and text != self.task.title:
            self.title.setText(text)
            self.renamed.emit(self.task, text)
        self.editingChanged.emit(False)

    def eventFilter(self, obj, e):
        if obj is self._editor and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            self._finish_rename(commit=False)
            return True
        return super().eventFilter(obj, e)


class SubtaskInput(QWidget):
    """Inline field for adding a subtask under its parent."""

    submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, depth: int, pal: Palette, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8 + depth * INDENT + 30, 3, 10, 3)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Subtask title, then Enter")
        self.edit.installEventFilter(self)
        self.edit.returnPressed.connect(self._submit)
        lay.addWidget(self.edit)
        self._done = False

    def focus(self) -> None:
        self.edit.setFocus()

    def _submit(self) -> None:
        text = self.edit.text().strip()
        if text:
            self._done = True
            self.submitted.emit(text)

    def eventFilter(self, obj, e):
        if obj is self.edit:
            if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                self._done = True
                self.cancelled.emit()
                return True
            if e.type() == QEvent.FocusOut and not self._done and not self.edit.text().strip():
                self._done = True
                self.cancelled.emit()
        return super().eventFilter(obj, e)
