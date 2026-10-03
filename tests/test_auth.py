import base64
import hashlib
import json
import threading
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from gtask_widget import auth as auth_mod
from gtask_widget.auth import (Auth, AuthError, ClientConfig, SignInCancelled, TokenStore,
                               install_client_config, load_client_config)

from .fake_google import FakeGoogle


@pytest.fixture
def google(monkeypatch):
    g = FakeGoogle()
    monkeypatch.setattr(auth_mod, "TOKEN_URI", g.url + "/token")
    yield g
    g.close()


def browser_that_consents(code="the-code", tamper_state=False, error=None):
    """Simulates the user approving access: follows the redirect back to the app."""
    seen = {}

    def open_browser(url):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        seen.update(q)
        params = {"state": "wrong" if tamper_state else q["state"]}
        params.update({"error": error} if error else {"code": code})

        def visit():
            with urllib.request.urlopen(q["redirect_uri"] + "/?" + urlencode(params), timeout=5) as r:
                seen["page"] = r.read().decode()

        threading.Thread(target=visit, daemon=True).start()
        return True

    return open_browser, seen


def test_sign_in_with_pkce(google, tmp_path):
    a = Auth(ClientConfig("cid", "secret"), TokenStore(tmp_path / "t.bin"))
    browser, seen = browser_that_consents()
    creds = a.sign_in(open_browser=browser, timeout=10)
    assert creds.refresh_token == "refresh-1" and a.signed_in
    # authorization request
    assert seen["redirect_uri"].startswith("http://127.0.0.1:")
    assert seen["code_challenge_method"] == "S256"
    assert seen["access_type"] == "offline" and seen["scope"] == auth_mod.SCOPE
    # token exchange proves possession of the PKCE verifier
    form = google.token_requests[-1]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=")
    assert challenge.decode() == seen["code_challenge"]
    assert form["code"] == "the-code" and form["redirect_uri"] == seen["redirect_uri"]
    assert "signed in" in seen["page"]
    # persisted, encrypted at rest on Windows
    assert TokenStore(tmp_path / "t.bin").load().refresh_token == "refresh-1"


def test_state_mismatch_rejected(google, tmp_path):
    a = Auth(ClientConfig("cid", None), TokenStore(tmp_path / "t.bin"))
    browser, _ = browser_that_consents(tamper_state=True)
    with pytest.raises(AuthError):
        a.sign_in(open_browser=browser, timeout=10)
    assert not google.token_requests


def test_access_denied(google, tmp_path):
    a = Auth(ClientConfig("cid", None), TokenStore(tmp_path / "t.bin"))
    browser, _ = browser_that_consents(error="access_denied")
    with pytest.raises(AuthError, match="not granted"):
        a.sign_in(open_browser=browser, timeout=10)


def test_cancel(tmp_path):
    a = Auth(ClientConfig("cid", None), TokenStore(tmp_path / "t.bin"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(SignInCancelled):
        a.sign_in(cancel=cancel, open_browser=lambda url: True, timeout=10)


def test_client_config_sources(tmp_path, monkeypatch):
    f = tmp_path / "client.json"
    f.write_text(json.dumps({"installed": {"client_id": "abc", "client_secret": "s"}}))
    monkeypatch.setenv("GTASK_WIDGET_CLIENT_SECRETS", str(f))
    cfg = load_client_config()
    assert (cfg.client_id, cfg.client_secret) == ("abc", "s")

    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(AuthError):
        install_client_config(bad)
    cfg = install_client_config(f)
    assert cfg.client_id == "abc"
