"""The lab chat and Google Chat, both ways (D315 to D320). Every Google call goes through the
patched HTTP layer; nothing leaves the process."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from integrations import services
from integrations.models import AccountStatus
from integrations.providers import google_chat
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response
from labs import google_chat as sync
from labs import services as lab_services
from labs.models import ChatSource, GoogleChatBridge, LabChatMessage

pytestmark = pytest.mark.django_db

API = google_chat.API
SPACE = "spaces/AAAA1234"
MESSAGES = f"{API}/{SPACE}/messages"
SCOPES = " ".join(google_chat.PROVIDER.scopes)


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_chat": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }


@pytest.fixture(autouse=True)
def committed(monkeypatch):
    """Run on_commit work at once, as a real commit would (the relay and Google deletes)."""
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, using=None, robust=False: func()
    )


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def connect_chat(transport, user, lab, sub, email, scopes=SCOPES):
    request = make_request(user)
    url = services.start_connect(request, lab, "google_chat")
    query = parse_qs(urlsplit(url).query)
    assert set(query["scope"][0].split()) == set(google_chat.PROVIDER.scopes)
    assert query["client_id"] == ["gc-client"]  # its own Google app, not Drive's (D315)
    transport.on("POST", google_chat.PROVIDER.token_url, token_reply("gc-at", "gc-rt", scopes))
    transport.on(
        "GET", google_chat.PROVIDER.identity_url, response(200, {"sub": sub, "email": email})
    )
    return services.complete_connect(request, state=query["state"][0], code="code")


@pytest.fixture
def linked(transport, lab_users):
    """The lab admin connects Google Chat and links the lab chat to SPACE."""
    lab, u = lab_users
    account = connect_chat(transport, u["lab_admin"], lab, "1001", "admin@example.test")
    transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
    bridge = sync.link_space(lab=lab, by=u["lab_admin"], space=SPACE)
    return lab, u, account, bridge


def test_connect_names_the_account_by_google_user_id(transport, lab_users):
    lab, u = lab_users
    account = connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    assert account.provider == "google_chat"
    assert account.external_account_id == "2002"
    assert account.external_email == "member@example.test"


CORE = " ".join(["openid", google_chat.EMAIL, google_chat.MESSAGES, google_chat.SPACES])


def test_connects_without_the_optional_membership_and_directory_scopes(transport, lab_users):
    lab, u = lab_users
    account = connect_chat(transport, u["member"], lab, "2002", "member@example.test", CORE)
    assert account.status == AccountStatus.ACTIVE and account.skipped == []
    assert set(account.granted_scopes) == set(CORE.split())


@pytest.mark.parametrize(
    "missing", ["openid", google_chat.EMAIL, google_chat.MESSAGES, google_chat.SPACES]
)
def test_a_declined_core_scope_connects_nothing(transport, lab_users, missing):
    lab, u = lab_users
    granted = " ".join(x for x in SCOPES.split() if x != missing)
    with pytest.raises(services.OAuthError) as err:
        connect_chat(transport, u["member"], lab, "2002", "member@example.test", granted)
    assert err.value.code == "scope_not_granted"
    assert not transport.sent("GET", google_chat.PROVIDER.identity_url)


def test_a_scope_chat_did_not_ask_for_is_refused(transport, lab_users):
    lab, u = lab_users
    extra = f"{CORE} https://www.googleapis.com/auth/drive.file"
    with pytest.raises(services.OAuthError) as err:
        connect_chat(transport, u["member"], lab, "2002", "member@example.test", extra)
    assert err.value.code == "unexpected_scope"


def test_spaces_and_link_need_manage_lab_integrations(transport, lab_users):
    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    url = reverse("labs:google-chat-spaces", args=[lab.pk])
    assert api(u["member"]).get(url).status_code == 403
    resp = api(u["member"]).put(
        reverse("labs:google-chat", args=[lab.pk]), {"space": SPACE}, format="json"
    )
    assert resp.status_code == 403
    assert not GoogleChatBridge.objects.for_lab(lab).exists()


def test_admin_lists_spaces_links_and_unlinks(transport, lab_users):
    lab, u = lab_users
    connect_chat(transport, u["lab_admin"], lab, "1001", "admin@example.test")
    transport.on(
        "GET",
        f"{API}/spaces",
        response(
            200,
            {
                "spaces": [
                    {"name": "spaces/B", "displayName": "Zebra"},
                    {"name": "spaces/A", "displayName": "alpha"},
                    {"name": "https://evil.test/x", "displayName": "bad"},
                ]
            },
        ),
    )
    client = api(u["lab_admin"])
    spaces = client.get(reverse("labs:google-chat-spaces", args=[lab.pk])).json()
    assert [s["name"] for s in spaces] == ["spaces/A", "spaces/B"]

    transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
    url = reverse("labs:google-chat", args=[lab.pk])
    body = client.put(url, {"space": SPACE}, format="json").json()
    assert body["bridge"]["space_name"] == "Lab"
    assert body["can_manage"] and body["connected"]
    assert AuditEvent.objects.filter(action=AuditAction.GOOGLE_CHAT_LINKED).exists()

    # Every member sees that it is linked, so the composer can say so.
    seen = api(u["viewer"]).get(url).json()
    assert seen["bridge"]["space"] == SPACE and not seen["can_manage"]

    assert client.delete(url).status_code == 204
    assert not GoogleChatBridge.objects.for_lab(lab).exists()
    assert AuditEvent.objects.filter(action=AuditAction.GOOGLE_CHAT_UNLINKED).exists()


def test_link_refuses_a_bad_space_name(transport, linked):
    lab, u, _, _ = linked
    resp = api(u["lab_admin"]).put(
        reverse("labs:google-chat", args=[lab.pk]), {"space": "spaces/../x"}, format="json"
    )
    assert resp.status_code == 400


def _posted(name):
    return response(200, {"name": name})


def test_a_member_with_google_chat_posts_as_themselves(transport, linked):
    lab, u, _, _ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m1"))
    message = lab_services.post_lab_message(
        lab=lab, by=u["member"], body="**Hi** @[Pat](user:00000000-0000-0000-0000-000000000000)"
    )
    (call,) = transport.sent("POST", MESSAGES)
    assert call["json"] == {"text": "*Hi* @Pat"}
    assert call["params"]["messageId"] == f"{sync.CLIENT_PREFIX}{message.pk}"
    assert call["headers"]["Authorization"] == "Bearer gc-at"
    message.refresh_from_db()
    assert message.external_id == f"{SPACE}/messages/m1"


def test_a_member_without_google_chat_is_posted_by_the_link_with_name_and_email(transport, linked):
    lab, u, _, _ = linked
    u["member"].display_name = "Robin Example"
    u["member"].save()
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m2"))
    lab_services.post_lab_message(lab=lab, by=u["member"], body="hello")
    (call,) = transport.sent("POST", MESSAGES)
    assert call["json"] == {"text": f"*Robin Example ({u['member'].email})* via labbenchos: hello"}


def test_a_member_with_no_name_is_relayed_by_email(transport, linked):
    lab, u, _, _ = linked
    u["member"].display_name = ""
    u["member"].save()
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m2"))
    lab_services.post_lab_message(lab=lab, by=u["member"], body="hello")
    (call,) = transport.sent("POST", MESSAGES)
    assert call["json"] == {"text": f"*{u['member'].email}* via labbenchos: hello"}


def test_a_member_not_in_the_space_falls_back_to_the_link(transport, linked):
    lab, u, _, _ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("POST", MESSAGES, response(403, {}), _posted(f"{SPACE}/messages/m3"))
    message = lab_services.post_lab_message(lab=lab, by=u["member"], body="hello")
    calls = transport.sent("POST", MESSAGES)
    assert len(calls) == 2 and calls[1]["json"]["text"].endswith("via labbenchos: hello")
    message.refresh_from_db()
    assert message.external_id == f"{SPACE}/messages/m3"


def test_nothing_is_relayed_without_a_link(transport, lab_users):
    lab, u = lab_users
    lab_services.post_lab_message(lab=lab, by=u["member"], body="hello")
    assert transport.calls == []


def _google(name, text, sender="users/9", kind="HUMAN", at="2099-01-01T00:00:01.123456789Z", **kw):
    return {
        "name": f"{SPACE}/messages/{name}",
        "text": text,
        "createTime": at,
        "sender": {"name": sender, "type": kind},
        **kw,
    }


def test_poll_brings_in_new_messages_once(transport, linked):
    lab, u, _, bridge = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on(
        "GET",
        MESSAGES,
        response(
            200,
            {
                "messages": [
                    _google("g1", "from a stranger"),
                    _google("g2", "from the member", sender="users/2002"),
                    _google("g3", "ours", clientAssignedMessageId=f"{sync.CLIENT_PREFIX}x"),
                    _google("g4", "a bot", kind="BOT"),
                    _google("g5", "sneaky @[Pat](user:00000000-0000-0000-0000-000000000000)"),
                    _google("g6", "x", name_override=True) | {"name": "spaces/OTHER/messages/1"},
                ]
            },
        ),
    )
    assert sync.poll_all() == 3
    rows = {m.external_id.rsplit("/", 1)[1]: m for m in LabChatMessage.objects.for_lab(lab)}
    assert set(rows) == {"g1", "g2", "g5"}
    assert rows["g1"].author is None and rows["g1"].external_author == sync.UNKNOWN_SENDER
    assert rows["g2"].author == u["member"] and rows["g2"].source == ChatSource.GOOGLE_CHAT
    assert "@[" not in rows["g5"].body  # can't draw a mention chip or notify anyone here
    # one read for what is new (it has a time filter), one for the reactions on the latest few
    (call,) = [c for c in transport.sent("GET", MESSAGES) if "filter" in c["params"]]
    assert call["params"]["filter"].startswith('createTime > "')
    bridge.refresh_from_db()
    assert bridge.cursor == "2099-01-01T00:00:01.123456Z" and bridge.last_error == ""

    assert sync.poll_all() == 0  # the same answer again adds nothing


def test_messages_from_google_show_in_the_lab_chat_api(transport, linked):
    lab, u, _, _ = linked
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    sync.poll_all()
    (row,) = api(u["viewer"]).get(reverse("labs:labchat-list", args=[lab.pk])).json()
    assert row["author"] is None and row["source"] == "google_chat"
    assert row["external_author"] == sync.UNKNOWN_SENDER


def test_disconnecting_the_link_connection_unlinks_the_chat(transport, linked):
    lab, u, account, bridge = linked
    url = reverse("labs:google-chat", args=[lab.pk])
    services.disconnect(account, actor=u["lab_admin"])
    account.refresh_from_db()
    assert account.status == AccountStatus.REVOKED
    assert not GoogleChatBridge.objects.for_lab(lab).exists()
    assert api(u["member"]).get(url).json()["bridge"] is None
    event = AuditEvent.objects.get(action=AuditAction.GOOGLE_CHAT_UNLINKED)
    assert event.actor is None and event.metadata["space"] == SPACE
    transport.calls.clear()
    assert sync.poll_all() == 0
    lab_services.post_lab_message(lab=lab, by=u["member"], body="hello")
    assert [c for c in transport.calls if "chat.googleapis.com" in c[1]] == []


def test_an_expired_link_connection_keeps_the_link_and_says_reconnect(transport, linked):
    lab, u, account, bridge = linked
    account.status = AccountStatus.EXPIRED  # revoked in Google: reconnecting resumes it
    account.save()
    assert sync.poll_all() == 0
    bridge.refresh_from_db()
    assert "no longer active" in bridge.last_error


def test_deleting_a_relayed_message_deletes_it_in_google(transport, linked):
    lab, u, _, _ = linked
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m9"))
    message = lab_services.post_lab_message(lab=lab, by=u["member"], body="oops")
    message.refresh_from_db()
    transport.on("DELETE", f"{MESSAGES}/m9", response(200, {}))
    lab_services.delete_lab_message(message=message, by=u["member"])
    assert len(transport.sent("DELETE", f"{MESSAGES}/m9")) == 1


def test_deleting_a_message_from_google_only_removes_it_here(transport, linked):
    lab, u, _, _ = linked
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    sync.poll_all()
    message = LabChatMessage.objects.for_lab(lab).get()
    lab_services.delete_lab_message(message=message, by=u["lab_admin"])
    assert not [c for c in transport.calls if c[0] == "DELETE"]
    assert not LabChatMessage.objects.for_lab(lab).exists()


# ---------------------------------------------------------------- names and thread import (D320)

PEOPLE = f"{google_chat.PEOPLE}/people:batchGet"


def _people(*pairs):
    return response(
        200,
        {
            "responses": [
                {"person": {"resourceName": f"people/{i}", "names": [{"displayName": n}]}}
                for i, n in pairs
            ]
        },
    )


def test_poll_names_strangers_from_the_directory(transport, linked):
    lab, *_ = linked
    transport.on("GET", PEOPLE, _people(("9", "Dana Example")))
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    sync.poll_all()
    assert LabChatMessage.objects.for_lab(lab).get().external_author == "Dana Example"
    (call,) = transport.sent("GET", PEOPLE)
    assert call["params"]["resourceNames"] == ["people/9"]


def test_without_the_optional_scopes_senders_and_group_chats_still_work(transport, lab_users):
    """No directory or membership call is made (the fake transport fails any unexpected one)."""
    lab, u = lab_users
    connect_chat(transport, u["lab_admin"], lab, "1001", "admin@example.test", CORE)
    transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
    sync.link_space(lab=lab, by=u["lab_admin"], space=SPACE)
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    sync.poll_all()
    assert LabChatMessage.objects.for_lab(lab).get().external_author == sync.UNKNOWN_SENDER
    group = {"name": "spaces/GRP1", "spaceType": "GROUP_CHAT"}
    transport.on("GET", f"{API}/spaces", response(200, {"spaces": [group]}))
    [row] = sync.list_spaces(lab, u["lab_admin"])
    assert row["display_name"] == "Group chat" and row["members"] == []
    asked = [url for _, url, _ in transport.calls]
    assert not [x for x in asked if "people.googleapis.com" in x or x.endswith("/members")]


THREAD = f"{SPACE}/threads/T1"


@pytest.fixture
def project(lab_users):
    from projects.models import Project, ProjectMembership, ProjectRole

    lab, u = lab_users
    p = Project.objects.create(lab=lab, name="Atlas", created_by=u["pi"])
    ProjectMembership.objects.create(lab=lab, project=p, user=u["member"], role=ProjectRole.LEAD)
    return p


def test_threads_are_listed_newest_first(transport, lab_users, project):
    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    newest_first = [
        _google("m3", "later", at="2099-01-03T00:00:00Z") | {"thread": {"name": THREAD}},
        _google("m2", "other", at="2099-01-02T00:00:00Z")
        | {"thread": {"name": f"{SPACE}/threads/T2"}},
        _google("m1", "opening words", at="2099-01-01T00:00:00Z") | {"thread": {"name": THREAD}},
        _google("x", "elsewhere") | {"thread": {"name": "spaces/OTHER/threads/T9"}},
    ]
    transport.on("GET", MESSAGES, response(200, {"messages": newest_first}))
    url = reverse("projects:project-google-chat-threads", args=[lab.pk, project.pk])
    rows = api(u["member"]).get(url, {"space": SPACE}).json()
    assert [(r["name"], r["first"], r["count"]) for r in rows] == [
        (THREAD, "opening words", 2),
        (f"{SPACE}/threads/T2", "other", 1),
    ]


def test_importing_a_thread_brings_its_messages_into_the_project_chat(
    transport, lab_users, project
):
    from projects.models import ChatMessage

    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("GET", PEOPLE, _people(("9", "Dana Example")))
    msgs = [
        _google("m1", "Shall we rerun?", at="2026-01-01T10:00:00Z") | {"thread": {"name": THREAD}},
        _google("m2", "Yes", sender="users/2002", at="2026-01-01T10:05:00Z")
        | {"thread": {"name": THREAD}},
        _google("m3", "not this thread") | {"thread": {"name": f"{SPACE}/threads/T2"}},
        _google("m4", "a bot", kind="BOT") | {"thread": {"name": THREAD}},
    ]
    transport.on("GET", MESSAGES, response(200, {"messages": msgs}))
    url = reverse("projects:project-google-chat-import", args=[lab.pk, project.pk])
    resp = api(u["member"]).post(url, {"space": SPACE, "thread": THREAD}, format="json")
    assert resp.json() == {"imported": 2, "skipped": 0}
    rows = list(ChatMessage.objects.for_lab(lab).filter(project=project).order_by("created_at"))
    assert [(r.author, r.external_author, r.body) for r in rows] == [
        (None, "Dana Example", "Shall we rerun?"),
        (u["member"], "", "Yes"),
    ]
    # They keep their own times, so they sit in the history where they were said.
    assert rows[0].created_at.isoformat().startswith("2026-01-01T10:00")
    assert all(r.source == ChatSource.GOOGLE_CHAT for r in rows)
    (call,) = transport.sent("GET", MESSAGES)
    assert call["params"]["filter"] == f'thread.name = "{THREAD}"'
    # Imported messages are never sent back to Google, and a second import adds nothing.
    assert not transport.sent("POST", MESSAGES)
    again = api(u["member"]).post(url, {"space": SPACE, "thread": THREAD}, format="json")
    assert again.json() == {"imported": 0, "skipped": 2}
    assert AuditEvent.objects.filter(action=AuditAction.GOOGLE_CHAT_IMPORTED).count() == 2


def test_importing_into_the_lab_chat_needs_manage_lab_integrations(transport, lab_users):
    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    url = reverse("labs:google-chat-import", args=[lab.pk])
    assert api(u["member"]).post(url, {"space": SPACE}, format="json").status_code == 403

    connect_chat(transport, u["lab_admin"], lab, "1001", "admin@example.test")
    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("m1", "hello")]}))
    resp = api(u["lab_admin"]).post(url, {"space": SPACE}, format="json")
    assert resp.json() == {"imported": 1, "skipped": 0}
    assert LabChatMessage.objects.for_lab(lab).get().body == "hello"


def test_import_refuses_a_thread_from_another_space(transport, lab_users, project):
    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    url = reverse("projects:project-google-chat-import", args=[lab.pk, project.pk])
    resp = api(u["member"]).post(
        url, {"space": SPACE, "thread": "spaces/OTHER/threads/T1"}, format="json"
    )
    assert resp.status_code == 400
    assert not [c for c in transport.calls if "chat.googleapis.com" in c[1]]


def test_a_display_name_cannot_pass_for_someone_else_in_google(transport, linked):
    lab, u, _, _ = linked
    u["member"].display_name = "*Prof. Alice*\nsays"
    u["member"].save()
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m5"))
    lab_services.post_lab_message(lab=lab, by=u["member"], body="hi")
    (call,) = transport.sent("POST", MESSAGES)
    assert call["json"]["text"] == (f"*Prof. Alice says ({u['member'].email})* via labbenchos: hi")


def test_a_google_account_shared_by_two_members_credits_neither(transport, linked):
    lab, u, _, _ = linked
    connect_chat(transport, u["member"], lab, "2002", "shared@example.test")
    connect_chat(transport, u["viewer"], lab, "2002", "shared@example.test")
    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    transport.on(
        "GET", MESSAGES, response(200, {"messages": [_google("g1", "hi", sender="users/2002")]})
    )
    sync.poll_all()
    row = LabChatMessage.objects.for_lab(lab).get()
    assert row.author is None


def test_inbound_messages_are_capped_per_hour(transport, linked, monkeypatch):
    lab, _, _, bridge = linked
    monkeypatch.setattr(sync, "INBOUND_PER_HOUR", 1)
    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    first = _google("g1", "one", at="2099-01-01T00:00:01Z")
    second = _google("g2", "two", at="2099-01-01T00:00:02Z")
    transport.on("GET", MESSAGES, response(200, {"messages": [first, second]}))
    assert sync.poll_all() == 1
    bridge.refresh_from_db()
    assert bridge.cursor == "2099-01-01T00:00:01.000000Z" and bridge.last_error.startswith("Paused")


# ------------------------------------------------------- group chats and project chats (D325)

GROUP = "spaces/GRP1"
GROUP_MESSAGES = f"{API}/{GROUP}/messages"


def test_group_chats_and_messages_are_listed_by_their_members(transport, lab_users):
    lab, u = lab_users
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on(
        "GET",
        f"{API}/spaces",
        response(
            200,
            {
                "spaces": [
                    {"name": "spaces/S1", "displayName": "Lab", "spaceType": "SPACE"},
                    {
                        "name": GROUP,
                        "spaceType": "GROUP_CHAT",
                        "lastActiveTime": "2099-01-02T00:00:00Z",
                    },
                    {
                        "name": "spaces/DM1",
                        "spaceType": "DIRECT_MESSAGE",
                        "lastActiveTime": "2099-01-01T00:00:00Z",
                    },
                ]
            },
        ),
    )
    members = lambda *ids: response(  # noqa: E731
        200, {"memberships": [{"member": {"name": f"users/{i}"}} for i in ids]}
    )
    transport.on("GET", f"{API}/{GROUP}/members", members("2002", "9", "8"))
    transport.on("GET", f"{API}/spaces/DM1/members", members("2002", "9"))
    transport.on("GET", PEOPLE, _people(("9", "Dana Example"), ("8", "Eli Example")))
    url = reverse("projects:project-google-chat-spaces", args=[lab.pk, _project(lab, u).pk])
    rows = api(u["member"]).get(url).json()
    assert rows == [
        {"name": "spaces/S1", "display_name": "Lab", "kind": "space", "members": []},
        {
            "name": GROUP,
            "display_name": "Dana Example, Eli Example",
            "kind": "group_chat",
            "members": ["Dana Example", "Eli Example"],
        },
        {
            "name": "spaces/DM1",
            "display_name": "Dana Example",
            "kind": "direct_message",
            "members": ["Dana Example"],
        },
    ]


def _project(lab, u):
    from projects.models import Project, ProjectMembership, ProjectRole

    p = Project.objects.for_lab(lab).filter(name="Sync").first()
    if p is None:
        p = Project.objects.create(lab=lab, name="Sync", created_by=u["pi"])
        ProjectMembership.objects.create(
            lab=lab, project=p, user=u["member"], role=ProjectRole.LEAD
        )
    return p


@pytest.fixture
def project_linked(transport, lab_users):
    """A project lead links their project's chat to a group chat."""
    lab, u = lab_users
    p = _project(lab, u)
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("GET", f"{API}/{GROUP}", response(200, {"name": GROUP, "spaceType": "GROUP_CHAT"}))
    transport.on("GET", f"{API}/{GROUP}/members", response(200, {"memberships": []}))
    url = reverse("projects:project-google-chat", args=[lab.pk, p.pk])
    resp = api(u["member"]).put(url, {"space": GROUP}, format="json")
    assert resp.status_code == 200, resp.content
    return lab, u, p


