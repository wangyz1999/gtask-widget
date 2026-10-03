"""Minimal Google Tasks REST client (v1), stdlib only.

Reference: https://developers.google.com/tasks/reference/rest
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .auth import SSL_CONTEXT, Auth
from .models import Task, TaskList

log = logging.getLogger(__name__)

# How far back to load completed tasks for the "Completed" section.
COMPLETED_WINDOW_DAYS = 30


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class OfflineError(ApiError):
    pass


class TasksClient:
    base_url = "https://tasks.googleapis.com/tasks/v1"

    def __init__(self, auth: Auth):
        self.auth = auth

    # -- transport ---------------------------------------------------------
    def _call(self, method: str, path: str, params: dict | None = None,
              body: dict | None = None, _retry: bool = True):
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.auth.access_token())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=20, context=SSL_CONTEXT) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except HTTPError as e:
            if e.code == 401 and _retry:
                self.auth.force_refresh()
                return self._call(method, path, params, body, _retry=False)
            try:
                msg = json.loads(e.read() or b"{}").get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                msg = ""
            log.warning("%s %s -> %s %s", method, path, e.code, msg)
            raise ApiError(e.code, msg or f"Google Tasks returned HTTP {e.code}") from e
        except (URLError, TimeoutError, OSError) as e:
            raise OfflineError(0, f"Can't reach Google ({getattr(e, 'reason', e)})") from e

    def _paged(self, path: str, params: dict) -> list[dict]:
        items, token = [], None
        while True:
            p = dict(params, maxResults=100)
            if token:
                p["pageToken"] = token
            page = self._call("GET", path, p) or {}
            items += page.get("items", [])
            token = page.get("nextPageToken")
            if not token:
                return items

    # -- task lists ----------------------------------------------------------
    def list_tasklists(self) -> list[TaskList]:
        return [TaskList(d["id"], d.get("title", "")) for d in self._paged("/users/@me/lists", {})]

    def insert_tasklist(self, title: str) -> TaskList:
        d = self._call("POST", "/users/@me/lists", body={"title": title})
        return TaskList(d["id"], d.get("title", title))

    # -- tasks ---------------------------------------------------------------
    def list_tasks(self, list_id: str) -> list[Task]:
        path = f"/lists/{quote(list_id, safe='')}/tasks"
        open_items = self._paged(path, {"showCompleted": "false"})
        since = datetime.now(timezone.utc) - timedelta(days=COMPLETED_WINDOW_DAYS)
        done_items = self._paged(path, {
            "showCompleted": "true",
            "showHidden": "true",
            "completedMin": since.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        })
        seen, tasks = set(), []
        for d in open_items + done_items:
            if d["id"] in seen or d.get("deleted"):
                continue
            seen.add(d["id"])
            tasks.append(Task.from_api(d, list_id))
        return tasks

    def insert_task(self, list_id: str, body: dict, parent: str | None = None,
                    previous: str | None = None) -> Task:
        params = {}
        if parent:
            params["parent"] = parent
        if previous:
            params["previous"] = previous
        d = self._call("POST", f"/lists/{quote(list_id, safe='')}/tasks", params or None, body)
        return Task.from_api(d, list_id)

    def patch_task(self, list_id: str, task_id: str, body: dict) -> Task:
        d = self._call("PATCH", f"/lists/{quote(list_id, safe='')}/tasks/{quote(task_id, safe='')}",
                       body=body)
        return Task.from_api(d, list_id)

    def delete_task(self, list_id: str, task_id: str) -> None:
        self._call("DELETE", f"/lists/{quote(list_id, safe='')}/tasks/{quote(task_id, safe='')}")
