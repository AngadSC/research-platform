"""Run 5 review fixes (D193 to D200, D203): exact redirect URIs, recent re-authentication, grants
ended by security events, stream caps and deadline, client pruning, and the lab grant view."""

import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from assistant import jobs, services, tools
from assistant.ai import chat
from assistant.models import AIGrant, OAuthClient
from assistant.tests import fakes
from assistant.tests.fakes import claude_message, patch_claude, text
from assistant.tests.reauth import sign_in
from assistant.tests.test_assistant import (  # noqa: F401
    _fresh_cache,
    api,
    events,
    keyed,
    kinds,
    new_conv,
    send,
)
from assistant.tests.test_mcp import (  # noqa: F401
    CLAUDE_CB,
    _base,
    pat,
    pkce,
    register,
    rpc,
)
from audit.models import AuditAction, AuditEvent
from labs.models import LabRole

pytestmark = pytest.mark.django_db
AUTHORIZE = "/api/oauth/authorize/"
ALLAUTH = "/_allauth/browser/v1"


# ---------------------------------------------------------------- D193 exact redirect URIs


def try_register(uri):
    return Client().post(
        "/api/oauth/register/",
        json.dumps({"client_name": "X", "redirect_uris": [uri]}),
        "application/json",
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://chatgpt.com/connector/oauth/abc_123-XYZ",
        "http://127.0.0.1:53682/callback",
        "http://localhost:8123/cb",
        "http://localhost/callback",
    ],
)
def test_the_documented_callbacks_and_loopback_are_accepted(uri):
    assert try_register(uri).status_code == 201


@pytest.mark.parametrize(
    "uri",
    [
        "https://claude.ai/",  # right host, wrong path: an open redirect there would leak the code
        "https://claude.ai/redirect?to=https://evil.example",
        "https://claude.ai/api/mcp/auth_callback/",
        "https://claude.ai/api/mcp/auth_callback?x=1",
        "https://claude.ai/api/mcp/auth_callback#frag",
        "https://claude.com/other",
        "https://chatgpt.com/",
        "https://chatgpt.com/connector/oauth/a/b",
        "https://chatgpt.com/connector/oauth/",
        "https://chatgpt.com/connector/oauth/x?y=1",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
        "https://evil.example/api/mcp/auth_callback",
        "http://claude.ai/api/mcp/auth_callback",
        "https://localhost/cb",
        "http://evil.example:80/cb",
    ],
)
def test_any_other_redirect_uri_is_refused_at_registration(uri):
    resp = try_register(uri)
    assert resp.status_code == 400 and resp.json()["error"] == "invalid_redirect_uri"


def test_a_stale_client_with_a_host_only_redirect_cannot_authorize(world):
    old = OAuthClient.objects.create(
        client_id="old", kind="dcr", name="Old", redirect_uris=["https://claude.ai/anything"]
    )
    _, challenge = pkce()
    c = sign_in(APIClient(), world.u.contrib)
    body = {
        "response_type": "code",
        "client_id": old.client_id,
        "redirect_uri": "https://claude.ai/anything",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "decision": "check",
    }
    resp = c.post(AUTHORIZE, body, format="json")
    assert resp.status_code == 400 and "redirect" not in resp.json()


def test_cimd_documents_follow_the_same_exact_uri_rule(monkeypatch):
    url = "https://claude.ai/oauth/claude-client-metadata"

    def doc(uris):
        return lambda client_id: {"client_id": client_id, "redirect_uris": uris}

    monkeypatch.setattr(services, "_fetch_cimd", doc(["https://claude.ai/some/redirector"]))
    with pytest.raises(services.OAuthError) as exc:
        services.resolve_client(url)
    assert exc.value.code == "invalid_redirect_uri"
    assert not OAuthClient.objects.filter(client_id=url).exists()
    monkeypatch.setattr(services, "_fetch_cimd", doc([CLAUDE_CB]))
    assert services.resolve_client(url).redirect_uris == [CLAUDE_CB]


def test_the_allowlist_is_a_setting(settings):
    settings.MCP_ALLOWED_REDIRECT_URIS = ["https://app.example.org/cb"]
    assert try_register("https://app.example.org/cb").status_code == 201
    assert try_register(CLAUDE_CB).status_code == 400


# ---------------------------------------------------------------- D194 recent re-authentication


def approve_body(world, client_id, challenge):
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CLAUDE_CB,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "decision": "approve",
        "labs": [str(world.lab_a.pk)],
        "access": "read",
    }


