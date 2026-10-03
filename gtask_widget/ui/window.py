"""The widget window: glass panel, header, filter bar, task list, sign-in screens."""

from __future__ import annotations

import webbrowser
from datetime import date

from PySide6.QtCore import QByteArray, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QKeySequence, QPainter, QPen,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QHBoxLayout, QLabel, QLayout,
                               QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget, QWidgetItem)

from .. import APP_NAME, REPO_URL, __version__
from ..backend import Backend
from ..models import CHIPS, Task, TaskList, arrange
from ..storage import ALL_LISTS, Settings
from . import icons, winfx
from .dialogs import EditDialog, PromptDialog
from .task_row import SubtaskInput, TaskRow
from .theme import GLASS, GLASS_LABELS, palette_for, qpalette, stylesheet
from .widgets import DateMenu, IconButton, Menu, Toast

if winfx.IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

_HIT = {  # (left, right, top, bottom) -> Win32 hit-test code
    (True, False, False, False): 10, (False, True, False, False): 11,
    (False, False, True, False): 12, (True, False, True, False): 13,
    (False, True, True, False): 14, (False, False, False, True): 15,
    (True, False, False, True): 16, (False, True, False, True): 17,
}
_EDGES = {code: edges for edges, code in _HIT.items()}
_RESIZE_CURSORS = {
    10: Qt.SizeHorCursor, 11: Qt.SizeHorCursor, 12: Qt.SizeVerCursor, 15: Qt.SizeVerCursor,
    13: Qt.SizeFDiagCursor, 17: Qt.SizeFDiagCursor, 14: Qt.SizeBDiagCursor, 16: Qt.SizeBDiagCursor,
}


