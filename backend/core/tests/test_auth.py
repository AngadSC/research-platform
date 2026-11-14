import importlib

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
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


def _theme(**over):
    return {
        "id": "t1",
        "name": "Paper",
        "background": "#ffffff",
        "text": "#18181b",
        "accent": "#4f46e5",
        **over,
    }


def test_custom_themes_must_be_readable(make_user):
    c = APIClient()
    c.force_authenticate(make_user(email="ada@uni.edu"))

    def patch(prefs):
        return c.patch("/api/me/", {"preferences": prefs}, format="json").status_code

    for bad in (
        _theme(text="#aaaaaa"),  # grey on white
        _theme(accent="#ffff00"),  # yellow on white
        _theme(background="red"),
        _theme(accent="#4f46e5;--x:y"),
        _theme(name=" "),
        _theme(id="a/b"),
        {**_theme(), "extra": "x"},
        "nope",
    ):
        assert patch({"custom_themes": [bad]}) == 400, bad
    assert patch({"custom_themes": [_theme(), _theme()]}) == 400  # same id twice
    assert patch({"custom_themes": [_theme(id=str(i)) for i in range(11)]}) == 400
    assert patch({"theme": "custom:t1"}) == 400  # no such theme yet

    assert patch({"custom_themes": [_theme()], "theme": "custom:t1"}) == 200
    assert patch({"custom_themes": []}) == 400  # would leave the account on a deleted theme
    assert patch({"custom_themes": [], "theme": "system"}) == 200


def test_signup_does_not_make_a_name_from_the_email():
    Client().post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "jgogia@uni.edu", "password": "a-long-Passw0rd!"},
        "application/json",
    )
    assert get_user_model().objects.get(email="jgogia@uni.edu").display_name == ""


def test_migration_blanks_only_names_made_from_the_email(make_user):
    from importlib import import_module

    from django.apps import apps

    fragment = make_user(email="jgogia@uni.edu", display_name="jgogia")
    real = make_user(email="ada@uni.edu", display_name="Ada Lovelace")
    import_module("core.migrations.0010_blank_email_fragment_names").blank_fragment_names(
        apps, None
    )
    fragment.refresh_from_db()
    real.refresh_from_db()
    assert fragment.display_name == ""
    assert real.display_name == "Ada Lovelace"


@pytest.mark.django_db
def test_sidebar_order_is_saved_and_checked(make_user):
    user = make_user()
    c = APIClient()
    c.force_authenticate(user)
    ok = {"sidebar_main": ["chat", "dashboard", "settings/integrations"], "sidebar_admin": []}
    resp = c.patch("/api/me/", {"preferences": ok}, format="json")
    assert resp.status_code == 200
    assert resp.json()["preferences"] == ok
    for bad in (
        {"sidebar_main": "chat"},
        {"sidebar_main": ["chat", "chat"]},
        {"sidebar_main": ["https://example.test"]},
        {"sidebar_main": ["../x"]},
        {"sidebar_main": [str(i) for i in range(41)]},
        {"sidebar_admin": [1]},
    ):
        assert c.patch("/api/me/", {"preferences": bad}, format="json").status_code == 400