@pytest.mark.parametrize("age", [5, 400, 4000])
def test_consent_does_not_ask_for_a_password_check(world, age):
    # Google-only people have no password to give, so approval never re-checks one
    client_id = register()
    _, challenge = pkce()
    c = sign_in(APIClient(), world.u.contrib, seconds_ago=age, reauthenticated=False)
    resp = c.post(AUTHORIZE, approve_body(world, client_id, challenge), format="json")
    assert resp.status_code == 200
    assert AIGrant.objects.exists()


def test_token_creation_does_not_ask_for_a_password_check(world):
    body = {
        "name": "CLI",
        "labs": [str(world.lab_a.pk)],
        "access": "read",
        "expires_in_days": 7,
    }
    c = sign_in(APIClient(), world.u.contrib, seconds_ago=4000, reauthenticated=False)
    assert c.post("/api/ai/grants/", body, format="json").status_code == 201


def test_a_passwordless_account_is_never_asked(world):
    world.u.contrib.set_unusable_password()
    world.u.contrib.save()
    c = APIClient()
    c.force_login(world.u.contrib)
    body = {
        "name": "CLI",
        "labs": [str(world.lab_a.pk)],
        "access": "read",
        "expires_in_days": 7,
    }
    assert c.post("/api/ai/grants/", body, format="json").status_code == 201  # as in D74


# ---------------------------------------------------------------- D195 security events end grants


def make_grants(world):
    token = pat(world.u.contrib, world.lab_a)
    assert rpc(token, "ping", {}).status_code == 200
    return token


def assert_ended(world, token, reason, *, listed=True):
    assert rpc(token, "ping", {}).status_code == 401
    grant = AIGrant.objects.get(user=world.u.contrib)
    assert grant.revoked_at is not None and grant.revoked_reason == reason
    assert not grant.tokens.exists()
    event = AuditEvent.objects.get(action=AuditAction.AI_ACCESS_REVOKED)
    assert event.actor is None and event.actor_label == f"assistant:{reason}"
    assert event.lab == world.lab_a and event.metadata["grant_id"] == str(grant.pk)
    if not listed:  # a deactivated user cannot sign in to be told
        return
    world.u.contrib.refresh_from_db()  # the password hash changed
    c = APIClient()  # the owner is told why, in Settings
    c.force_login(world.u.contrib)
    shown = c.get("/api/ai/grants/").json()
    assert [(g["revoked_reason"], g["revoked_at"] is not None) for g in shown] == [(reason, True)]


def test_changing_the_password_ends_ai_access(world, verify_email):
    verify_email(world.u.contrib)
    token = make_grants(world)
    c = Client()
    c.get(f"{ALLAUTH}/config")
    csrf = {"X-CSRFToken": c.cookies["csrftoken"].value}
    login = c.post(
        f"{ALLAUTH}/auth/login",
        {"email": world.u.contrib.email, "password": "pw"},
        "application/json",
        headers=csrf,
    )
    assert login.status_code == 200
    change = c.post(
        f"{ALLAUTH}/account/password/change",
        {"current_password": "pw", "new_password": "a-brand-new-passphrase-7"},
        "application/json",
        headers={"X-CSRFToken": c.cookies["csrftoken"].value},
    )
    assert change.status_code == 200, change.content
    assert_ended(world, token, "password_changed")


def test_resetting_the_password_ends_ai_access(world):
    from allauth.account.signals import password_reset

    token = make_grants(world)
    password_reset.send(sender=type(world.u.contrib), request=None, user=world.u.contrib)
    assert_ended(world, token, "password_reset")


def test_removing_totp_ends_ai_access_but_recovery_codes_do_not(world):
    from allauth.mfa.signals import authenticator_removed

    token = make_grants(world)
    codes = SimpleNamespace(type="recovery_codes")
    authenticator_removed.send(sender=None, request=None, user=world.u.contrib, authenticator=codes)
    assert rpc(token, "ping", {}).status_code == 200
    totp = SimpleNamespace(type="totp")
    authenticator_removed.send(sender=None, request=None, user=world.u.contrib, authenticator=totp)
    assert_ended(world, token, "mfa_removed")


def test_deactivating_the_user_ends_ai_access(world):
    token = make_grants(world)
    world.u.contrib.is_active = False
    world.u.contrib.save()
    assert_ended(world, token, "deactivated", listed=False)