def test_a_project_chat_syncs_with_its_own_conversation(transport, project_linked):
    from projects import services as project_services
    from projects.models import ChatMessage

    lab, u, p = project_linked
    transport.on("POST", GROUP_MESSAGES, _posted(f"{GROUP}/messages/p1"))
    message = project_services.post_message(project=p, by=u["member"], body="hello project")
    (call,) = transport.sent("POST", GROUP_MESSAGES)
    assert call["json"] == {"text": "hello project"}
    message.refresh_from_db()
    assert message.external_id == f"{GROUP}/messages/p1"

    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    item = _google("x", "from google") | {"name": f"{GROUP}/messages/x"}
    transport.on("GET", GROUP_MESSAGES, response(200, {"messages": [item]}))
    sync.poll_all()
    row = ChatMessage.objects.for_lab(lab).get(source=ChatSource.GOOGLE_CHAT)
    assert row.project == p and row.author is None and row.body == "from google"
    # The lab chat is untouched.
    assert not LabChatMessage.objects.for_lab(lab).exists()
    # Everyone on the project sees the link; it arrives in the project chat API.
    seen = api(u["pi"]).get(reverse("projects:project-google-chat", args=[lab.pk, p.pk])).json()
    assert seen["bridge"]["space"] == GROUP


def test_only_project_editors_link_a_project_chat(transport, lab_users):
    from projects.models import ProjectMembership, ProjectRole

    lab, u = lab_users
    p = _project(lab, u)
    ProjectMembership.objects.create(lab=lab, project=p, user=u["viewer"], role=ProjectRole.VIEWER)
    url = reverse("projects:project-google-chat", args=[lab.pk, p.pk])
    assert api(u["viewer"]).get(url).status_code == 200
    assert api(u["viewer"]).put(url, {"space": GROUP}, format="json").status_code == 403


