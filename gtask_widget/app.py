"""Entry point: single-instance guard, tray icon, and the widget window."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import APP_ID, APP_NAME, __version__
from .storage import Settings, data_dir


def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="gtask-widget", description=f"{APP_NAME}: Google Tasks on your desktop.")
    ap.add_argument("--demo", action="store_true", help="run with sample tasks, no Google account needed")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return ap.parse_args(argv)


def _setup_logging(demo: bool) -> None:
    handlers: list[logging.Handler] = []
    if not demo:
        try:
            handlers.append(RotatingFileHandler(data_dir() / "gtask-widget.log", maxBytes=256_000,
                                                backupCount=1, encoding="utf-8"))
        except OSError:
            pass
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"{APP_ID}-{user}"


def _notify_running_instance(name: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.demo:
        os.environ.setdefault("GTASK_WIDGET_HOME", tempfile.mkdtemp(prefix="gtask-demo-"))
    _setup_logging(args.demo)
    log = logging.getLogger("gtask_widget")

    from .ui import winfx
    winfx.set_app_id(f"wangyz1999.{APP_ID}")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setPointSizeF(9.75)
    app.setFont(font)

    server = None
    if not args.demo:
        name = _server_name()
        if _notify_running_instance(name):
            log.info("Already running; asked the other instance to show itself")
            return 0
        QLocalServer.removeServer(name)
        server = QLocalServer()
        server.listen(name)

    from .backend import Backend
    from .ui import icons
    from .ui.widgets import Menu
    from .ui.window import TaskWidget

    settings = Settings() if args.demo else Settings.load()
    backend = Backend(demo=args.demo)
    win = TaskWidget(backend, settings, persist=not args.demo)

    tray = QSystemTrayIcon(icons.app_icon())
    tray.setToolTip(APP_NAME)

    def quit_app():
        win._save_geometry()
        backend.shutdown()
        tray.hide()
        app.quit()

    tray_menu = Menu()
    toggle_action = tray_menu.item("Hide widget", win.toggle_visible, "blank", win.pal)
    refresh_action = tray_menu.item("Refresh", backend.refresh, "refresh", win.pal)
    tray_menu.addSeparator()
    tray_menu.item("Quit", quit_app, "power", win.pal)

    def update_tray_menu():
        toggle_action.setText("Hide widget" if win.isVisible() else "Show widget")
        refresh_action.setEnabled(backend.state == "ready")

    tray_menu.aboutToShow.connect(update_tray_menu)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(lambda reason: win.toggle_visible()
                           if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    def hidden_hint():
        if tray.isVisible():
            tray.showMessage(APP_NAME, "Still running here. Click the tray icon to bring the widget back.",
                             icons.app_icon(), 4000)

    win.hiddenByUser.connect(hidden_hint)
    win.quitRequested.connect(quit_app)

    if server is not None:
        def on_connection():
            conn = server.nextPendingConnection()
            if conn:
                conn.readyRead.connect(lambda: (conn.readAll(), win.show(), win.raise_(), win.activateWindow()))
        server.newConnection.connect(on_connection)

    win.show()
    QTimer.singleShot(300, backend.refresh)
    log.info("%s %s started", APP_NAME, __version__)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