class FlowLayout(QLayout):
    """Lays children left to right and wraps, so chips fit any widget width."""

    def __init__(self, spacing: int = 4):
        super().__init__()
        self._items: list = []
        self._gap = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802 (Qt API)
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return self._layout(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _layout(self, rect: QRect, dry: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line_h:
                x, y = rect.x(), y + line_h + self._gap
                line_h = 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._gap
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class Header(QWidget):
    """Empty parts of the header drag the widget around."""

    def __init__(self, win: "TaskWidget"):
        super().__init__()
        self.win = win
        self._grab: QPoint | None = None

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and not self.win.s.locked:
            self._grab = e.globalPosition().toPoint() - self.win.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self.win.move(e.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, _e) -> None:
        self._grab = None


class InfoPage(QWidget):
    """Centered icon + title + text + buttons (used for sign-in and setup)."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 10, 18, 18)
        lay.setSpacing(10)
        lay.addStretch(1)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setPixmap(icons.app_pixmap(52))
        self.title = QLabel()
        self.title.setObjectName("signInTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.body = QLabel()
        self.body.setProperty("role", "secondary")
        self.body.setAlignment(Qt.AlignCenter)
        self.body.setWordWrap(True)
        self.primary = QPushButton()
        self.primary.setObjectName("primary")
        self.primary.setCursor(Qt.PointingHandCursor)
        self.secondary = QPushButton()
        self.secondary.setObjectName("ghost")
        self.secondary.setCursor(Qt.PointingHandCursor)
        self.tertiary = QPushButton()
        self.tertiary.setObjectName("ghost")
        self.tertiary.setCursor(Qt.PointingHandCursor)
        self.foot = QLabel()
        self.foot.setProperty("role", "muted")
        self.foot.setAlignment(Qt.AlignCenter)
        self.foot.setWordWrap(True)
        f = self.foot.font()
        f.setPointSizeF(f.pointSizeF() * 0.88)
        self.foot.setFont(f)
        for w in (self.icon, self.title, self.body):
            lay.addWidget(w)
        lay.addSpacing(6)
        for b in (self.primary, self.secondary, self.tertiary):
            lay.addWidget(b, 0, Qt.AlignHCenter)
        lay.addStretch(1)
        lay.addWidget(self.foot)


class TaskWidget(QWidget):
    quitRequested = Signal()
    hiddenByUser = Signal()

    def __init__(self, backend: Backend, settings: Settings, persist: bool = True):
        super().__init__()
        self.backend = backend
        self.s = settings
        self.persist = persist
        self.pal = palette_for(settings.theme)
        self._blur_active = False
        self._query = ""
        self._subtask_parent: str | None = None
        self._editing = 0
        self._dirty = False
        self._today = date.today()
        self._menu = None
        self._hid_once = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(260, 240)
        self._set_flags()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 8, 8)
        root.setSpacing(4)
        root.addWidget(self._build_header())
        root.addWidget(self._build_filter_bar())
        self.stack = QStackedWidget()
        self.tasks_page = self._build_tasks_page()
        self.signin_page = InfoPage()
        self.setup_page = InfoPage()
        for page in (self.tasks_page, self.signin_page, self.setup_page):
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)
        self._init_info_pages()
        self.toast = Toast(self)

        self.refresh_timer = QTimer(self, timeout=self.backend.refresh)
        self.refresh_timer.start(max(1, self.s.refresh_minutes) * 60_000)
        self.minute_timer = QTimer(self, interval=60_000, timeout=self._minute_tick)
        self.minute_timer.start()
        self.save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save_geometry)
        self.resize_timer = QTimer(self, interval=12, timeout=self._resize_tick)
        self._resize = None

        QShortcut(QKeySequence.Find, self, self.open_search)
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.add_input.setFocus())
        QShortcut(QKeySequence("F5"), self, self.backend.refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, self.backend.refresh)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._escape)

        backend.changed.connect(self.render)
        backend.stateChanged.connect(self._on_state)
        backend.busyChanged.connect(self.refresh_btn.set_spinning)
        backend.message.connect(lambda text, kind: self.toast.show_message(text, kind))
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.s.theme == "system" and self.apply_theme())

        self.apply_theme()
        self._restore_geometry()
        self._on_state(backend.state)

    # ================================================================== building
    def _build_header(self) -> QWidget:
        self.header = Header(self)
        h = QHBoxLayout(self.header)
        h.setContentsMargins(0, 0, 0, 2)
        h.setSpacing(2)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.list_btn = QPushButton()
        self.list_btn.setObjectName("listButton")
        self.list_btn.setCursor(Qt.PointingHandCursor)
        self.list_btn.setLayoutDirection(Qt.RightToLeft)
        self.list_btn.setIconSize(QSize(14, 14))
        self.list_btn.clicked.connect(self._list_menu)
        self.subtitle = QLabel()
        self.subtitle.setProperty("role", "muted")
        self.subtitle.setContentsMargins(5, 0, 0, 0)
        f = self.subtitle.font()
        f.setPointSizeF(f.pointSizeF() * 0.88)
        self.subtitle.setFont(f)
        col.addWidget(self.list_btn, 0, Qt.AlignLeft | Qt.AlignAbsolute)
        col.addWidget(self.subtitle)
        h.addLayout(col, 1)
        self.filter_btn = IconButton("filter", "Filter and search (Ctrl+F)")
        self.filter_btn.setCheckable(True)
        self.filter_btn.clicked.connect(lambda: self.set_filter_open(not self.s.filter_open))
        self.refresh_btn = IconButton("refresh", "Refresh (F5)")
        self.refresh_btn.clicked.connect(self.backend.refresh)
        self.more_btn = IconButton("more", "Menu")
        self.more_btn.clicked.connect(self._more_menu)
        for b in (self.filter_btn, self.refresh_btn, self.more_btn):
            h.addWidget(b, 0, Qt.AlignTop)
        return self.header

    def _build_filter_bar(self) -> QWidget:
        self.filter_bar = QWidget()
        lay = QVBoxLayout(self.filter_bar)
        lay.setContentsMargins(2, 2, 4, 4)
        lay.setSpacing(7)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(icons.icon("search", self.pal.text3), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._set_query)
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        search_row.addWidget(self.search, 1)
        self.sort_btn = IconButton("sort", "", 30, 16)
        self.sort_btn.setCheckable(True)
        self.sort_btn.clicked.connect(self._toggle_sort)
        search_row.addWidget(self.sort_btn)
        lay.addLayout(search_row)
        chips_host = QWidget()
        flow = FlowLayout(4)
        chips_host.setLayout(flow)
        chips_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        self.chips: dict[str, QPushButton] = {}
        for key, label in CHIPS:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_chip(k))
            self.chip_group.addButton(b)
            flow.addItem(QWidgetItem(b))
            b.setParent(chips_host)
            self.chips[key] = b
        lay.addWidget(chips_host)
        return self.filter_bar

    def _build_tasks_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        add_row = QWidget()
        ar = QHBoxLayout(add_row)
        ar.setContentsMargins(10, 0, 4, 0)
        ar.setSpacing(8)
        self.add_icon = QLabel()
        self.add_icon.setFixedSize(22, 22)
        self.add_icon.setAlignment(Qt.AlignCenter)
        self.add_input = QLineEdit()
        self.add_input.setObjectName("addInput")
        self.add_input.returnPressed.connect(self._add_from_input)
        ar.addWidget(self.add_icon)
        ar.addWidget(self.add_input, 1)
        lay.addWidget(add_row)
        self.divider = QWidget()
        self.divider.setFixedHeight(1)
        lay.addWidget(self.divider)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        self.list_lay = QVBoxLayout(host)
        self.list_lay.setContentsMargins(0, 4, 2, 40)
        self.list_lay.setSpacing(0)
        self.scroll.setWidget(host)
        self.scroll.viewport().setAutoFillBackground(False)
        lay.addWidget(self.scroll, 1)
        return page

    def _init_info_pages(self) -> None:
        sp = self.signin_page
        sp.title.setText("Your tasks, on your desktop")
        sp.body.setText("Connect your Google account to see, check off and add Google Tasks right here.")
        sp.primary.setText("Connect Google account")
        sp.primary.clicked.connect(self.backend.sign_in)
        sp.secondary.setText("Copy sign-in link")
        sp.secondary.clicked.connect(self._copy_sign_in_link)
        sp.tertiary.setText("Cancel")
        sp.tertiary.clicked.connect(self.backend.cancel_sign_in)
        sp.foot.setText("Sign-in happens in your browser. This app never sees your password.")

        su = self.setup_page
        su.title.setText("One more step")
        su.body.setText("This build doesn't include a Google OAuth client. Choose the client_secret.json "
                        "you created in Google Cloud Console.")
        su.primary.setText("Choose client_secret.json…")
        su.primary.clicked.connect(self._choose_client_file)
        su.secondary.setText("How do I get one?")
        su.secondary.clicked.connect(lambda: webbrowser.open(REPO_URL + "#build-from-source"))
        su.tertiary.hide()
        su.foot.setText("The file stays on this computer.")

    # ================================================================== theme & native window
    def apply_theme(self) -> None:
        self.pal = p = palette_for(self.s.theme)
        app = QApplication.instance()
        app.setPalette(qpalette(p))
        app.setStyleSheet(stylesheet(p))
        for b in (self.filter_btn, self.refresh_btn, self.more_btn, self.sort_btn):
            b.set_palette(p)
        self.toast.set_palette(p)
        self._search_action.setIcon(icons.icon("search", p.text3))
        self.add_icon.setPixmap(icons.pixmap("plus", p.accent, 18, 2.0))
        self.list_btn.setIcon(icons.icon("chevron-down", p.text2, 14, 2.0))
        self.divider.setStyleSheet(f"background: rgba({p.divider.red()},{p.divider.green()},"
                                   f"{p.divider.blue()},{p.divider.alpha()});")
        if self.isVisible():
            winfx.style_frame(int(self.winId()), p.dark, rounded=True)
        self.update()
        self.render()

    def _set_flags(self) -> None:
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        flags |= Qt.WindowStaysOnTopHint if self.s.layer == "top" else Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self._apply_native)

    def _apply_native(self) -> None:
        if not self.isVisible():
            return
        hwnd = int(self.winId())
        self._blur_active = winfx.set_backdrop(hwnd, self.s.blur)
        winfx.style_frame(hwnd, self.pal.dark, rounded=True)
        winfx.pin_to_desktop(hwnd, self.s.layer == "desktop")
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        with_blur, without_blur = GLASS.get(self.s.glass, GLASS["balanced"])
        tint = QColor(self.pal.tint)
        tint.setAlpha(with_blur if self._blur_active else without_blur)
        if self._blur_active and not winfx.WIN11:
            radius = 0.0  # Windows 10 blurs the full rectangle
        elif self._blur_active:
            radius = 8.0  # matches the Windows 11 rounded-corner clip
        else:
            radius = 12.0
        p.setBrush(tint)
        p.setPen(QPen(self.pal.edge, 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    def nativeEvent(self, event_type, message):
        """Resize from any edge (Windows).

        Hit-testing the edges gives the right cursors; the resize itself is done
        here because Windows won't size a borderless window without a thick frame.
        """
        if winfx.IS_WINDOWS and not self.s.locked:
            et = event_type.data() if isinstance(event_type, QByteArray) else bytes(event_type)
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    left, top, right, bottom = winfx.window_rect(int(self.winId()))
                    m = round(6 * self.devicePixelRatioF())
                    key = (x < left + m, x >= right - m, y < top + m, y >= bottom - m)
                    if key in _HIT:
                        return True, _HIT[key]
                elif msg.message == 0x00A1 and msg.wParam in _EDGES:  # WM_NCLBUTTONDOWN on an edge
                    self._begin_resize(int(msg.wParam))
                    return True, 0
        return super().nativeEvent(event_type, message)

    def _begin_resize(self, code: int) -> None:
        self._resize = (code, QCursor.pos(), self.geometry())
        QApplication.setOverrideCursor(_RESIZE_CURSORS[code])
        self.resize_timer.start()

    def _resize_tick(self) -> None:
        if self._resize is None:
            self.resize_timer.stop()
            return
        if not winfx.primary_button_down():
            self.resize_timer.stop()
            self._resize = None
            QApplication.restoreOverrideCursor()
            self._save_geometry()
            return
        code, start, g = self._resize
        d = QCursor.pos() - start
        left, right, top, bottom = _EDGES[code]
        x1, y1, x2, y2 = g.x(), g.y(), g.x() + g.width(), g.y() + g.height()
        mw, mh = self.minimumWidth(), self.minimumHeight()
        if left:
            x1 = min(x1 + d.x(), x2 - mw)
        if right:
            x2 = max(x2 + d.x(), x1 + mw)
        if top:
            y1 = min(y1 + d.y(), y2 - mh)
        if bottom:
            y2 = max(y2 + d.y(), y1 + mh)
        self.setGeometry(x1, y1, x2 - x1, y2 - y1)

    # ================================================================== geometry
    def _restore_geometry(self) -> None:
        w, h = max(260, self.s.width), max(240, self.s.height)
        x, y = self.s.x, self.s.y
        if x is None or y is None or QGuiApplication.screenAt(QPoint(x + w // 2, y + 16)) is None:
            area = QGuiApplication.primaryScreen().availableGeometry()
            x, y = area.right() - w - 28, area.top() + 28
        self.setGeometry(x, y, w, h)

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        self.save_timer.start()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.save_timer.start()
        if self.toast.isVisible():
            self.toast.reposition()

    def _save_geometry(self) -> None:
        g = self.geometry()
        self.s.x, self.s.y, self.s.width, self.s.height = g.x(), g.y(), g.width(), g.height()
        self._save()

    def _save(self) -> None:
        if self.persist:
            self.s.save()

    # ================================================================== state
    def _on_state(self, state: str) -> None:
        if state == "ready":
            self.stack.setCurrentWidget(self.tasks_page)
        elif state == "no_client":
            self.stack.setCurrentWidget(self.setup_page)
        else:
            self.stack.setCurrentWidget(self.signin_page)
            waiting = state == "signing_in"
            sp = self.signin_page
            sp.primary.setVisible(not waiting)
            sp.secondary.setVisible(waiting)
            sp.tertiary.setVisible(waiting)
            sp.body.setText("Finish signing in in your browser, then come back here." if waiting else
                            "Connect your Google account to see, check off and add Google Tasks right here.")
        ready = state == "ready"
        self.filter_btn.setVisible(ready)
        self.refresh_btn.setVisible(ready)
        self.filter_bar.setVisible(ready and self.s.filter_open)
        self.render()

    def _copy_sign_in_link(self) -> None:
        if self.backend.sign_in_url:
            QGuiApplication.clipboard().setText(self.backend.sign_in_url)
            self.toast.show_message("Link copied. Paste it into your browser.")

    def _choose_client_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose OAuth client file", "", "JSON files (*.json)")
        if path:
            self.backend.install_client(path)

    # ================================================================== filters
    def set_filter_open(self, open_: bool) -> None:
        self.s.filter_open = open_
        self.filter_bar.setVisible(open_ and self.backend.state == "ready")
        if not open_ and self._query:
            self.search.clear()
        self._save()
        self._update_header()
        if open_:
            self.search.setFocus()

    def open_search(self) -> None:
        if not self.s.filter_open:
            self.set_filter_open(True)
        self.search.setFocus()
        self.search.selectAll()

    def set_chip(self, key: str) -> None:
        self.s.chip = key
        self._save()
        self.render()

    def _set_query(self, text: str) -> None:
        self._query = text
        self.render()

    def _toggle_sort(self) -> None:
        self.s.sort = "my" if self.s.sort == "date" else "date"
        self._save()
        self.render()

    def _filters_active(self) -> bool:
        return self.s.chip != "all" or bool(self._query.strip())

    def _escape(self) -> None:
        if self.search.hasFocus() and self.search.text():
            self.search.clear()
        elif self.s.filter_open:
            self.set_filter_open(False)
        elif self.add_input.hasFocus():
            self.add_input.clear()
            self.add_input.clearFocus()

    # ================================================================== rendering
    def _visible_lists(self) -> list[TaskList]:
        if self.s.current_list != ALL_LISTS:
            tl = [l for l in self.backend.lists if l.id == self.s.current_list]
            if tl:
                return tl
        return list(self.backend.lists)

    def _target_list(self) -> TaskList | None:
        lists = self._visible_lists()
        return lists[0] if lists else None

    def _update_header(self) -> None:
        state = self.backend.state
        if state != "ready":
            self.list_btn.setText(APP_NAME)
            self.list_btn.setIcon(icons.icon("blank", self.pal.text2, 14))
            self.list_btn.setEnabled(False)
            self.subtitle.setText(self._today_text())
            return
        self.list_btn.setEnabled(True)
        self.list_btn.setIcon(icons.icon("chevron-down", self.pal.text2, 14, 2.0))
        lists = self._visible_lists()
        all_mode = self.s.current_list == ALL_LISTS or len(lists) != 1
        self.list_btn.setText("All lists" if all_mode and len(self.backend.lists) > 1
                              else (lists[0].title if lists else "Tasks"))
        n_open = sum(1 for l in lists for t in self.backend.tasks.get(l.id, []) if not t.done)
        bits = [self._today_text(), f"{n_open} open"]
        if self.backend.offline:
            bits.append("offline")
        self.subtitle.setText("  ·  ".join(bits))
        target = self._target_list()
        self.add_input.setPlaceholderText(
            f"Add a task to {target.title}" if target and all_mode and len(self.backend.lists) > 1
            else "Add a task")
        self.filter_btn.set_badge(self._filters_active())
        self.filter_btn.setChecked(self.s.filter_open)
        for key, b in self.chips.items():
            b.setChecked(key == self.s.chip)
        self.sort_btn.setChecked(self.s.sort == "date")
        self.sort_btn.setToolTip("Sorted by due date (click for your order)" if self.s.sort == "date"
                                 else "Your order (click to sort by due date)")

    @staticmethod
    def _today_text() -> str:
        d = date.today()
        return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}"

    def _set_editing(self, on: bool) -> None:
        self._editing = max(0, self._editing + (1 if on else -1))
        if not self._editing and self._dirty:
            QTimer.singleShot(0, self.render)

    def render(self) -> None:
        if self._editing:
            self._dirty = True
            return
        self._dirty = False
        self._update_header()
        if self.backend.state != "ready":
            return
        bar = self.scroll.verticalScrollBar()
        pos = bar.value()
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = date.today()
        lists = self._visible_lists()
        multi = len(lists) > 1
        any_rows = False
        completed: list[tuple[Task, str | None]] = []
        for tl in lists:
            rows, done = arrange(self.backend.tasks.get(tl.id, []), chip=self.s.chip,
                                 query=self._query, sort=self.s.sort, today=today)
            completed += [(t, tl.title if multi else None) for t in done]
            if not rows:
                continue
            any_rows = True
            if multi:
                self.list_lay.addWidget(self._section(tl, len(rows)))
            for task, depth in rows:
                self.list_lay.addWidget(self._row(task, depth, today))
                if task.id == self._subtask_parent:
                    self.list_lay.addWidget(self._subtask_input(task, depth + 1))

        if not any_rows:
            self.list_lay.addWidget(self._empty_state(bool(self.backend.lists)))

        if completed:
            completed.sort(key=lambda x: x[0].completed, reverse=True)
            btn = QPushButton(f"  Completed  ({len(completed)})")
            btn.setObjectName("section")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(icons.icon("chevron-down" if self.s.completed_open else "chevron-right",
                                   self.pal.text2, 14, 2.0))
            btn.clicked.connect(self._toggle_completed)
            self.list_lay.addSpacing(6)
            self.list_lay.addWidget(btn)
            if self.s.completed_open:
                for task, list_name in completed[:200]:
                    self.list_lay.addWidget(self._row(task, 0, today, list_name))
        self.list_lay.addStretch(1)
        QTimer.singleShot(0, lambda: bar.setValue(pos))

    def _section(self, tl: TaskList, count: int) -> QWidget:
        b = QPushButton(f"{tl.title.upper()}   {count}")
        b.setObjectName("section")
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(f"Show only {tl.title}")
        f = b.font()
        f.setPointSizeF(f.pointSizeF() * 0.85)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
        b.setFont(f)
        b.setStyleSheet("padding-top: 10px;")
        b.clicked.connect(lambda: self.select_list(tl.id))
        return b

    def _empty_state(self, has_lists: bool) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 36, 10, 10)
        lay.setSpacing(4)
        t = QLabel("No matching tasks" if self._filters_active() else "All caught up")
        t.setObjectName("emptyTitle")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Try a different filter or search." if self._filters_active()
                   else ("Add a task above to get started." if has_lists else "Loading your lists…"))
        s.setProperty("role", "muted")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(s)
        return w

    def _row(self, task: Task, depth: int, today: date, list_name: str | None = None) -> TaskRow:
        r = TaskRow(task, depth, self.pal, today, list_name)
        r.toggled.connect(self._toggle)
        r.renamed.connect(lambda t, title: self.backend.edit_task(t, title=title))
        r.deleteRequested.connect(self._delete)
        r.dueRequested.connect(self._due_menu)
        r.menuRequested.connect(self._task_menu)
        r.editingChanged.connect(self._set_editing)
        return r

    def _subtask_input(self, parent: Task, depth: int) -> QWidget:
        w = SubtaskInput(depth, self.pal)

        def submit(text: str):
            self._subtask_parent = None
            self.backend.add_task(parent.list_id, text, parent=parent.id)

        def cancel():
            self._subtask_parent = None
            QTimer.singleShot(0, self.render)

        w.submitted.connect(submit)
        w.cancelled.connect(cancel)
        QTimer.singleShot(0, w.focus)
        return w

    def _toggle_completed(self) -> None:
        self.s.completed_open = not self.s.completed_open
        self._save()
        self.render()

    def _minute_tick(self) -> None:
        if date.today() != self._today:
            self._today = date.today()
            self.render()
        elif self.backend.state == "ready":
            self._update_header()
        if self.isVisible() and self.s.layer == "desktop" and not winfx.is_pinned(int(self.winId())):
            winfx.pin_to_desktop(int(self.winId()), True)  # Explorer restarted

    # ================================================================== actions
    def _add_from_input(self) -> None:
        text = self.add_input.text().strip()
        target = self._target_list()
        if not text:
            return
        if target is None:
            self.toast.show_message("No task list yet. Try refreshing.", "error")
            return
        due = date.today() if self.s.chip == "today" else None
        self.backend.add_task(target.id, text, due=due)
        self.add_input.clear()
        if self.s.chip in ("upcoming", "overdue") or (self._query and self._query.casefold() not in text.casefold()):
            self.toast.show_message(f"Added to {target.title}")

    def _toggle(self, task: Task, done: bool) -> None:
        # let the check mark show for a moment before the row moves
        QTimer.singleShot(220, lambda: self.backend.set_done(task, done))

    def _delete(self, task: Task) -> None:
        self.backend.delete_task(task)
        self.toast.show_message("Task deleted", action="Undo", callback=lambda: self.backend.restore_task(task))

    def _due_menu(self, task: Task, pos: QPoint) -> None:
        m = DateMenu(self.pal, task.due, self)
        m.picked.connect(lambda d: self.backend.set_due(task, d))
        self._menu = m
        m.popup(pos)

    def _task_menu(self, task: Task, pos: QPoint) -> None:
        p = self.pal
        m = Menu(parent=self)
        m.item("Edit details…", lambda: self.edit_task(task), "edit", p)
        if not task.done:
            dm = DateMenu(p, task.due, m)
            dm.setIcon(icons.icon("calendar", p.text2))
            dm.picked.connect(lambda d: self.backend.set_due(task, d))
            m.addMenu(dm)
            if not task.parent:
                m.item("Add subtask", lambda: self._start_subtask(task), "subtask", p)
            m.item("Rename", lambda: self._rename(task), "blank", p)
        m.item("Mark not done" if task.done else "Mark done",
               lambda: self.backend.set_done(task, not task.done), "check", p)
        if task.web_link:
            m.item("Open in Google Tasks", lambda: webbrowser.open(task.web_link), "external", p)
        m.addSeparator()
        m.item("Delete", lambda: self._delete(task), "trash", p)
        self._menu = m
        m.popup(pos)

    def _rename(self, task: Task) -> None:
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, TaskRow) and w.task.id == task.id:
                w.start_rename()
                return

    def _start_subtask(self, task: Task) -> None:
        self._subtask_parent = task.id
        self.render()

    def edit_task(self, task: Task) -> None:
        dlg = EditDialog(task, self.pal, self.backend.list_title(task.list_id), self)
        dlg.center_on(self)
        if not dlg.exec():
            return
        if dlg.deleted:
            self._delete(task)
            return
        title, notes, due = dlg.values
        self.backend.edit_task(task, title=title or task.title, notes=notes, due=due)

    def select_list(self, list_id: str) -> None:
        self.s.current_list = list_id
        self._save()
        self.scroll.verticalScrollBar().setValue(0)
        self.render()

    def _new_list(self) -> None:
        dlg = PromptDialog("New list", "List name", "Create", self.pal, self)
        dlg.center_on(self)
        if dlg.exec() and dlg.text:
            self.backend.add_list(dlg.text, on_done=lambda tl: self.select_list(tl.id))

    # ================================================================== menus
    def _list_menu(self) -> None:
        p = self.pal
        m = Menu(parent=self)
        if len(self.backend.lists) > 1:
            m.option("All lists", self.s.current_list == ALL_LISTS, lambda: self.select_list(ALL_LISTS), p)
            m.addSeparator()
        current = self._visible_lists()
        single = current[0].id if len(current) == 1 else None
        for tl in self.backend.lists:
            m.option(tl.title, tl.id == single, lambda lid=tl.id: self.select_list(lid), p)
        m.addSeparator()
        m.item("New list…", self._new_list, "plus", p)
        self._menu = m
        m.popup(self.list_btn.mapToGlobal(QPoint(0, self.list_btn.height() + 2)))

    def _more_menu(self) -> None:
        p, s = self.pal, self.s
        m = Menu(parent=self)

        theme = m.submenu("Theme", "palette", p)
        for key, label in (("dark", "Dark"), ("light", "Light"), ("system", "Match Windows")):
            theme.option(label, s.theme == key, lambda k=key: self._set("theme", k, theme=True), p)

        glass = m.submenu("Glass", "glass", p)
        for key, label in GLASS_LABELS:
            glass.option(label, s.glass == key, lambda k=key: self._set("glass", k), p)
        if winfx.IS_WINDOWS:
            glass.addSeparator()
            glass.option("Blur background", s.blur, lambda: self._set("blur", not s.blur, native=True), p)

        place = m.submenu("Placement", "layers", p)
        place.option("On desktop", s.layer == "desktop", lambda: self.set_layer("desktop"), p)
        place.option("Always on top", s.layer == "top", lambda: self.set_layer("top"), p)
        place.addSeparator()
        place.option("Lock position", s.locked, lambda: self._set("locked", not s.locked), p)
        place.item("Reset position", self._reset_position, "blank", p)

        every = m.submenu("Refresh every", "clock", p)
        for mins in (1, 5, 15, 30):
            every.option(f"{mins} minute{'s' if mins > 1 else ''}", s.refresh_minutes == mins,
                         lambda n=mins: self._set_refresh(n), p)

        if winfx.startup_supported():
            on = winfx.startup_enabled()
            m.option("Start with Windows", on, lambda: self._set_startup(not on), p)
        m.addSeparator()
        if self.backend.state == "ready":
            m.item("Open Google Tasks", lambda: webbrowser.open("https://tasks.google.com/"), "external", p)
        m.item("Hide widget", self._hide, "blank", p)
        if self.backend.state == "ready" and not self.backend.demo:
            m.item("Sign out", self.backend.sign_out, "logout", p)
        m.addSeparator()
        m.item(f"About {APP_NAME} {__version__}", lambda: webbrowser.open(REPO_URL), "info", p)
        m.item("Quit", self.quitRequested.emit, "power", p)
        self._menu = m
        m.popup(self.more_btn.mapToGlobal(QPoint(self.more_btn.width() - m.sizeHint().width(),
                                                 self.more_btn.height() + 2)))

    def _set(self, key: str, value, theme: bool = False, native: bool = False) -> None:
        setattr(self.s, key, value)
        self._save()
        if theme:
            self.apply_theme()
        if native:
            self._apply_native()
        self.update()

    def _set_refresh(self, minutes: int) -> None:
        self._set("refresh_minutes", minutes)
        self.refresh_timer.start(minutes * 60_000)

    def _set_startup(self, on: bool) -> None:
        try:
            winfx.set_startup(on)
        except OSError as e:
            self.toast.show_message(f"Couldn't change startup setting: {e}", "error")

    def set_layer(self, layer: str) -> None:
        if layer == self.s.layer:
            return
        self.s.layer = layer
        self._save()
        geo, visible = self.geometry(), self.isVisible()
        self._set_flags()
        self.setGeometry(geo)
        if visible:
            self.show()

    def _reset_position(self) -> None:
        self.s.x = self.s.y = None
        self._restore_geometry()

    def _hide(self) -> None:
        self.hide()
        self.hiddenByUser.emit()

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
