"""In-memory stand-in for TasksClient, used by `--demo` and for screenshots."""

from __future__ import annotations

import copy
import itertools
from datetime import date, datetime, timedelta, timezone

from .models import Task, TaskList, next_weekday, parse_due


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class DemoClient:
    def __init__(self, today: date | None = None):
        t = today or date.today()
        d = timedelta
        self._ids = itertools.count(1)
        self._pos = itertools.count(1000)
        self._lists = [TaskList("mine", "My Tasks"), TaskList("work", "Work"), TaskList("groceries", "Groceries")]
        self._tasks: dict[str, list[Task]] = {l.id: [] for l in self._lists}
        hike = self._add("mine", "Plan weekend hike", due=t, notes="Check trail conditions and parking")
        self._add("mine", "Pack water filter", parent=hike)
        self._add("mine", "Charge headlamp", parent=hike)
        self._add("mine", "Call Mom", due=t + d(1))
        self._add("mine", "Renew passport", due=t - d(3), notes="Photos are in the top drawer")
        self._add("mine", "Read “The Pragmatic Programmer”")
        self._add("mine", "Book dentist appointment", done=True)
        self._add("work", "Review open pull requests", due=t)
        self._add("work", "Draft Q4 roadmap", due=t + d(4), notes="Focus on onboarding metrics")
        self._add("work", "Prepare slides for the Friday sync", due=next_weekday(t, 4))
        self._add("work", "Reply to design feedback")
        self._add("work", "Send weekly update", done=True)
        for item in ("Oat milk", "Avocados", "Coffee beans", "Sourdough bread"):
            self._add("groceries", item)
        self._add("groceries", "Eggs", done=True)

    def _add(self, list_id, title, due=None, notes="", parent=None, done=False) -> str:
        tid = f"demo{next(self._ids)}"
        self._tasks[list_id].append(Task(
            id=tid, list_id=list_id, title=title, notes=notes, due=due, parent=parent,
            status="completed" if done else "needsAction", completed=_now() if done else "",
            position=f"{next(self._pos):020d}",
        ))
        return tid

    def _get(self, list_id: str, task_id: str) -> Task:
        for t in self._tasks[list_id]:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    # -- TasksClient interface ------------------------------------------------
    def list_tasklists(self):
        return copy.deepcopy(self._lists)

    def insert_tasklist(self, title):
        tl = TaskList(f"list{next(self._ids)}", title)
        self._lists.append(tl)
        self._tasks[tl.id] = []
        return copy.deepcopy(tl)

    def list_tasks(self, list_id):
        return copy.deepcopy(self._tasks.get(list_id, []))

    def insert_task(self, list_id, body, parent=None, previous=None):
        top = min((t.position for t in self._tasks[list_id]), default=f"{10**6:020d}")
        tid = f"demo{next(self._ids)}"
        task = Task(id=tid, list_id=list_id, title=body.get("title", ""), notes=body.get("notes", ""),
                    due=parse_due(body.get("due")), parent=parent, position=f"{int(top) - 1:020d}")
        self._tasks[list_id].append(task)
        return copy.deepcopy(task)

    def patch_task(self, list_id, task_id, body):
        t = self._get(list_id, task_id)
        if "title" in body:
            t.title = body["title"]
        if "notes" in body:
            t.notes = body["notes"] or ""
        if "due" in body:
            t.due = parse_due(body["due"])
        if "status" in body:
            t.status = body["status"]
            t.completed = _now() if t.status == "completed" else ""
        return copy.deepcopy(t)

    def delete_task(self, list_id, task_id):
        self._tasks[list_id] = [t for t in self._tasks[list_id] if t.id != task_id and t.parent != task_id]
