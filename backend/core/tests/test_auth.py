import importlib

import pytest
from allauth.account.models import EmailAddress
from django.test import Client, override_settings
from django.urls import clear_url_caches
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent

pytestmark = pytest.mark.django_db

CONFIG = "/_allauth/browser/v1/config"
LOGIN = "/_allauth/browser/v1/auth/login"


def test_anonymous_spa_gets_csrf_cookie_before_first_post(make_user):
    """The SPA reads the csrftoken cookie after GET config, then POSTs with X-CSRFToken."""
    client = Client(enforce_csrf_checks=True)
    assert client.post(LOGIN, {"email": "a@example.com", "password": "x"}).status_code == 403
    assert client.get(CONFIG).status_code == 200
    token = client.cookies["csrftoken"].value
    resp = client.post(
        LOGIN,
        {"email": "a@example.com", "password": "wrong"},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert resp.status_code == 400  # a normal credentials error, not a CSRF rejection


def test_login_logout_and_failed_login_are_audited(make_user):
    user = make_user(email="u@example.com")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client = Client()
    client.get(CONFIG)
    h = {"X-CSRFToken": client.cookies["csrftoken"].value}
    bad = client.post(
        LOGIN, {"email": "u@example.com", "password": "nope"}, "application/json", headers=h
    )
    assert bad.status_code == 400
    failed = AuditEvent.objects.get(action=AuditAction.AUTH_LOGIN_FAILED)
    assert failed.actor_label == "u@example.com" and "nope" not in str(failed.metadata)
    ok = client.post(
        LOGIN, {"email": "u@example.com", "password": "pw"}, "application/json", headers=h
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["data"]["user"]["email"] == "u@example.com"
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN, actor=user).count() == 1
    h = {"X-CSRFToken": client.cookies["csrftoken"].value}
    assert client.delete("/_allauth/browser/v1/auth/session", headers=h).status_code == 401
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_LOGOUT, actor=user).count() == 1


def test_unverified_email_cannot_log_in(make_user):
    user = make_user(email="v@example.com")
    EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)
    client = Client()
    client.get(CONFIG)
    h = {"X-CSRFToken": client.cookies["csrftoken"].value}
    resp = client.post(
        LOGIN, {"email": "v@example.com", "password": "pw"}, "application/json", headers=h
    )
    assert resp.status_code == 401  # allauth: pending email verification flow
    assert client.get("/api/me/").status_code in (401, 403)


def test_anonymous_api_call_is_401_with_authenticate_header():
    resp = APIClient().get("/api/me/")
    assert resp.status_code == 401 and resp["WWW-Authenticate"] == "Session"


def test_schema_is_mounted_only_in_debug():
    import config.urls

    def reload(debug):
        with override_settings(DEBUG=debug):
            importlib.reload(config.urls)
            clear_url_caches()
            return APIClient().get("/api/schema/").status_code

    try:
        assert reload(False) == 404
        assert reload(True) == 200
    finally:
        importlib.reload(config.urls)
        clear_url_caches()


@pytest.mark.django_db
def test_me_preferences_are_validated_and_merged(make_user):
    """D125: only known keys and values; PATCH merges into what's there."""
    from rest_framework.test import APIClient

    user = make_user()
    c = APIClient()
    c.force_authenticate(user)
    assert c.get("/api/me/").json()["preferences"] == {}
    assert c.patch("/api/me/", {"preferences": {"theme": "dark"}}, format="json").status_code == 200
    resp = c.patch("/api/me/", {"preferences": {"task_view": "list"}}, format="json")
    assert resp.json()["preferences"] == {"theme": "dark", "task_view": "list"}
    for bad in ({"theme": "neon"}, {"evil": "x"}, ["theme"]):
        assert c.patch("/api/me/", {"preferences": bad}, format="json").status_code == 400


@pytest.mark.django_db
def test_me_saved_links_are_validated(make_user):
    """Pins and recents are size-capped and only hold paths on this site."""
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(make_user())
    pin = {"url": "/labs/1/projects/2", "label": "Sleep"}
    recent = {**pin, "kind": "project", "at": "2026-11-08T12:00:00.000Z"}

    def status(**prefs):
        return c.patch("/api/me/", {"preferences": prefs}, format="json").status_code

    assert status(pins=[pin], recents=[recent]) == 200
    assert c.get("/api/me/").json()["preferences"] == {"pins": [pin], "recents": [recent]}
    for url in (
        "https://evil.example",
        "//evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "javascript:alert(1)",
        "relative",
        "/" + "x" * 500,
    ):
        assert status(pins=[{**pin, "url": url}]) == 400, url
    for bad in (
        [pin] * 21,
        [{**pin, "label": ""}],
        [{**pin, "label": "x" * 301}],
        [{**pin, "label": "a\nb"}],
        [{**pin, "extra": 1}],
        [{"url": 1, "label": "x"}],
        "nope",
    ):
        assert status(pins=bad) == 400, bad
    for bad in (
        [recent] * 13,
        [{**recent, "kind": "evil"}],
        [{**recent, "at": "soon"}],
        [{**recent, "at": "2026-13-45T00:00:00Z"}],
    ):
        assert status(recents=bad) == 400, bad
