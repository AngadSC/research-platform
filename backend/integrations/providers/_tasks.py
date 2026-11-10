"""Shared by the task-import providers (Todoist, Trello, monday.com, D240)."""

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from integrations.providers._refs import clean_text

MAX_TASKS = 1000  # one import, the same as a CSV of inventory
PAGE_SIZE = 200  # the most Todoist returns at once
MAX_PAGES = MAX_TASKS // PAGE_SIZE + 1  # one more than a full import needs, to spot an excess


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
    """All of a list or none of it (D244): quietly keeping the first part hides the rest."""
    found = [t for t in rows if t]
    if len(found) > MAX_TASKS:
        raise ValidationError(
            {
                "detail": f"This list has more than {MAX_TASKS} tasks, which is too many to "
                "import at once. Split it into smaller lists first."
            }
        )
    return found
