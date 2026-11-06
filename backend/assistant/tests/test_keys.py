"""Provider keys (D187): encrypted at rest, checked on save, never shown back, per user."""

import io
import json

import anthropic
import httpx2 as httpx
import openai
import pytest
from django.contrib import admin
from django.core.management import call_command
from django.test import Client

from assistant.ai import claude, keys, openai_responses
from assistant.models import AIProviderKey
from assistant.tests.fakes import CANARY_KEY, OPENAI_CANARY, patch_claude, patch_openai
from audit.models import AuditAction, AuditEvent
from integrations import crypto

pytestmark = pytest.mark.django_db


def api(user):
    c = Client()
    c.force_login(user)
    return c


def put(c, provider, key):
    return c.put(f"/api/ai/keys/{provider}/", {"api_key": key}, "application/json")


def auth_error(cls):
    req = httpx.Request("GET", "https://api.example.com/v1/models")
    resp = httpx.Response(401, request=req, json={"error": {"message": f"bad {CANARY_KEY}"}})
    return cls(f"bad {CANARY_KEY}", response=resp, body=None)


def test_saving_a_key_checks_it_encrypts_it_and_shows_only_the_last_four(world, monkeypatch):
    fake = patch_claude(monkeypatch)
    c = api(world.u.pi)
    r = put(c, "anthropic", CANARY_KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True and body["last4"] == CANARY_KEY[-4:]
    assert CANARY_KEY not in r.content.decode()
    assert fake.listed == [{"limit": 1}]  # one cheap, free call
    row = AIProviderKey.objects.get(user=world.u.pi, provider="anthropic")
    assert row.key_ciphertext and CANARY_KEY not in row.key_ciphertext
    assert row.api_key() == CANARY_KEY and crypto.decrypt(row.key_ciphertext) == CANARY_KEY
    listing = c.get("/api/ai/keys/")
    assert CANARY_KEY not in listing.content.decode()
    by = {k["provider"]: k for k in listing.json()}
    assert by["anthropic"]["saved"] and not by["openai"]["saved"] and by["openai"]["last4"] == ""
    assert str(row) == "anthropic key" and CANARY_KEY[-4:] not in repr(row)


def test_the_ciphertext_is_not_deterministic_and_rotates(world, monkeypatch, settings):
    patch_claude(monkeypatch)
    c = api(world.u.pi)
    put(c, "anthropic", CANARY_KEY)
    first = AIProviderKey.objects.get().key_ciphertext
    put(c, "anthropic", CANARY_KEY)
    assert AIProviderKey.objects.get().key_ciphertext != first  # fresh nonce each time
    from cryptography.fernet import Fernet

    settings.INTEGRATION_ENCRYPTION_KEYS = [
        Fernet.generate_key().decode(),
        *settings.INTEGRATION_ENCRYPTION_KEYS,
    ]
    crypto._fernet.cache_clear()
    try:
        before = AIProviderKey.objects.get().key_ciphertext
        assert keys.rotate_all() == 1
        row = AIProviderKey.objects.get()
        assert row.key_ciphertext != before and row.api_key() == CANARY_KEY
        out = io.StringIO()
        call_command("rotate_integration_keys", stdout=out)
        assert "1 AI provider key" in out.getvalue()
    finally:
        crypto._fernet.cache_clear()


@pytest.mark.parametrize(
    "bad", ["", "   ", "hello world", "sk-short", "sk-ant-" + "a" * 5, "sk-ant-ok\nline", "x" * 600]
)
def test_a_value_that_is_not_a_key_is_refused_before_any_call(world, monkeypatch, bad):
    fake = patch_claude(monkeypatch)
    r = put(api(world.u.pi), "anthropic", bad)
    assert r.status_code == 400 and "api_key" in r.json()
    assert fake.listed == [] and not AIProviderKey.objects.exists()


def test_an_anthropic_key_is_not_accepted_as_an_openai_key(world, monkeypatch):
    patch_openai(monkeypatch)
    assert put(api(world.u.pi), "openai", CANARY_KEY).status_code == 400


def test_a_key_the_provider_rejects_is_not_stored_and_its_error_text_is_not_shown(
    world, monkeypatch
):
    fake = patch_claude(monkeypatch)
    fake.list_error = auth_error(anthropic.AuthenticationError)
    r = put(api(world.u.pi), "anthropic", CANARY_KEY)
    assert r.status_code == 400
    assert "rejected your API key" in r.json()["api_key"]
    assert CANARY_KEY not in r.content.decode()
    assert not AIProviderKey.objects.exists()


def test_openai_keys_are_checked_with_the_openai_sdk(world, monkeypatch):
    fake = patch_openai(monkeypatch)
    r = put(api(world.u.pi), "openai", OPENAI_CANARY)
    assert r.status_code == 200 and fake.listed == 1
    fake.list_error = auth_error(openai.AuthenticationError)
    assert put(api(world.u.contrib), "openai", OPENAI_CANARY).status_code == 400


def test_a_key_is_per_user_and_removing_it_removes_only_yours(world, monkeypatch):
    patch_claude(monkeypatch)
    pi, contrib = api(world.u.pi), api(world.u.contrib)
    put(pi, "anthropic", CANARY_KEY)
    put(contrib, "anthropic", CANARY_KEY.replace("CANARY", "OTHERON"))
    assert pi.delete("/api/ai/keys/anthropic/").status_code == 204
    assert pi.delete("/api/ai/keys/anthropic/").status_code == 404  # already gone
    assert [k["saved"] for k in contrib.get("/api/ai/keys/").json()] == [True, False]
    assert AIProviderKey.objects.get().user_id == world.u.contrib.pk


def test_a_key_is_not_tied_to_a_lab(world, monkeypatch):
    patch_claude(monkeypatch)
    row = put(api(world.u.pi), "anthropic", CANARY_KEY)
    assert row.status_code == 200
    assert "lab" not in [f.name for f in AIProviderKey._meta.get_fields()]


def test_unknown_provider_is_404(world):
    c = api(world.u.pi)
    assert put(c, "mistral", CANARY_KEY).status_code == 404
    assert c.delete("/api/ai/keys/mistral/").status_code == 404


def test_the_fallback_setting_can_be_turned_off_and_on(world, monkeypatch):
    patch_claude(monkeypatch)
    c = api(world.u.pi)
    put(c, "anthropic", CANARY_KEY)
    r = c.patch("/api/ai/keys/anthropic/", {"refusal_fallback": False}, "application/json")
    assert r.json()["refusal_fallback"] is False
    assert AIProviderKey.objects.get().refusal_fallback is False
    assert (
        c.patch("/api/ai/keys/openai/", {"refusal_fallback": False}, "application/json").status_code
        == 404
    )


def test_saving_and_removing_are_audited_without_the_key(world, monkeypatch):
    patch_claude(monkeypatch)
    c = api(world.u.pi)
    put(c, "anthropic", CANARY_KEY)
    c.delete("/api/ai/keys/anthropic/")
    events = AuditEvent.objects.filter(
        action__in=[AuditAction.AI_KEY_SAVED, AuditAction.AI_KEY_REMOVED], lab=world.lab_a
    ).order_by("occurred_at")
    assert [e.action for e in events] == ["ai_key.saved", "ai_key.removed"]
    assert events[0].metadata == {"provider": "anthropic"}
    assert CANARY_KEY[-4:] not in json.dumps(list(AuditEvent.objects.values()), default=str)


def test_the_admin_does_not_register_the_key_model():
    assert AIProviderKey not in admin.site._registry


def test_every_provider_error_class_maps_to_a_fixed_message():
    # the most specific classes first: a rate limit is retryable, a bad request is not
    req = httpx.Request("POST", "https://x")

    def err(cls, code, headers=None):
        resp = httpx.Response(code, request=req, headers=headers or {}, json={})
        return cls("msg", response=resp, body=None)

    assert claude.translate(err(anthropic.RateLimitError, 429, {"retry-after": "9"})).retryable
    assert not claude.translate(err(anthropic.BadRequestError, 400)).retryable
    assert claude.translate(err(anthropic.OverloadedError, 529)).code == "overloaded"
    assert claude.translate(err(anthropic.ServiceUnavailableError, 503)).code == "unavailable"
    assert claude.translate(RuntimeError("boom")).code == "unknown"
    assert openai_responses.translate(err(openai.RateLimitError, 429)).retryable
    assert openai_responses.translate(err(openai.InternalServerError, 500)).code == "unavailable"
    quota = err(openai.RateLimitError, 429)
    quota.code = "insufficient_quota"
    assert openai_responses.translate(quota).code == "billing"
