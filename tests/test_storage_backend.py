import sys
from datetime import date

import pytest

from gtask_widget.storage import Settings, protect, read_secure_json, unprotect, write_secure_json


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_roundtrip_and_ciphertext(tmp_path):
    blob = protect(b"secret refresh token")
    assert b"secret" not in blob and unprotect(blob) == b"secret refresh token"
    write_secure_json(tmp_path / "x.bin", {"a": 1})
    assert b'"a"' not in (tmp_path / "x.bin").read_bytes()
    assert read_secure_json(tmp_path / "x.bin") == {"a": 1}


def test_settings_roundtrip_ignores_junk():
    s = Settings(theme="light", width=400, x=10, y=20)
    s.save()
    Settings.path().write_text(Settings.path().read_text().replace('"glass": "balanced"', '"glass": 5'))
    loaded = Settings.load()
    assert (loaded.theme, loaded.width, loaded.x) == ("light", 400, 10)
    assert loaded.glass == "balanced"  # wrong type falls back to the default


def test_backend_demo_flow():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest

    from gtask_widget.backend import Backend

    app = QApplication.instance() or QApplication([])

    def settle(timeout_ms=3000):
        for _ in range(timeout_ms // 20):
            QTest.qWait(20)
            if not be.busy:
                return

    be = Backend(demo=True)
    be.refresh()
    settle()
    assert be.lists and be.tasks["mine"]

    be.add_task("mine", "New one", due=date.today())
    added = next(t for t in be.tasks["mine"] if t.title == "New one")
    assert added.id.startswith("local-")  # shown instantly
    settle()
    added = next(t for t in be.tasks["mine"] if t.title == "New one")
    assert not added.id.startswith("local-")  # replaced by the server copy

    be.set_done(added, True)
    settle()
    assert next(t for t in be.tasks["mine"] if t.id == added.id).done

    be.delete_task(added)
    settle()
    assert all(t.id != added.id for t in be.tasks["mine"])
    be.shutdown()
    assert app is not None
