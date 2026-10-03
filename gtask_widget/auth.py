"""Google OAuth 2.0 for installed apps: loopback redirect + PKCE, stdlib only.

See https://developers.google.com/identity/protocols/oauth2/native-app
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import ssl
import sys
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .storage import data_dir, read_secure_json, write_secure_json

log = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
SCOPE = "https://www.googleapis.com/auth/tasks"

SSL_CONTEXT = ssl.create_default_context()


class AuthError(Exception):
    pass


class SignInCancelled(AuthError):
    pass


class ReauthRequired(AuthError):
    """The saved sign-in is no longer valid (revoked or expired)."""


class AuthNetworkError(AuthError):
    """Google's sign-in servers couldn't be reached."""


# --------------------------------------------------------------------------- client config

@dataclass
class ClientConfig:
    client_id: str
    client_secret: str | None
    source: str = ""


def _parse_client_json(raw: dict) -> ClientConfig | None:
    section = raw.get("installed") or raw.get("web") or raw
    cid = section.get("client_id")
    if not cid:
        return None
    return ClientConfig(cid, section.get("client_secret"))


def _bundled_client_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "gtask_widget" / "_bundled_client.json"


def user_client_path() -> Path:
    return data_dir() / "client_secret.json"


def load_client_config() -> ClientConfig | None:
    """Find OAuth client credentials.

    Order: $GTASK_WIDGET_CLIENT_SECRETS, the user's data folder, then the
    client bundled into official release builds.
    """
    candidates = []
    if os.environ.get("GTASK_WIDGET_CLIENT_SECRETS"):
        candidates.append(Path(os.environ["GTASK_WIDGET_CLIENT_SECRETS"]))
    candidates += [user_client_path(), _bundled_client_path()]
    for path in candidates:
        try:
            cfg = _parse_client_json(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError, AttributeError):
            continue
        if cfg:
            cfg.source = str(path)
            return cfg
    return None


def install_client_config(src: str | Path) -> ClientConfig:
    """Validate a client_secret.json chosen by the user and copy it to the data folder."""
    try:
        cfg = _parse_client_json(json.loads(Path(src).read_text("utf-8")))
    except (OSError, ValueError, AttributeError) as e:
        raise AuthError(f"Couldn't read that file: {e}") from e
    if not cfg:
        raise AuthError("That file doesn't look like a Google OAuth client (no client_id).")
    shutil.copyfile(src, user_client_path())
    cfg.source = str(user_client_path())
    return cfg


# --------------------------------------------------------------------------- tokens

@dataclass
class Credentials:
    access_token: str
    refresh_token: str
    expiry: float
    scope: str = ""

    @property
    def expired(self) -> bool:
        return time.time() > self.expiry - 60


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "token.bin"

    def load(self) -> Credentials | None:
        raw = read_secure_json(self.path)
        if not isinstance(raw, dict):
            return None
        try:
            return Credentials(**raw)
        except TypeError:
            return None

    def save(self, creds: Credentials) -> None:
        write_secure_json(self.path, asdict(creds))

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _post_form(url: str, data: dict) -> dict:
    req = Request(url, data=urlencode(data).encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(req, timeout=20, context=SSL_CONTEXT) as r:
            return json.loads(r.read() or b"{}")
    except HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            body = {}
        body.setdefault("error", f"http_{e.code}")
        body["_status"] = e.code
        return body
    except (URLError, OSError) as e:
        raise AuthNetworkError(f"Can't reach Google ({getattr(e, 'reason', e)})") from e


# --------------------------------------------------------------------------- browser pages

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>GTask Widget</title>
<style>
  body{{margin:0;height:100vh;display:grid;place-items:center;background:#0f1115;color:#e8eaed;
       font:15px/1.5 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}}
  .card{{text-align:center;padding:40px 48px;border-radius:16px;background:#1a1d24;
        border:1px solid #2a2e37;max-width:380px}}
  .mark{{width:44px;height:44px;border-radius:50%;margin:0 auto 16px;display:grid;place-items:center;
        background:{color};color:#0f1115;font-size:24px;font-weight:700}}
  h1{{font-size:19px;font-weight:600;margin:0 0 6px}} p{{margin:0;color:#9aa0a6}}
</style></head><body><div class="card"><div class="mark">{mark}</div>
<h1>{title}</h1><p>{body}</p></div></body></html>"""

SUCCESS_PAGE = _PAGE.format(color="#8ab4f8", mark="&#10003;", title="You're signed in",
                            body="You can close this tab. Your tasks are loading in the widget.")


def _error_page(msg: str) -> str:
    import html
    return _PAGE.format(color="#f28b82", mark="!", title="Sign-in didn't finish",
                        body=html.escape(msg) + "<br>Go back to the widget and try again.")