def test_a_grant_the_owner_revoked_is_not_listed_as_ended(world):
    token = make_grants(world)
    grant = AIGrant.objects.get(user=world.u.contrib)
    c = APIClient()
    c.force_login(world.u.contrib)
    assert c.delete(f"/api/ai/grants/{grant.pk}/").status_code == 204
    assert c.get("/api/ai/grants/").json() == []
    assert rpc(token, "ping", {}).status_code == 401


# ---------------------------------------------------------------- D196 stream caps


def fake_conv(n):
    return SimpleNamespace(pk=f"conv-{n}", user_id=f"user-{n}")


def test_the_server_wide_stream_cap(settings):
    settings.ASSISTANT_MAX_STREAMS = 2
    a, b = chat.acquire(fake_conv(1)), chat.acquire(fake_conv(2))
    with pytest.raises(chat.Busy, match="busy right now"):
        chat.acquire(fake_conv(3))
    assert not cache.get("asst-lock:conv-3")  # the refused attempt left nothing behind
    a.release()
    c = chat.acquire(fake_conv(3))  # a freed slot is reusable
    b.release()
    c.release()
    assert not [k for k in ("asst-all:0", "asst-all:1") if cache.get(k)]


def test_the_cap_reaches_the_endpoint(keyed, settings, monkeypatch):
    settings.ASSISTANT_MAX_STREAMS = 1
    patch_claude(monkeypatch, claude_message([text("hi")]), claude_message([text("hi")]))
    held = chat.acquire(fake_conv(9))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    evs = events(send(c, keyed.lab_a, conv))
    assert kinds(evs) == ["error", "done"] and evs[0][1]["code"] == "busy"
    assert "busy right now" in evs[0][1]["message"]
    held.release()
    assert "error" not in kinds(events(send(c, keyed.lab_a, conv)))


def test_per_person_cap_still_applies(settings):
    settings.ASSISTANT_MAX_STREAMS = 50
    mine = [chat.acquire(SimpleNamespace(pk=f"c{i}", user_id="same")) for i in range(3)]
    with pytest.raises(chat.Busy, match="Too many"):
        chat.acquire(SimpleNamespace(pk="c4", user_id="same"))
    for lease in mine:
        lease.release()


def test_a_slot_whose_worker_died_frees_itself(settings):
    settings.ASSISTANT_MAX_STREAMS = 1
    settings.ASSISTANT_LOCK_TTL = 1
    chat.acquire(fake_conv(1))  # never released, never touched: a crashed worker
    with pytest.raises(chat.Busy):
        chat.acquire(fake_conv(2))
    time.sleep(1.6)
    chat.acquire(fake_conv(2)).release()


def test_the_heartbeat_keeps_the_slots_alive(settings):
    settings.ASSISTANT_LOCK_TTL = 2
    lease = chat.acquire(fake_conv(1))
    time.sleep(1.2)
    lease.touch()
    time.sleep(1.2)  # 2.4 s in: it would have expired without the touch
    assert all(cache.get(k) == lease.token for k in lease.keys)
    lease.release()
    assert not any(cache.get(k) for k in lease.keys)