def test_one_conversation_can_feed_several_chats(transport, linked):
    lab, u, _, _ = linked  # the lab chat is linked to SPACE
    p = _project(lab, u)
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
    url = reverse("projects:project-google-chat", args=[lab.pk, p.pk])
    resp = api(u["member"]).put(url, {"space": SPACE}, format="json")
    assert resp.status_code == 200, resp.content


def test_a_message_written_in_one_linked_chat_reaches_the_other(transport, linked):
    from projects import services as project_services
    from projects.models import ChatMessage

    lab, u, _, _ = linked
    p = _project(lab, u)
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
    url = reverse("projects:project-google-chat", args=[lab.pk, p.pk])
    assert api(u["member"]).put(url, {"space": SPACE}, format="json").status_code == 200

    # Written in the project chat; posted to Google under the app's own message id.
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/p1"))
    written = project_services.post_message(project=p, by=u["member"], body="from the project")
    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    echo = _google(
        "p1", "from the project", clientAssignedMessageId=f"{sync.CLIENT_PREFIX}{written.pk}"
    )
    transport.on(
        "GET", MESSAGES, response(200, {"messages": [echo | {"name": f"{SPACE}/messages/p1"}]})
    )
    sync.poll_all()

    # The lab chat takes it in under the writer's name; the project chat does not get a copy.
    lab_row = LabChatMessage.objects.for_lab(lab).get(external_id=f"{SPACE}/messages/p1")
    assert lab_row.author == u["member"] and lab_row.body == "from the project"
    assert ChatMessage.objects.for_lab(lab).filter(project=p).count() == 1


