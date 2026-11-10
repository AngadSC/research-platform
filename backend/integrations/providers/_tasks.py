"""Shared by the task-import providers (Todoist, Trello, monday.com, D240)."""

from django.utils.dateparse import parse_date

from integrations.providers._refs import clean_text

MAX_TASKS = 200  # one import; also the page size asked for, so no paging is needed


def task(title, notes, due) -> dict | None:
    """One imported task, or None when it has no title. `due` may be a date or a date-time."""
    title = clean_text(title, 300)
    if not title:
        return None
    try:
        due_date = parse_date(str(due)[:10]) if due else None
    except ValueError:  # the right shape but not a real date (2026-13-01)
        due_date = None
    return {"title": title, "notes": str(notes or "")[:5000], "due_date": due_date}


def tasks(rows) -> list[dict]:
    return [t for t in rows[:MAX_TASKS] if t]