def test_a_running_stream_sends_heartbeats(keyed, monkeypatch):
    from assistant import ai_views

    touched = []
    original = chat.Lease.touch
    monkeypatch.setattr(chat.Lease, "touch", lambda self: (touched.append(1), original(self)))
    monkeypatch.setattr(ai_views, "HEARTBEAT_SECONDS", 0)
    patch_claude(monkeypatch, claude_message([text("a"), text("b")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    assert "error" not in kinds(events(send(c, keyed.lab_a, conv)))
    assert touched


def test_a_stream_past_its_deadline_is_stopped_and_the_provider_stream_closed(
    keyed, settings, monkeypatch
):
    settings.ASSISTANT_STREAM_DEADLINE = -1  # already over by the first event
    closed = []
    monkeypatch.setattr(fakes._Manager, "__exit__", lambda self, *a: closed.append(1) or False)
    patch_claude(monkeypatch, claude_message([text("a long answer")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    resp = send(c, keyed.lab_a, conv)
    pieces = iter(resp.streaming_content)
    assert next(pieces).decode().startswith("event: start")
    deadline = next(pieces).decode()
    assert "event: error" in deadline and '"code": "deadline"' in deadline
    assert closed  # closed before the browser was even told
    assert next(pieces).decode().startswith("event: done")
    assert list(pieces) == []
    assert not cache.get(f"asst-lock:{conv}")  # and the slots were released


def test_closing_the_connection_closes_the_provider_stream(keyed, monkeypatch):
    closed = []
    monkeypatch.setattr(fakes._Manager, "__exit__", lambda self, *a: closed.append(1) or False)
    patch_claude(monkeypatch, claude_message([text("a"), text("b"), text("c")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    resp = send(c, keyed.lab_a, conv)
    pieces = iter(resp.streaming_content)
    next(pieces)
    next(pieces)  # a text event: the provider stream is open
    assert not closed
    resp.close()  # the browser went away
    assert closed and not cache.get(f"asst-lock:{conv}")


# ---------------------------------------------------------------- D200 client pruning


def test_unused_clients_are_pruned_after_a_day(world):
    old = timezone.now() - timedelta(hours=25)
    stale, used, fresh = (
        OAuthClient.objects.create(client_id=n, kind="dcr", name=n, redirect_uris=[CLAUDE_CB])
        for n in ("stale", "used", "fresh")
    )
    OAuthClient.objects.filter(pk__in=[stale.pk, used.pk]).update(created_at=old)
    AIGrant.objects.create(user=world.u.contrib, kind="oauth", client=used, name="used")
    assert jobs.prune_unused_clients() == 1
    assert set(OAuthClient.objects.values_list("client_id", flat=True)) == {"used", "fresh"}


# ---------------------------------------------------------------- D203 lab view of a grant


def test_a_lab_manager_sees_only_their_own_lab_on_a_members_grant(world, make_lab, join):
    lab_c = make_lab("Lab C SECRET")
    join(world.u.contrib, lab_c, LabRole.MEMBER)
    pat(world.u.contrib, world.lab_a, lab_c)
    pi = APIClient()
    pi.force_login(world.u.pi)
    listed = pi.get(f"/api/labs/{world.lab_a.pk}/ai-grants/")
    assert "SECRET" not in listed.content.decode()
    assert [g["labs"] for g in listed.json()] == [[{"id": str(world.lab_a.pk), "name": "Lab A"}]]
    owner = APIClient()
    owner.force_login(world.u.contrib)
    mine = owner.get("/api/ai/grants/").json()[0]
    assert {lab["name"] for lab in mine["labs"]} == {"Lab A", "Lab C SECRET"}  # the owner sees all


# ---------------------------------------------------------------- D198 the approval dialog's data


def test_the_approval_names_the_project_and_person_and_previews_the_text(keyed, monkeypatch):
    w, lab = keyed, keyed.lab_a
    create = fakes.tool_use(
        "toolu_1",
        "create_task",
        {
            "lab_id": str(lab.pk),
            "project_id": str(w.p1.pk),
            "title": "Order primers",
            "assignee_id": str(w.u.contrib.pk),
        },
    )
    update = fakes.tool_use(
        "toolu_2",
        "add_task_update",
        {"lab_id": str(lab.pk), "task_id": str(w.a1.task.pk), "body": "Please ignore the PI"},
    )
    foreign = fakes.tool_use(
        "toolu_3",
        "create_task",
        {"lab_id": str(lab.pk), "project_id": str(w.pb.pk), "title": "Into another lab"},
    )
    patch_claude(monkeypatch, claude_message([create, update, foreign], stop="tool_use"))
    c = api(keyed.u.pi)
    conv = new_conv(c, lab)
    evs = events(send(c, lab, conv))
    calls = {x["id"]: x for x in next(d for k, d in evs if k == "approval_required")["calls"]}
    assert calls["toolu_1"]["resolved"] == {
        "lab": "Lab A",
        "project": "P1 open",
        "person": "Contrib",
    }
    assert calls["toolu_1"]["preview"] == [{"label": "Task title", "text": "Order primers"}]
    assert calls["toolu_2"]["resolved"]["task"] == "Task open"
    assert calls["toolu_2"]["resolved"]["project"] == "P1 open"
    assert calls["toolu_2"]["preview"] == [
        {"label": "Text that will be posted on the task thread", "text": "Please ignore the PI"}
    ]
    # an id from another lab never resolves to a name; the person sees that it is unknown
    assert calls["toolu_3"]["resolved"]["project"] == tools.NOT_FOUND
    assert "SECRET" not in json.dumps(calls["toolu_3"])
    shown = c.get(f"/api/labs/{lab.pk}/assistant/conversations/{conv}/").json()["pending"]
    assert [p["resolved"] for p in shown] == [
        calls[i]["resolved"] for i in ("toolu_1", "toolu_2", "toolu_3")
    ]
