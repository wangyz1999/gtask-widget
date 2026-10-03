"""A tiny local stand-in for Google's token endpoint and the Tasks API."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeGoogle:
    def __init__(self):
        self.requests: list[tuple[str, str, dict, dict | None]] = []
        self.token_requests: list[dict] = []
        self.lists = [{"id": "L1", "title": "My Tasks"}]
        self.tasks = {"L1": [{"id": f"t{i}", "title": f"Task {i}", "status": "needsAction",
                              "position": f"{i:020d}"} for i in range(150)]}
        self.tasks["L1"].append({"id": "done1", "title": "Finished", "status": "completed",
                                 "completed": "2026-10-01T00:00:00.000Z", "position": "x"})
        self.valid_token = "access-1"
        self.reject_next_with_401 = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj=None):
                body = b"" if obj is None else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def do_POST(self):  # noqa: N802
                u = urlparse(self.path)
                if u.path == "/token":
                    form = {k: v[0] for k, v in parse_qs(self._body().decode()).items()}
                    fake.token_requests.append(form)
                    return self._send(200, fake.token_response(form))
                return self._api("POST", u, json.loads(self._body() or b"null"))

            def do_GET(self):  # noqa: N802
                return self._api("GET", urlparse(self.path), None)

            def do_PATCH(self):  # noqa: N802
                return self._api("PATCH", urlparse(self.path), json.loads(self._body() or b"null"))

            def do_DELETE(self):  # noqa: N802
                return self._api("DELETE", urlparse(self.path), None)

            def _api(self, method, u, body):
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                fake.requests.append((method, u.path, q, body))
                auth = self.headers.get("Authorization", "")
                if fake.reject_next_with_401 or auth != f"Bearer {fake.valid_token}":
                    fake.reject_next_with_401 = False
                    return self._send(401, {"error": {"message": "Invalid Credentials"}})
                status, obj = fake.route(method, u.path, q, body)
                return self._send(status, obj)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    # -- behaviour -----------------------------------------------------------
    def token_response(self, form):
        if form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") != "refresh-1":
                return {"error": "invalid_grant"}
            self.valid_token = "access-2"
            return {"access_token": "access-2", "expires_in": 3600}
        return {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/tasks", "_code": form.get("code")}

    def route(self, method, path, q, body):
        parts = path.strip("/").split("/")
        if parts[:3] == ["users", "@me", "lists"]:
            if method == "POST":
                tl = {"id": f"L{len(self.lists) + 1}", "title": body["title"]}
                self.lists.append(tl)
                self.tasks[tl["id"]] = []
                return 200, tl
            return 200, {"items": self.lists}
        if parts[0] == "lists" and parts[2] == "tasks":
            lid = parts[1]
            items = self.tasks[lid]
            if len(parts) == 3 and method == "GET":
                if q.get("showCompleted") == "false":
                    items = [t for t in items if t["status"] != "completed"]
                start = int(q.get("pageToken", 0))
                size = int(q.get("maxResults", 100))
                page = {"items": items[start:start + size]}
                if start + size < len(items):
                    page["nextPageToken"] = str(start + size)
                return 200, page
            if len(parts) == 3 and method == "POST":
                t = dict(body, id=f"new{len(items)}", status="needsAction", position="0")
                if q.get("parent"):
                    t["parent"] = q["parent"]
                items.append(t)
                return 200, t
            tid = parts[3]
            t = next(t for t in items if t["id"] == tid)
            if method == "PATCH":
                for k, v in body.items():
                    if v is None:
                        t.pop(k, None)
                    else:
                        t[k] = v
                return 200, t
            if method == "DELETE":
                items.remove(t)
                return 204, None
        return 404, {"error": {"message": "not found"}}
