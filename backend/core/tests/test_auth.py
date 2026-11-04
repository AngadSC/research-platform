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