# --------------------------------------------------------------------------- session

class Auth:
    """Holds credentials, refreshes them, and runs the browser sign-in flow."""

    def __init__(self, client: ClientConfig, store: TokenStore | None = None):
        self.client = client
        self.store = store or TokenStore()
        self._lock = threading.Lock()
        self.creds: Credentials | None = self.store.load()

    @property
    def signed_in(self) -> bool:
        return self.creds is not None

    # -- tokens -----------------------------------------------------------
    def access_token(self) -> str:
        with self._lock:
            if self.creds is None:
                raise ReauthRequired("Not signed in")
            if self.creds.expired:
                self._refresh_locked()
            return self.creds.access_token

    def force_refresh(self) -> None:
        with self._lock:
            if self.creds is None:
                raise ReauthRequired("Not signed in")
            self._refresh_locked()

    def _refresh_locked(self) -> None:
        data = {
            "client_id": self.client.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.creds.refresh_token,
        }
        if self.client.client_secret:
            data["client_secret"] = self.client.client_secret
        tok = _post_form(TOKEN_URI, data)
        if "access_token" not in tok:
            err = tok.get("error", "unknown")
            if err in ("invalid_grant", "unauthorized_client", "invalid_client"):
                log.warning("Refresh token rejected (%s); sign-in required", err)
                self.creds = None
                self.store.clear()
                raise ReauthRequired("Your Google sign-in expired. Please sign in again.")
            raise AuthError(f"Couldn't refresh sign-in: {tok.get('error_description', err)}")
        self.creds.access_token = tok["access_token"]
        self.creds.expiry = time.time() + int(tok.get("expires_in", 3600))
        if tok.get("refresh_token"):
            self.creds.refresh_token = tok["refresh_token"]
        self.store.save(self.creds)

    # -- sign in / out ----------------------------------------------------
    def sign_in(
        self,
        cancel: threading.Event | None = None,
        open_browser: Callable[[str], object] = webbrowser.open,
        on_url: Callable[[str], None] | None = None,
        timeout: float = 300,
    ) -> Credentials:
        cancel = cancel or threading.Event()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(24)
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (stdlib API)
                parsed = urlparse(self.path)
                if parsed.path not in ("", "/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if q.get("state") != state:
                    page = _error_page("The sign-in response didn't match this request.")
                    result.setdefault("error", "state_mismatch")
                elif "error" in q:
                    result["error"] = q["error"]
                    page = _error_page("Access was not granted." if q["error"] == "access_denied" else q["error"])
                elif "code" in q:
                    result["code"] = q["code"]
                    page = SUCCESS_PAGE
                else:
                    self.send_response(400)
                    self.end_headers()
                    return
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 0.25
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
        url = AUTH_URI + "?" + urlencode({
            "client_id": self.client.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        })
        try:
            if on_url:
                on_url(url)
            open_browser(url)
            deadline = time.monotonic() + timeout
            while not result:
                if cancel.is_set():
                    raise SignInCancelled("Sign-in cancelled")
                if time.monotonic() > deadline:
                    raise AuthError("Sign-in timed out. Please try again.")
                server.handle_request()
        finally:
            server.server_close()

        if "error" in result:
            if result["error"] == "access_denied":
                raise AuthError("Access was not granted.")
            raise AuthError(f"Sign-in failed: {result['error']}")

        data = {
            "code": result["code"],
            "client_id": self.client.client_id,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
        if self.client.client_secret:
            data["client_secret"] = self.client.client_secret
        tok = _post_form(TOKEN_URI, data)
        if "access_token" not in tok:
            raise AuthError(f"Sign-in failed: {tok.get('error_description') or tok.get('error')}")
        if SCOPE not in tok.get("scope", SCOPE).split():
            raise AuthError("Permission to view and edit your tasks wasn't granted.")
        if not tok.get("refresh_token"):
            raise AuthError("Google didn't return a refresh token. Please try again.")
        creds = Credentials(
            access_token=tok["access_token"],
            refresh_token=tok["refresh_token"],
            expiry=time.time() + int(tok.get("expires_in", 3600)),
            scope=tok.get("scope", SCOPE),
        )
        with self._lock:
            self.creds = creds
            self.store.save(creds)
        log.info("Signed in")
        return creds

    def sign_out(self) -> None:
        with self._lock:
            creds, self.creds = self.creds, None
            self.store.clear()
        if creds:
            # Best effort: revoke the grant so it disappears from the Google account.
            # Done in the background so signing out never waits on the network.
            def revoke():
                try:
                    _post_form(REVOKE_URI, {"token": creds.refresh_token})
                except AuthError:
                    pass
            threading.Thread(target=revoke, daemon=True).start()
        log.info("Signed out")
