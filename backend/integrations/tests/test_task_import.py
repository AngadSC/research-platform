"""Importing tasks from Todoist, Trello and monday.com (D240). Hidden until the deployment opts in,
own account only, and never a second copy. Every provider reply is faked."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from integrations.models import ConnectedAccount
from integrations.providers import monday, todoist, trello
from integrations.tests.fake import response
from projects.models import Task

pytestmark = pytest.mark.django_db

TODOIST_TASKS = f"{todoist.API}/tasks?project_id=p1&limit=200"
BOARD = "0123456789abcdef01234567"
TRELLO_CARDS = f"{trello.API}/boards/{BOARD}/cards/open?fields=name,desc,due"


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.INTEGRATION_OPTIONAL_PROVIDERS = ["todoist", "trello", "monday"]


@pytest.fixture
def world(lab_users, make_project):
    lab, users = lab_users
    return lab, users["lab_admin"], make_project(lab)


def account(lab, user, provider="todoist", key="k", secret=""):
    row = ConnectedAccount(
        lab=lab,
        user=user,
        provider=provider,
        external_account_id="1",
        external_email="x@example.org",
        connected_at="2030-01-01T00:00:00Z",
    )
    row.set_tokens(access=key, refresh=secret, expires_at=None)
    row.save()
    return row


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def imp(user, lab, project, provider, source):
    url = f"/api/labs/{lab.pk}/projects/{project.pk}/integrations/{provider}/import-tasks/"
    return client(user).post(url, {"source": source}, format="json")


def test_hidden_unless_the_deployment_opts_in(world, settings):
    lab, user, project = world
    account(lab, user)
    settings.INTEGRATION_OPTIONAL_PROVIDERS = []
    names = [
        p["name"] for p in client(user).get(f"/api/labs/{lab.pk}/integrations/providers/").json()
    ]
    assert "todoist" not in names and "zotero" in names
    connect = client(user).post(
        f"/api/labs/{lab.pk}/integrations/todoist/connect/", {"api_key": "x"}, format="json"
    )
    assert connect.json()["code"] == "unknown_provider"
    assert (
        client(user).get(f"/api/labs/{lab.pk}/integrations/todoist/task-sources/").status_code
        == 404
    )
    assert imp(user, lab, project, "todoist", "p1").status_code == 404


def test_shown_when_opted_in(world):
    lab, user, _ = world
    rows = client(user).get(f"/api/labs/{lab.pk}/integrations/providers/").json()
    assert next(p for p in rows if p["name"] == "todoist")["task_import"] is True


def test_todoist_import_copies_tasks_once(world, transport):
    lab, user, project = world
    account(lab, user)
    transport.on(
        "GET",
        TODOIST_TASKS,
        response(
            200,
            {
                "results": [
                    {
                        "content": "Book MRI",
                        "description": "Slot B",
                        "due": {"date": "2030-02-03T10:00:00"},
                    },
                    {"content": "No due date"},
                    {"content": "  "},
                ],
                "next_cursor": None,
            },
        ),
    )
    first = imp(user, lab, project, "todoist", "p1")
    assert first.json() == {"created": 2, "skipped": 0}
    task = Task.objects.for_lab(lab).get(title="Book MRI")
    assert task.description == "Slot B" and task.due_date == date(2030, 2, 3)
    assert task.assignee is None and task.created_by == user
    assert imp(user, lab, project, "todoist", "p1").json() == {"created": 0, "skipped": 2}
    event = AuditEvent.objects.filter(action=AuditAction.TASKS_IMPORTED).first()
    assert event.metadata["provider"] == "todoist" and "Book MRI" not in str(event.metadata)


def test_import_needs_your_own_account(world, lab_users, transport):
    lab, user, project = world
    account(lab, lab_users[1]["pi"])  # someone else's connection must not be used
    assert imp(user, lab, project, "todoist", "p1").status_code == 404
    assert transport.calls == []


def test_a_bad_source_id_never_reaches_the_service(world, transport):
    lab, user, project = world
    account(lab, user)
    assert imp(user, lab, project, "todoist", "../users").status_code == 502
    assert transport.calls == []


def test_trello_sends_credentials_in_the_header_only(world, transport):
    lab, user, project = world
    account(lab, user, "trello", key="the-key", secret="the-token")
    transport.on(
        "GET",
        TRELLO_CARDS,
        response(200, [{"name": "Card", "desc": "d", "due": "2030-01-02T00:00:00.000Z"}]),
    )
    assert imp(user, lab, project, "trello", BOARD).json() == {"created": 1, "skipped": 0}
    url, sent = transport.calls[0][1], transport.calls[0][2]
    assert "the-key" not in url and "the-token" not in url
    assert (
        sent["headers"]["Authorization"]
        == 'OAuth oauth_consumer_key="the-key", oauth_token="the-token"'
    )


def test_monday_reads_a_board_with_the_id_as_a_variable(world, transport):
    lab, user, project = world
    account(lab, user, "monday", key="tok")
    transport.on(
        "POST",
        monday.API,
        response(
            200,
            {
                "data": {
                    "boards": [
                        {
                            "items_page": {
                                "items": [
                                    {"name": "Item", "column_values": [{}, {"date": "2030-05-06"}]},
                                    {"name": "Undated", "column_values": []},
                                ]
                            }
                        }
                    ]
                }
            },
        ),
    )
    assert imp(user, lab, project, "monday", "12345").json() == {"created": 2, "skipped": 0}
    sent = transport.calls[0][2]
    assert sent["json"]["variables"]["board"] == ["12345"] and "12345" not in sent["json"]["query"]
    assert sent["headers"]["Authorization"] == "tok"
    assert Task.objects.for_lab(lab).get(title="Item").due_date == date(2030, 5, 6)


def test_monday_errors_are_a_clean_failure(world, transport):
    lab, user, project = world
    account(lab, user, "monday")
    transport.on("POST", monday.API, response(200, {"errors": [{"message": "nope"}]}))
    resp = imp(user, lab, project, "monday", "12345")
    assert resp.status_code == 502 and "nope" not in resp.content.decode()


def test_task_sources_lists_your_projects(world, transport):
    lab, user, _ = world
    account(lab, user)
    transport.on(
        "GET",
        f"{todoist.API}/projects?limit=200",
        response(200, {"results": [{"id": "p1", "name": "Inbox"}]}),
    )
    got = client(user).get(f"/api/labs/{lab.pk}/integrations/todoist/task-sources/")
    assert got.json() == [{"id": "p1", "name": "Inbox"}]


def test_a_revoked_token_is_handled(world, transport):
    lab, user, project = world
    acct = account(lab, user)
    transport.on("GET", TODOIST_TASKS, response(401, {}))
    assert imp(user, lab, project, "todoist", "p1").status_code == 502
    acct.refresh_from_db()
    assert acct.status == "expired"
