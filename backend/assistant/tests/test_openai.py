"""The OpenAI adapter (D192): the Responses API through the official SDK, over the same tool layer.
It shares no request code with the Claude adapter, and these tests pin that."""

import json

import openai
import pytest

from assistant.models import AIProviderKey, Message
from assistant.tests.fakes import (
    OPENAI_CANARY,
    o_call,
    o_message,
    openai_response,
    patch_openai,
)
from assistant.tests.test_assistant import api, events, kinds, new_conv, send, url
from projects.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def keyed(world):
    for user in (world.u.pi, world.u.contrib):
        row = AIProviderKey(user=user, provider="openai")
        row.set_key(OPENAI_CANARY)
        row.save()
    return world


def test_openai_request_uses_the_responses_api_not_the_claude_format(keyed, monkeypatch):
    fake = patch_openai(monkeypatch, openai_response([o_message("Hello")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a, provider="openai")
    evs = events(send(c, keyed.lab_a, conv, "hi"))
    kw = fake.calls[0]
    assert kw["model"] == "gpt-6.1-sol"
    assert kw["store"] is False and kw["stream"] is True
    assert kw["include"] == ["reasoning.encrypted_content"]
    assert kw["input"] == [{"role": "user", "content": "hi"}]
    assert kw["instructions"].startswith("You are the research assistant")
    assert all(t["type"] == "function" and "parameters" in t for t in kw["tools"])
    # nothing Claude-shaped leaks into an OpenAI request
    for claude_only in ("thinking", "output_config", "betas", "fallbacks", "messages", "system"):
        assert claude_only not in kw
    assert not any("eager_input_streaming" in t or "input_schema" in t for t in kw["tools"])
    assert "".join(d["delta"] for k, d in evs if k == "text") == "Hello"
    msg = Message.objects.get(conversation_id=conv, role="assistant")
    assert msg.model == "gpt-6.1-sol"
    # cached tokens are split out so the cost estimate can price them separately
    assert msg.usage == {
        "input_tokens": 100,
        "output_tokens": 30,
        "cache_read_tokens": 20,
        "cache_write_tokens": 0,
    }


def test_openai_parallel_tool_calls_one_failing(keyed, monkeypatch):
    lab = keyed.lab_a
    first = openai_response(
        [
            {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "enc"},
            o_call("call_1", "list_projects", json.dumps({"lab_id": str(lab.pk)})),
            o_call(
                "call_2", "project_overview", json.dumps({"lab_id": str(lab.pk), "project_id": "x"})
            ),
            o_call("call_3", "list_labs", "{not json"),
        ]
    )
    fake = patch_openai(monkeypatch, first, openai_response([o_message("Done")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, lab, provider="openai")
    evs = events(send(c, lab, conv))
    assert [d["status"] for k, d in evs if k == "tool"] == ["done", "error", "error"]
    second_input = fake.calls[1]["input"]
    outputs = [i for i in second_input if i.get("type") == "function_call_output"]
    assert [o["call_id"] for o in outputs] == ["call_1", "call_2", "call_3"]
    assert [o["output"].startswith("Error: ") for o in outputs] == [False, True, True]
    # the first turn's items (reasoning included) come back unchanged, ahead of the results
    kinds_sent = [i.get("type", i.get("role")) for i in second_input]
    assert kinds_sent[:5] == [
        "user",
        "reasoning",
        "function_call",
        "function_call",
        "function_call",
    ]
    assert second_input[1]["encrypted_content"] == "enc"


def test_openai_write_waits_for_approval(keyed, monkeypatch):
    w, lab = keyed, keyed.lab_a
    args = json.dumps({"lab_id": str(lab.pk), "project_id": str(w.p1.pk), "title": "From OpenAI"})
    fake = patch_openai(
        monkeypatch,
        openai_response([o_call("call_w", "create_task", args)]),
        openai_response([o_message("Added")]),
    )
    c = api(w.u.contrib)
    conv = new_conv(c, lab, provider="openai")
    before = Task.objects.for_lab(lab).count()
    evs = events(send(c, lab, conv))
    assert kinds(evs)[-2] == "approval_required" and Task.objects.for_lab(lab).count() == before
    events(
        c.post(
            url(lab, "conversations", conv, "approvals"),
            {"decisions": {"call_w": True}},
            "application/json",
        )
    )
    assert Task.objects.for_lab(lab).count() == before + 1
    out = [i for i in fake.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert out[0]["call_id"] == "call_w"


def test_openai_errors_and_truncation(keyed, monkeypatch):
    import httpx2 as httpx

    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    resp = httpx.Response(401, request=req, json={})
    patch_openai(
        monkeypatch, openai.AuthenticationError(f"bad {OPENAI_CANARY}", response=resp, body=None)
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a, provider="openai")
    err = next(d for k, d in events(send(c, keyed.lab_a, conv)) if k == "error")
    assert err["code"] == "key_invalid" and OPENAI_CANARY not in json.dumps(err)
    cut = openai_response(
        [o_message("partial")],
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )
    patch_openai(monkeypatch, cut)
    conv2 = new_conv(c, keyed.lab_a, provider="openai")
    evs = events(send(c, keyed.lab_a, conv2))
    assert [d["code"] for k, d in evs if k == "notice"] == ["max_tokens"]


def test_openai_in_band_refusal_is_shown_and_replayable(keyed, monkeypatch):
    refusal = {
        "id": "msg_r",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "refusal", "refusal": "I can't help with that."}],
    }
    patch_openai(monkeypatch, openai_response([refusal]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a, provider="openai")
    evs = events(send(c, keyed.lab_a, conv))
    notice = next(d for k, d in evs if k == "notice")
    assert notice["refusal"]["explanation"] == "I can't help with that."
    assert Message.objects.get(conversation_id=conv, role="assistant").in_context is True
    items = c.get(url(keyed.lab_a, "conversations", conv)).json()["items"]
    assert items[-1]["refusal"]["explanation"] == "I can't help with that."


def test_a_conversation_keeps_its_provider(keyed, monkeypatch):
    patch_openai(monkeypatch, openai_response([o_message("x")]))
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a, provider="openai")
    assert c.get(url(keyed.lab_a, "conversations", conv)).json()["provider"] == "openai"
    # no Anthropic key was saved, and this chat never needs one
    assert send(c, keyed.lab_a, conv).status_code == 200