def test_importing_a_whole_group_chat(transport, lab_users):
    from projects.models import ChatMessage

    lab, u = lab_users
    p = _project(lab, u)
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("GET", PEOPLE, response(200, {"responses": []}))
    newest_first = [
        _google("b", "second", at="2026-01-01T10:05:00Z") | {"name": f"{GROUP}/messages/b"},
        _google("a", "first", at="2026-01-01T10:00:00Z") | {"name": f"{GROUP}/messages/a"},
    ]
    transport.on("GET", GROUP_MESSAGES, response(200, {"messages": newest_first}))
    url = reverse("projects:project-google-chat-import", args=[lab.pk, p.pk])
    resp = api(u["member"]).post(url, {"space": GROUP}, format="json")
    assert resp.json() == {"imported": 2, "skipped": 0}, resp.content
    bodies = list(
        ChatMessage.objects.for_lab(lab)
        .filter(project=p)
        .order_by("created_at")
        .values_list("body", flat=True)
    )
    assert bodies == ["first", "second"]


def _reacts(**counts):
    return {
        "emojiReactionSummaries": [
            {"emoji": {"unicode": e}, "reactionCount": n} for e, n in counts.items()
        ]
    }


def test_reactions_from_google_show_with_the_message_and_keep_up_to_date(transport, linked):
    lab, u, *_ = linked
    transport.on(
        "GET",
        MESSAGES,
        response(
            200,
            {
                "messages": [
                    _google(
                        "g1",
                        "hi",
                        emojiReactionSummaries=[
                            {"emoji": {"unicode": "👍"}, "reactionCount": 2},
                            {"emoji": {"customEmoji": {"uid": "x"}}, "reactionCount": 5},
                            {"emoji": {"unicode": "<b>"}, "reactionCount": 1},  # not an emoji
                        ],
                    )
                ]
            },
        ),
    )
    sync.poll_all()
    message = LabChatMessage.objects.for_lab(lab).get()
    assert message.external_reactions == {"👍": 2}  # custom and non-emoji left out
    (row,) = api(u["member"]).get(reverse("labs:labchat-list", args=[lab.pk])).json()
    assert row["reactions"] == [{"emoji": "👍", "count": 2, "mine": False, "people": []}]

    # someone adds a heart later; the message is older than the cursor, but is read again
    from django.core.cache import cache

    cache.clear()
    transport.on(
        "GET",
        MESSAGES,
        response(200, {"messages": [_google("g1", "hi", **_reacts(**{"👍": 2, "❤️": 1}))]}),
    )
    sync.poll_all()
    message.refresh_from_db()
    assert message.external_reactions == {"👍": 2, "❤️": 1}


