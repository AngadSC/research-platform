"""monday.com (D240). A personal API token and one GraphQL endpoint. The board id is a query
variable, never built into the query text. Imports items only: nothing is ever written back."""

import re

from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider
from integrations.providers._refs import clean_text
from integrations.providers._tasks import MAX_PAGES, PAGE_SIZE, task, tasks

API = "https://api.monday.com/v2"
_BOARD = re.compile(r"^[0-9]{1,20}$")
_ME = "query { me { id email } }"
_BOARDS = "query { boards(limit: 200, state: active) { id name } }"
_PAGE = "cursor items { name column_values(types: [date]) { ... on DateValue { date } } }"
_ITEMS = (
    "query ($board: [ID!], $limit: Int!) { boards(ids: $board) { items_page(limit: $limit) { "
    + _PAGE
    + " } } }"
)
_NEXT = (
    "query ($cursor: String!, $limit: Int!) { next_items_page(cursor: $cursor, limit: $limit) { "
    + _PAGE
    + " } }"
)


@sensitive_variables("key")
def sign(kwargs, key, secret):
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "Authorization": key}}


def _query(account, query, variables=None) -> dict:
    """monday.com answers 200 with an `errors` list when a query fails."""
    resp = http.send(
        "POST",
        API,
        provider=PROVIDER,
        account=account,
        json={"query": query, "variables": variables or {}},
    )
    if resp.status_code != 200:
        raise http.IntegrationError("monday.com did not answer")
    try:
        body = resp.json()
        if body.get("errors"):
            raise ValueError
        return body["data"]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("monday.com returned an unreadable answer") from None


def identify(account):
    me = _query(account, _ME)["me"]
    return str(me["id"]), str(me.get("email") or "")


def task_sources(account):
    boards = _query(account, _BOARDS)["boards"]
    return [{"id": str(b["id"]), "name": clean_text(b["name"], 200)} for b in boards]


def _due(item):
    return next((c["date"] for c in item.get("column_values") or [] if c.get("date")), None)


def fetch_tasks(account, source_id):
    if not _BOARD.match(source_id):
        raise http.IntegrationError("monday.com board id is not valid")
    boards = _query(account, _ITEMS, {"board": [source_id], "limit": PAGE_SIZE})["boards"]
    if not boards:
        return []
    page, items = boards[0]["items_page"], []
    for _ in range(MAX_PAGES):
        items += page["items"]
        if not page.get("cursor"):
            break
        page = _query(account, _NEXT, {"cursor": page["cursor"], "limit": PAGE_SIZE})[
            "next_items_page"
        ]
    return tasks([task(i.get("name"), "", _due(i)) for i in items])


PROVIDER = Provider(
    name="monday",
    label="monday.com",
    auth_type=AuthType.API_KEY,
    category=Category.TASKS,
    icon="monday",
    connect_fields=(
        ConnectField(
            "api_key",
            "monday.com API token",
            "Find your personal token in monday.com under Developers, My access tokens.",
        ),
    ),
    identify=identify,
    sign=sign,
    api_hosts=frozenset({"api.monday.com"}),
    task_sources=task_sources,
    fetch_tasks=fetch_tasks,
    opt_in=True,
)
