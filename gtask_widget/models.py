"""Task data, due-date helpers, and the filter/sort logic behind the list view."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta


@dataclass
class TaskList:
    id: str
    title: str


@dataclass
class Task:
    id: str
    list_id: str
    title: str = ""
    notes: str = ""
    status: str = "needsAction"
    due: date | None = None
    completed: str = ""          # RFC 3339 timestamp when done
    parent: str | None = None
    position: str = ""
    updated: str = ""
    web_link: str = ""
    pending: bool = field(default=False, compare=False)  # local change not yet confirmed

    @property
    def done(self) -> bool:
        return self.status == "completed"

    @classmethod
    def from_api(cls, d: dict, list_id: str) -> "Task":
        return cls(
            id=d["id"],
            list_id=list_id,
            title=d.get("title", ""),
            notes=d.get("notes", ""),
            status=d.get("status", "needsAction"),
            due=parse_due(d.get("due")),
            completed=d.get("completed", ""),
            parent=d.get("parent"),
            position=d.get("position", ""),
            updated=d.get("updated", ""),
            web_link=d.get("webViewLink", ""),
        )

    def to_cache(self) -> dict:
        d = asdict(self)
        d["due"] = self.due.isoformat() if self.due else None
        d.pop("pending")
        return d

    @classmethod
    def from_cache(cls, d: dict) -> "Task":
        d = dict(d)
        d["due"] = parse_due(d.get("due"))
        return cls(**d)


# --------------------------------------------------------------------------- due dates

def parse_due(value: str | None) -> date | None:
    """Google stores due as midnight UTC of the chosen day; only the date part matters."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def due_to_api(d: date | None) -> str | None:
    return f"{d.isoformat()}T00:00:00.000Z" if d else None


def next_weekday(today: date, weekday: int = 0) -> date:
    """The next given weekday strictly after today (0 = Monday)."""
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def due_label(d: date, today: date) -> tuple[str, str]:
    """Short label and a kind: overdue | today | soon | later."""
    delta = (d - today).days
    if delta == 0:
        return "Today", "today"
    if delta == 1:
        return "Tomorrow", "soon"
    if delta == -1:
        return "Yesterday", "overdue"
    if 1 < delta < 7:
        return d.strftime("%a"), "soon"
    text = f"{d.strftime('%b')} {d.day}"
    if d.year != today.year:
        text += f", {d.year}"
    return text, "overdue" if delta < 0 else "later"


# --------------------------------------------------------------------------- filtering

CHIPS = [
    ("all", "All"),
    ("today", "Today"),
    ("upcoming", "Upcoming"),
    ("overdue", "Overdue"),
    ("nodate", "No date"),
]


def matches_chip(t: Task, chip: str, today: date) -> bool:
    if chip == "today":
        return t.due == today
    if chip == "upcoming":
        return t.due is not None and t.due > today
    if chip == "overdue":
        return t.due is not None and t.due < today
    if chip == "nodate":
        return t.due is None
    return True


def matches_query(t: Task, query: str) -> bool:
    q = query.strip().casefold()
    return not q or q in t.title.casefold() or q in t.notes.casefold()


def _tree_order(tasks: list[Task]) -> list[tuple[Task, int]]:
    """Depth-first order by Google's position, keeping subtasks under parents."""
    ids = {t.id for t in tasks}
    children: dict[str | None, list[Task]] = defaultdict(list)
    for t in tasks:
        children[t.parent if t.parent in ids else None].append(t)
    for kids in children.values():
        kids.sort(key=lambda t: t.position)
    out: list[tuple[Task, int]] = []

    def walk(parent: str | None, depth: int) -> None:
        for t in children.get(parent, []):
            out.append((t, depth))
            walk(t.id, depth + 1)

    walk(None, 0)
    return out


def arrange(
    tasks: list[Task],
    *,
    chip: str = "all",
    query: str = "",
    sort: str = "my",
    today: date | None = None,
) -> tuple[list[tuple[Task, int]], list[Task]]:
    """Return (open rows as (task, depth), completed tasks) for one list."""
    today = today or date.today()
    open_tasks = [t for t in tasks if not t.done]
    ordered = _tree_order(open_tasks)
    shown = {t.id for t, _ in ordered if matches_chip(t, chip, today) and matches_query(t, query)}
    rows = []
    for t, depth in ordered:
        if t.id in shown:
            # indent only while the parent is visible too
            rows.append((t, depth if t.parent in shown else 0))
    if sort == "date":
        rank = {t.id: i for i, (t, _) in enumerate(ordered)}
        rows = [(t, 0) for t, _ in rows]
        rows.sort(key=lambda r: (r[0].due is None, r[0].due or date.max, rank[r[0].id]))

    done = []
    if chip == "all":
        done = [t for t in tasks if t.done and matches_query(t, query)]
        done.sort(key=lambda t: t.completed, reverse=True)
    return rows, done