def test_a_reaction_made_here_adds_to_the_ones_from_google(transport, linked):
    from core import reactions

    lab, u, *_ = linked
    transport.on(
        "GET", MESSAGES, response(200, {"messages": [_google("g1", "hi", **_reacts(**{"👍": 2}))]})
    )
    sync.poll_all()
    message = LabChatMessage.objects.for_lab(lab).get()
    reactions.toggle(LabChatMessage.objects.for_lab(lab), message.pk, u["member"], "👍")
    message.refresh_from_db()
    names = {str(u["member"].pk): "Member Example"}
    assert reactions.summary(message.reactions, u["member"], message.external_reactions, names) == [
        {"emoji": "👍", "count": 3, "mine": True, "people": ["Member Example"]}
    ]
    assert reactions.summary(message.reactions, u["pi"], message.external_reactions, names) == [
        {"emoji": "👍", "count": 3, "mine": False, "people": ["Member Example"]}
    ]


def test_profile_pictures_come_in_for_strangers_and_members(transport, linked):
    lab, u, *_ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    pic = "https://lh3.googleusercontent.com/a/photo=s64"
    transport.on(
        "GET",
        PEOPLE,
        response(
            200,
            {
                "responses": [
                    {
                        "person": {
                            "resourceName": f"people/{i}",
                            "names": [{"displayName": n}],
                            "photos": [{"url": pic}],
                        }
                    }
                    for i, n in (("9", "Dana Example"), ("2002", "Member Example"))
                ]
            },
        ),
    )
    transport.on(
        "GET",
        MESSAGES,
        response(
            200,
            {
                "messages": [
                    _google("g1", "from a stranger"),
                    _google("g2", "from the member", sender="users/2002"),
                ]
            },
        ),
    )
    sync.poll_all()
    rows = {m.external_id.rsplit("/", 1)[1]: m for m in LabChatMessage.objects.for_lab(lab)}
    assert rows["g1"].external_avatar == pic
    # the member's message keeps their account as author, with Google's picture as a fallback
    assert rows["g2"].author == u["member"] and rows["g2"].external_avatar == pic


