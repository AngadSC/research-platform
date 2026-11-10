"""Todoist (D240). A personal API token, sent as a bearer header. Imports tasks only: nothing is
ever written back to Todoist."""

import re
from urllib.parse import urlencode

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider
from integrations.providers._refs import clean_text, read
from integrations.providers._tasks import MAX_TASKS, task, tasks

API = "https://api.todoist.com/api/v1"
_SOURCE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def identify(account):
    resp = http.send("GET", f"{API}/user", provider=PROVIDER, account=account)
    if resp.status_code != 200:
        raise http.IntegrationError("Todoist did not answer")
    data = resp.json()
    return str(data["id"]), str(data.get("email") or "")


def task_sources(account):
    data = read(PROVIDER, account, f"{API}/projects?limit={MAX_TASKS}", "Todoist") or {}
    return [{"id": str(p["id"]), "name": clean_text(p["name"], 200)} for p in data["results"]]


def fetch_tasks(account, source_id):
    if not _SOURCE.match(source_id):
        raise http.IntegrationError("Todoist project id is not valid")
    query = urlencode({"project_id": source_id, "limit": MAX_TASKS})
    data = read(PROVIDER, account, f"{API}/tasks?{query}", "Todoist") or {"results": []}
    return tasks(
        [
            task(t.get("content"), t.get("description"), (t.get("due") or {}).get("date"))
            for t in data["results"]
        ]
    )


PROVIDER = Provider(
    name="todoist",
    label="Todoist",
    auth_type=AuthType.API_KEY,
    category=Category.TASKS,
    icon="todoist",
    connect_fields=(
        ConnectField(
            "api_key", "Todoist API token", "Find it in Todoist under Settings, Integrations."
        ),
    ),
    identify=identify,
    api_hosts=frozenset({"api.todoist.com"}),
    task_sources=task_sources,
    fetch_tasks=fetch_tasks,
    opt_in=True,
)
