"""Trello (D240). An API key and a token, sent in the Authorization header so they never appear
in a URL. Imports open cards only: nothing is ever written back to Trello."""

import re
from urllib.parse import quote

from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider
from integrations.providers._refs import clean_text, read
from integrations.providers._tasks import task, tasks

API = "https://api.trello.com/1"
_BOARD = re.compile(r"^[0-9a-f]{24}$")


@sensitive_variables("key", "secret", "header")
def sign(kwargs, key, secret):
    header = f'OAuth oauth_consumer_key="{key}", oauth_token="{secret}"'
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "Authorization": header}}


def identify(account):
    resp = http.send("GET", f"{API}/members/me?fields=username", provider=PROVIDER, account=account)
    if resp.status_code != 200:
        raise http.IntegrationError("Trello did not answer")
    data = resp.json()
    return str(data["id"]), str(data.get("username") or "")


def task_sources(account):
    url = f"{API}/members/me/boards?filter=open&fields=name"
    boards = read(PROVIDER, account, url, "Trello") or []
    return [{"id": str(b["id"]), "name": clean_text(b["name"], 200)} for b in boards]


def fetch_tasks(account, source_id):
    if not _BOARD.match(source_id):
        raise http.IntegrationError("Trello board id is not valid")
    url = f"{API}/boards/{quote(source_id, safe='')}/cards/open?fields=name,desc,due"
    cards = read(PROVIDER, account, url, "Trello") or []
    return tasks([task(c.get("name"), c.get("desc"), c.get("due")) for c in cards])


PROVIDER = Provider(
    name="trello",
    label="Trello",
    auth_type=AuthType.API_KEY,
    category=Category.TASKS,
    icon="trello",
    connect_fields=(
        ConnectField(
            "api_key",
            "Trello API key",
            "Make a key at trello.com/power-ups/admin, on your Power-Up's API key page.",
        ),
        ConnectField(
            "secret",
            "Trello token",
            "On that same page, follow the link to generate a token for your key.",
        ),
    ),
    identify=identify,
    sign=sign,
    api_hosts=frozenset({"api.trello.com"}),
    task_sources=task_sources,
    fetch_tasks=fetch_tasks,
    opt_in=True,
)