def test_mentions_become_real_google_mentions_where_google_can_name_them(transport, linked):
    lab, u, *_ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m9"))
    member = f"@[Member](user:{u['member'].pk})"  # connected: Google can name them
    pi = f"@[Pat](user:{u['pi'].pk})"  # not connected: plain text
    dana = "@[Dana](gchat:777)"  # only in the Google space
    lab_services.post_lab_message(lab=lab, by=u["member"], body=f"{member} {pi} {dana}")
    (call,) = transport.sent("POST", MESSAGES)
    assert call["json"] == {"text": "<users/2002> @Pat <users/777>"}


def test_a_google_mention_notifies_no_one_here_and_is_shown_as_a_name(transport, linked):
    from core.models import Notification

    lab, u, *_ = linked
    transport.on("POST", MESSAGES, _posted(f"{SPACE}/messages/m8"))
    message = lab_services.post_lab_message(lab=lab, by=u["member"], body="hi @[Dana](gchat:777)")
    assert message.body == "hi @[Dana](gchat:777)"
    assert not Notification.objects.for_lab(lab).filter(kind="mention").exists()


def test_the_space_people_list_leaves_out_members_connected_here(transport, linked):
    lab, u, *_ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on(
        "GET",
        f"{API}/{SPACE}/members",
        response(
            200,
            {
                "memberships": [
                    {"member": {"name": "users/2002", "displayName": "Member Example"}},
                    {"member": {"name": "users/777", "displayName": "Dana Example"}},
                    {"member": {"name": "users/555", "displayName": "A Bot", "type": "BOT"}},
                    {"member": {"name": "users/not-a-number", "displayName": "Odd"}},
                ]
            },
        ),
    )
    url = reverse("labs:google-chat-people", args=[lab.pk])
    assert api(u["viewer"]).get(url).json() == [{"id": "777", "name": "Dana Example"}]


