from datetime import date

from gtask_widget.models import Task, arrange, due_label, due_to_api, next_weekday, parse_due

TODAY = date(2026, 10, 3)  # a Saturday


def t(id, title, pos, due=None, parent=None, done=False, notes="", completed=""):
    return Task(id=id, list_id="L", title=title, position=pos, due=due, parent=parent,
                status="completed" if done else "needsAction", notes=notes, completed=completed)


def test_due_roundtrip_keeps_calendar_date():
    # Google stores due as midnight UTC; the date part must never shift with time zones.
    assert parse_due("2026-10-03T00:00:00.000Z") == date(2026, 10, 3)
    assert due_to_api(date(2026, 10, 3)) == "2026-10-03T00:00:00.000Z"
    assert parse_due(None) is None
    assert parse_due("garbage") is None


def test_due_labels():
    assert due_label(TODAY, TODAY) == ("Today", "today")
    assert due_label(date(2026, 10, 4), TODAY) == ("Tomorrow", "soon")
    assert due_label(date(2026, 10, 2), TODAY) == ("Yesterday", "overdue")
    assert due_label(date(2026, 10, 7), TODAY) == ("Wed", "soon")
    assert due_label(date(2026, 9, 20), TODAY) == ("Sep 20", "overdue")
    assert due_label(date(2027, 1, 5), TODAY) == ("Jan 5, 2027", "later")


def test_next_weekday():
    assert next_weekday(TODAY, 0) == date(2026, 10, 5)  # Monday after
    assert next_weekday(date(2026, 10, 5), 0) == date(2026, 10, 12)  # strictly after


def test_arrange_keeps_subtasks_under_parent():
    tasks = [
        t("b", "B", "2"),
        t("a", "A", "1"),
        t("a2", "A child 2", "2", parent="a"),
        t("a1", "A child 1", "1", parent="a"),
        t("d", "Done", "3", done=True, completed="2026-10-02T10:00:00.000Z"),
    ]
    rows, done = arrange(tasks, today=TODAY)
    assert [(r.id, depth) for r, depth in rows] == [("a", 0), ("a1", 1), ("a2", 1), ("b", 0)]
    assert [d.id for d in done] == ["d"]


def test_orphan_subtask_shown_at_top_level():
    tasks = [t("p", "Parent", "1", done=True), t("c", "Child", "1", parent="p")]
    rows, _ = arrange(tasks, today=TODAY)
    assert [(r.id, depth) for r, depth in rows] == [("c", 0)]


def test_chips_and_search():
    tasks = [
        t("1", "Pay rent", "1", due=TODAY),
        t("2", "Old thing", "2", due=date(2026, 9, 1)),
        t("3", "Future", "3", due=date(2026, 12, 1)),
        t("4", "Someday", "4", notes="buy RENT supplies"),
    ]
    ids = lambda chip, q="": [r.id for r, _ in arrange(tasks, chip=chip, query=q, today=TODAY)[0]]
    assert ids("today") == ["1"]
    assert ids("overdue") == ["2"]
    assert ids("upcoming") == ["3"]
    assert ids("nodate") == ["4"]
    assert ids("all", "rent") == ["1", "4"]  # matches title and notes, case-insensitive
    # completed section only accompanies the "All" chip
    assert arrange(tasks + [t("5", "x", "5", done=True)], chip="today", today=TODAY)[1] == []


def test_sort_by_due_date():
    tasks = [
        t("1", "No date", "1"),
        t("2", "Later", "2", due=date(2026, 11, 1)),
        t("3", "Sooner", "3", due=date(2026, 10, 4)),
    ]
    rows, _ = arrange(tasks, sort="date", today=TODAY)
    assert [r.id for r, _ in rows] == ["3", "2", "1"]


def test_cache_roundtrip():
    task = t("x", "Title", "1", due=TODAY, notes="n")
    assert Task.from_cache(task.to_cache()) == task
