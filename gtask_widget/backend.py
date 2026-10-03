"""App state and background sync.

All network calls run one at a time on a worker thread, so changes reach
Google in the order you made them. The UI updates immediately (optimistic
updates) and rolls back if Google rejects a change.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from .api import ApiError, OfflineError, TasksClient
from .auth import (Auth, AuthError, AuthNetworkError, ReauthRequired, SignInCancelled,
                   install_client_config, load_client_config)
from .demo import DemoClient
from .models import Task, TaskList, due_to_api
from .storage import data_dir, read_secure_json, write_secure_json

log = logging.getLogger(__name__)

_UNSET = object()


class _Invoker(QObject):
    """Runs callables on the GUI thread when emitted from a worker thread."""

    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        fn()


class Backend(QObject):
    changed = Signal()                 # lists or tasks changed
    stateChanged = Signal(str)         # no_client | signed_out | signing_in | ready
    busyChanged = Signal(bool)
    message = Signal(str, str)         # text, kind (info | error)

    def __init__(self, demo: bool = False):
        super().__init__()
        self.demo = demo
        self.lists: list[TaskList] = []
        self.tasks: dict[str, list[Task]] = {}
        self.offline = False
        self.last_sync = 0.0
        self.sign_in_url = ""
        self.auth: Auth | None = None
        self.client: TasksClient | DemoClient | None = None
        self.state = "signed_out"
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gtask-api")
        self._invoker = _Invoker()
        self._busy = 0
        self._refreshing = False
        self._cancel_sign_in: threading.Event | None = None
        self._overrides: dict[str, Task | None] = {}
        self._override_count: dict[str, int] = {}
        self._id_map: dict[str, str] = {}   # local temp id -> id assigned by Google
        self._setup()

    # ------------------------------------------------------------------ setup
    def _setup(self) -> None:
        if self.demo:
            self.client = DemoClient()
            self.state = "ready"
            return
        cfg = load_client_config()
        if not cfg:
            self.state = "no_client"
            return
        self.auth = Auth(cfg)
        self.client = TasksClient(self.auth)
        if self.auth.signed_in:
            self.state = "ready"
            self._load_cache()

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.stateChanged.emit(state)

    def install_client(self, path: str) -> None:
        try:
            cfg = install_client_config(path)
        except AuthError as e:
            self.message.emit(str(e), "error")
            return
        self.auth = Auth(cfg)
        self.client = TasksClient(self.auth)
        self._set_state("ready" if self.auth.signed_in else "signed_out")
        if self.state == "ready":
            self.refresh()

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _cache_path():
        return data_dir() / "cache.bin"

    def _load_cache(self) -> None:
        raw = read_secure_json(self._cache_path())
        if not isinstance(raw, dict):
            return
        try:
            self.lists = [TaskList(**l) for l in raw["lists"]]
            self.tasks = {lid: [Task.from_cache(t) for t in ts] for lid, ts in raw["tasks"].items()}
            self.last_sync = float(raw.get("saved_at", 0))
        except (KeyError, TypeError, ValueError):
            self.lists, self.tasks = [], {}

    def _save_cache(self) -> None:
        if self.demo:
            return
        try:
            write_secure_json(self._cache_path(), {
                "lists": [{"id": l.id, "title": l.title} for l in self.lists],
                "tasks": {lid: [t.to_cache() for t in ts if not t.id.startswith("local-")]
                          for lid, ts in self.tasks.items()},
                "saved_at": self.last_sync,
            })
        except OSError:
            log.exception("Couldn't write cache")

    # ------------------------------------------------------------------ worker plumbing
    def _set_busy(self, delta: int) -> None:
        was = self._busy > 0
        self._busy += delta
        if (self._busy > 0) != was:
            self.busyChanged.emit(self._busy > 0)

    @property
    def busy(self) -> bool:
        return self._busy > 0

    def _submit(self, job: Callable, ok: Callable | None = None, fail: Callable | None = None) -> None:
        self._set_busy(+1)
        emit = self._invoker.call.emit

        def work():
            try:
                res = job()
            except Exception as e:  # noqa: BLE001 (reported to the UI)
                emit(lambda e=e: (self._set_busy(-1), self._on_error(e, fail)))
            else:
                emit(lambda res=res: (self._set_busy(-1), ok and ok(res)))

        self._exec.submit(work)

    def _on_error(self, e: Exception, fail: Callable | None) -> None:
        if fail:
            fail(e)
        if isinstance(e, SignInCancelled):
            return
        if isinstance(e, ReauthRequired):
            self._signed_out()
            self.message.emit(str(e), "error")
        elif isinstance(e, (OfflineError, AuthNetworkError)):
            if not self.offline:
                self.offline = True
                self.message.emit("You're offline. Showing saved tasks.", "error")
            self.changed.emit()
        elif isinstance(e, (ApiError, AuthError)):
            self.message.emit(str(e), "error")
        else:
            log.error("Unexpected error", exc_info=e)
            self.message.emit(f"Something went wrong: {e}", "error")

    def shutdown(self) -> None:
        if self._cancel_sign_in:
            self._cancel_sign_in.set()
        self._exec.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ queries
    def list_title(self, list_id: str) -> str:
        return next((l.title for l in self.lists if l.id == list_id), "")

    def find(self, task_id: str) -> Task | None:
        for ts in self.tasks.values():
            for t in ts:
                if t.id == task_id:
                    return t
        return None

    def children(self, task: Task) -> list[Task]:
        return [t for t in self.tasks.get(task.list_id, []) if t.parent == task.id]

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        if self.state != "ready" or self._refreshing or self.client is None:
            return
        self._refreshing = True
        client = self.client

        def job():
            lists = client.list_tasklists()
            return lists, {l.id: client.list_tasks(l.id) for l in lists}

        def ok(res):
            self._refreshing = False
            self.offline = False
            self.lists, fetched = res
            self.tasks = self._with_overrides(fetched)
            self.last_sync = time.time()
            self._save_cache()
            self.changed.emit()

        def fail(_e):
            self._refreshing = False

        self._submit(job, ok, fail)

    def _with_overrides(self, fetched: dict[str, list[Task]]) -> dict[str, list[Task]]:
        """Keep local edits that Google hasn't confirmed yet on top of fresh data."""
        if not self._overrides:
            return fetched
        hidden = set(self._overrides)
        hidden |= {self._id_map[t] for t in self._overrides if t in self._id_map}
        out = {lid: [t for t in ts if t.id not in hidden] for lid, ts in fetched.items()}
        for local in self._overrides.values():
            if local is not None and local.list_id in out:
                out[local.list_id].append(local)
        return out

    # ------------------------------------------------------------------ local edits
    def _put_local(self, task: Task, old_id: str | None = None) -> None:
        key = old_id or task.id
        for lid, ts in self.tasks.items():
            for i, t in enumerate(ts):
                if t.id == key:
                    if lid == task.list_id:
                        ts[i] = task
                    else:
                        del ts[i]
                        self.tasks.setdefault(task.list_id, []).append(task)
                    return
        self.tasks.setdefault(task.list_id, []).append(task)

    def _drop_local(self, task_id: str) -> None:
        for lid, ts in self.tasks.items():
            self.tasks[lid] = [t for t in ts if t.id != task_id]

    def _real(self, task_id: str | None) -> str | None:
        return self._id_map.get(task_id, task_id) if task_id else None

    def _mutate(self, key: str, local: Task | None, revert: Task | None, call: Callable,
                after: Callable | None = None) -> None:
        """Apply `local` now, run `call` on the worker, then reconcile."""
        if local is None:
            self._drop_local(key)
        else:
            self._put_local(local)
        self._overrides[key] = local
        self._override_count[key] = self._override_count.get(key, 0) + 1
        self.changed.emit()

        def settle() -> bool:
            n = self._override_count.get(key, 1) - 1
            if n <= 0:
                self._override_count.pop(key, None)
                self._overrides.pop(key, None)
                return True
            self._override_count[key] = n
            return False

        def ok(server: Task | None):
            if settle() and server is not None:
                self._put_local(server, old_id=key)
            self._save_cache()
            self.changed.emit()
            if after:
                after(server)

        def fail(_e):
            if settle():
                if revert is None:
                    self._drop_local(key)
                else:
                    self._put_local(revert, old_id=key)
            self.changed.emit()

        self._submit(call, ok, fail)

    # ------------------------------------------------------------------ actions
    def add_task(self, list_id: str, title: str, *, parent: str | None = None,
                 due: date | None = None, notes: str = "") -> None:
        title = title.strip()
        if not title or self.client is None:
            return
        temp = "local-" + uuid.uuid4().hex
        local = Task(id=temp, list_id=list_id, title=title, notes=notes, due=due,
                     parent=parent, position="", pending=True)
        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due_to_api(due)
        client = self.client

        def call():
            t = client.insert_task(list_id, body, parent=self._real(parent))
            self._id_map[temp] = t.id
            return t

        self._mutate(temp, local, None, call)

    def set_done(self, task: Task, done: bool) -> None:
        if self.client is None or task.done == done:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if done else ""
        local = replace(task, status="completed" if done else "needsAction", completed=stamp, pending=True)
        body = {"status": "completed"} if done else {"status": "needsAction", "completed": None}
        client, tid, lid = self.client, task.id, task.list_id
        self._mutate(tid, local, task, lambda: client.patch_task(lid, self._real(tid), body))
        if done:  # like Google Tasks: finishing a task finishes its subtasks
            for child in self.children(task):
                if not child.done:
                    self.set_done(child, True)

    def edit_task(self, task: Task, *, title: str | None = None, notes: str | None = None,
                  due=_UNSET) -> None:
        if self.client is None:
            return
        body, changes = {}, {}
        if title is not None and title.strip() and title.strip() != task.title:
            body["title"] = changes["title"] = title.strip()
        if notes is not None and notes != task.notes:
            body["notes"] = changes["notes"] = notes
        if due is not _UNSET and due != task.due:
            body["due"] = due_to_api(due)
            changes["due"] = due
        if not body:
            return
        local = replace(task, pending=True, **changes)
        client, tid, lid = self.client, task.id, task.list_id
        self._mutate(tid, local, task, lambda: client.patch_task(lid, self._real(tid), body))

    def set_due(self, task: Task, due: date | None) -> None:
        self.edit_task(task, due=due)

    def delete_task(self, task: Task) -> None:
        if self.client is None:
            return
        for child in self.children(task):
            self._drop_local(child.id)
        client, tid, lid = self.client, task.id, task.list_id
        self._mutate(tid, None, task, lambda: client.delete_task(lid, self._real(tid)),
                     after=lambda _r: self.refresh())

    def restore_task(self, task: Task) -> None:
        """Undo a delete by re-creating the task (Google assigns a new id)."""
        parent = task.parent if task.parent and self.find(task.parent) else None
        self.add_task(task.list_id, task.title, parent=parent, due=task.due, notes=task.notes)

    def add_list(self, title: str, on_done: Callable[[TaskList], None] | None = None) -> None:
        title = title.strip()
        if not title or self.client is None:
            return
        client = self.client

        def ok(tl: TaskList):
            self.lists.append(tl)
            self.tasks.setdefault(tl.id, [])
            self._save_cache()
            self.changed.emit()
            if on_done:
                on_done(tl)

        self._submit(lambda: client.insert_tasklist(title), ok)

    # ------------------------------------------------------------------ sign in / out
    def sign_in(self) -> None:
        if self.auth is None or self.state == "signing_in":
            return
        self._cancel_sign_in = cancel = threading.Event()
        self.sign_in_url = ""
        self._set_state("signing_in")
        auth = self.auth
        emit = self._invoker.call.emit

        def on_url(url):
            emit(lambda: setattr(self, "sign_in_url", url))

        def ok(_creds):
            self._set_state("ready")
            self.refresh()

        def fail(_e):
            self._set_state("signed_out")

        self._submit(lambda: auth.sign_in(cancel=cancel, on_url=on_url), ok, fail)

    def cancel_sign_in(self) -> None:
        if self._cancel_sign_in:
            self._cancel_sign_in.set()

    def sign_out(self) -> None:
        if self.auth:
            self.auth.sign_out()
        self._signed_out()

    def _signed_out(self) -> None:
        self.lists, self.tasks = [], {}
        self._overrides.clear()
        self._override_count.clear()
        try:
            self._cache_path().unlink()
        except OSError:
            pass
        self._set_state("signed_out")
        self.changed.emit()