def test_no_space_people_without_a_link(transport, lab_users):
    lab, u = lab_users
    url = reverse("labs:google-chat-people", args=[lab.pk])
    assert api(u["viewer"]).get(url).json() == []


def test_space_people_are_named_from_the_directory_when_google_sends_only_ids(transport, linked):
    lab, u, *_ = linked
    transport.on(
        "GET",
        f"{API}/{SPACE}/members",
        response(
            200,
            {"memberships": [{"member": {"name": "users/777"}}, {"member": {"name": "users/888"}}]},
        ),
    )
    transport.on("GET", PEOPLE, _people(("777", "Dana Example"), ("888", "Eli Example")))
    url = reverse("labs:google-chat-people", args=[lab.pk])
    assert api(u["viewer"]).get(url).json() == [
        {"id": "777", "name": "Dana Example"},
        {"id": "888", "name": "Eli Example"},
    ]


def test_repair_gives_members_their_google_picture_too(transport, linked):
    from django.core.cache import cache

    lab, u, *_ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    transport.on(
        "GET", MESSAGES, response(200, {"messages": [_google("g2", "hi", sender="users/2002")]})
    )
    sync.poll_all()  # no directory answer yet: the message comes in without a picture
    message = LabChatMessage.objects.for_lab(lab).get()
    assert message.external_avatar == ""
    pic = "https://lh3.googleusercontent.com/a/photo=s64"
    transport.on(
        "GET",
        PEOPLE,
        response(
            200,
            {
                "responses": [
                    {
                        "person": {
                            "resourceName": "people/2002",
                            "names": [{"displayName": "Member Example"}],
                            "photos": [{"url": pic}],
                        }
                    }
                ]
            },
        ),
    )
    cache.clear()
    sync.poll_all()
    message.refresh_from_db()
    assert message.external_avatar == pic and message.author == u["member"]


