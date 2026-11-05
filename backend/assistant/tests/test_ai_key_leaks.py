"""Key-leak test for the in-app assistant (D187). Two real-looking provider keys go through saving,
checking, use in a chat, provider errors, deletion and crashes. After they are saved neither may
appear in any API response (not even the one that saves it), event stream, log line, audit event,
model repr, dumpdata output, admin, or Django's DEBUG 500 page. The stored ciphertext may not
appear in any response, log or audit event either."""

import io
import json
import logging
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest
from django.core.management import call_command
from django.test import Client
from django.test.utils import override_settings

from assistant import ai_views, tools
from assistant.ai import keys
from assistant.models import AIProviderKey, Conversation, Message
from assistant.tests.fakes import (
    CANARY_KEY,
    OPENAI_CANARY,
    claude_message,
    patch_claude,
    patch_openai,
    text,
    tool_use,
)
from assistant.tests.test_assistant import new_conv, send, url
from audit.models import AuditEvent

pytestmark = pytest.mark.django_db


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


def dump(resp):
    body = b"".join(resp.streaming_content) if resp.streaming else resp.content
    return f"{resp.status_code} {dict(resp.headers)} {body.decode(errors='replace')}"


def test_no_provider_key_appears_anywhere(world, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    seen = []
    fake = patch_claude(monkeypatch)
    patch_openai(monkeypatch)
    c = Client()
    c.force_login(world.u.pi)

    # --- saving: the response that saves a key does not contain it either
    seen.append(dump(c.put("/api/ai/keys/anthropic/", {"api_key": CANARY_KEY}, "application/json")))
    seen.append(dump(c.put("/api/ai/keys/openai/", {"api_key": OPENAI_CANARY}, "application/json")))
    seen.append(dump(c.get("/api/ai/keys/")))
    seen.append(dump(c.get(f"/api/labs/{world.lab_a.pk}/assistant/config/")))
    seen.append(
        dump(c.patch("/api/ai/keys/anthropic/", {"refusal_fallback": False}, "application/json"))
    )
    seen.append(
        dump(c.patch("/api/ai/keys/anthropic/", {"refusal_fallback": True}, "application/json"))
    )
    ciphertexts = list(AIProviderKey.objects.values_list("key_ciphertext", flat=True))
    assert len(ciphertexts) == 2 and all(ciphertexts)

    # --- a key the provider rejects, and one that is not a key at all
    req = httpx.Request("GET", "https://api.anthropic.com/v1/models")
    rejected = anthropic.AuthenticationError(
        f"invalid x-api-key {CANARY_KEY}",
        response=httpx.Response(401, request=req, json={"error": {"message": CANARY_KEY}}),
        body={"error": CANARY_KEY},
    )
    other = Client()
    other.force_login(world.u.contrib)
    fake.list_error = rejected
    seen.append(
        dump(other.put("/api/ai/keys/anthropic/", {"api_key": CANARY_KEY}, "application/json"))
    )
    seen.append(
        dump(
            other.put(
                "/api/ai/keys/anthropic/",
                {"api_key": "not a key " + CANARY_KEY},
                "application/json",
            )
        )
    )
    fake.list_error = None

    # --- a chat: a normal answer, a tool call, a provider error that echoes the key, a crash
    conv = new_conv(c, world.lab_a)
    patch_claude(
        monkeypatch,
        claude_message([tool_use("t1", "list_labs", {})], stop="tool_use"),
        claude_message([text("Answer")]),
    )
    seen.append(dump(send(c, world.lab_a, conv, "hello")))
    seen.append(dump(c.get(url(world.lab_a, "conversations", conv))))
    seen.append(dump(c.get(url(world.lab_a, "conversations"))))
    patch_claude(monkeypatch, rejected)
    seen.append(dump(send(c, world.lab_a, conv, "again")))
    patch_claude(monkeypatch, RuntimeError(f"unexpected {CANARY_KEY}"))
    seen.append(dump(send(c, world.lab_a, conv, "and again")))  # an unexpected error: generic text
    seen.append(dump(c.delete("/api/ai/keys/openai/")))

    # --- DEBUG 500 pages with the key in memory
    raw = Client(raise_request_exception=False)
    raw.force_login(world.u.pi)
    pages = []
    with override_settings(DEBUG=True):
        monkeypatch.setattr(keys, "check", _boom)  # the key is in scope inside keys.save
        pages.append(
            dump(raw.put("/api/ai/keys/anthropic/", {"api_key": CANARY_KEY}, "application/json"))
        )
        monkeypatch.undo()
        patch_claude(monkeypatch)
        monkeypatch.setattr(
            ai_views, "cache", SimpleNamespace(get=_boom)
        )  # the stored key is in scope in the view
        pages.append(
            dump(
                raw.post(
                    url(world.lab_a, "conversations", conv, "messages"),
                    {"text": "x"},
                    "application/json",
                )
            )
        )
        monkeypatch.undo()
        patch_claude(monkeypatch)
        monkeypatch.setattr(tools, "call", _boom)
    assert all(p.startswith("500") and "RuntimeError" in p for p in pages), [p[:80] for p in pages]
    seen += pages

    # --- stored state: reprs, audit, logs, dumpdata, admin
    seen.append(caplog.text)
    seen.append(json.dumps(list(AuditEvent.objects.values()), default=str))
    for model in (AIProviderKey, Conversation, Message):
        for obj in model.objects.all():
            seen += [
                str(obj),
                repr(obj),
                str(obj.__dict__) if model is not AIProviderKey else str(obj),
            ]
    out = io.StringIO()
    call_command("dumpdata", "assistant.conversation", "assistant.message", "audit", stdout=out)
    seen.append(out.getvalue())

    joined = "\n".join(seen)
    assert CANARY_KEY not in joined and OPENAI_CANARY not in joined
    assert not [x[:12] for x in ciphertexts if x in joined]
    assert CANARY_KEY[-4:] not in "".join(
        e["metadata"]
        for e in [
            {"metadata": json.dumps(m)}
            for m in AuditEvent.objects.values_list("metadata", flat=True)
        ]
    )
    # the database does hold the keys, but only as ciphertext
    with_db = io.StringIO()
    call_command("dumpdata", "assistant.aiproviderkey", stdout=with_db)
    assert CANARY_KEY not in with_db.getvalue() and "key_ciphertext" in with_db.getvalue()


def test_the_system_prompt_and_ciphertext_are_never_serialized(world, monkeypatch):
    patch_claude(monkeypatch)
    c = Client()
    c.force_login(world.u.pi)
    c.put("/api/ai/keys/anthropic/", {"api_key": CANARY_KEY}, "application/json")
    conv = new_conv(c, world.lab_a)
    detail = c.get(url(world.lab_a, "conversations", conv)).content.decode()
    assert "system_prompt" not in detail and "You are the research assistant" not in detail
    assert "key_ciphertext" not in c.get("/api/ai/keys/").content.decode()