def test_who_reacted_in_google_is_looked_up_and_shown_by_name(transport, linked):
    lab, u, *_ = linked
    connect_chat(transport, u["member"], lab, "2002", "member@example.test")
    u["member"].display_name = "Member Example"
    u["member"].save()
    transport.on("GET", PEOPLE, _people(("777", "Dana Example")))
    transport.on(
        "GET",
        MESSAGES,
        response(200, {"messages": [_google("g1", "hi", **_reacts(**{"👍": 2}))]}),
    )
    transport.on(
        "GET",
        f"{API}/{SPACE}/messages/g1/reactions",
        response(
            200,
            {
                "reactions": [
                    {"emoji": {"unicode": "👍"}, "user": {"name": "users/2002", "type": "HUMAN"}},
                    {"emoji": {"unicode": "👍"}, "user": {"name": "users/777", "type": "HUMAN"}},
                ]
            },
        ),
    )
    sync.poll_all()
    message = LabChatMessage.objects.for_lab(lab).get()
    assert message.external_reactions == {
        "👍": {"count": 2, "by": ["Member Example", "Dana Example"]}
    }
    (row,) = api(u["viewer"]).get(reverse("labs:labchat-list", args=[lab.pk])).json()
    assert row["reactions"] == [
        {"emoji": "👍", "count": 2, "mine": False, "people": ["Member Example", "Dana Example"]}
    ]


def test_people_who_reacted_here_are_named_for_everyone_who_reads(transport, linked):
    lab, u, *_ = linked
    u["member"].display_name = "Member Example"
    u["member"].save()
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    sync.poll_all()
    message = LabChatMessage.objects.for_lab(lab).get()
    api(u["member"]).post(
        reverse("labs:labchat-reactions", args=[lab.pk, message.pk]), {"emoji": "❤️"}, format="json"
    )
    (row,) = api(u["viewer"]).get(reverse("labs:labchat-list", args=[lab.pk])).json()
    assert row["reactions"] == [
        {"emoji": "❤️", "count": 1, "mine": False, "people": ["Member Example"]}
    ]
