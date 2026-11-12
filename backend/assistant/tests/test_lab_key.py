"""The lab's AI key with a monthly cap (VISION A5). Nothing reaches the network: the provider SDK
is the fake in fakes.py, and saving a key skips the provider's check."""

from decimal import Decimal

import pytest
from django.core.cache import cache

from assistant.ai import catalog, chat, claude, keys, lab_keys
from assistant.models import AIProviderKey, Conversation, LabAIKey, LabAIUsage
from assistant.tests.fakes import FakeClaude, claude_message, text, tool_use
from assistant.tests.test_assistant import api, events, new_conv, send
from audit.models import AuditAction, AuditEvent
from labs.models import AiPolicy, LabRole

pytestmark = pytest.mark.django_db

LAB_KEY = "sk-ant-api03-LABKEYabcdefghijklmnop9876"
OWN_KEY = "sk-ant-api03-OWNKEYabcdefghijklmnop5432"
LAB_A_KEY = "sk-ant-api03-LABAKEYabcdefghijklmnop1357"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    cache.clear()
    monkeypatch.setattr(keys, "check", lambda provider, api_key: None)


def fake_claude(monkeypatch, *scripts):
    """Like fakes.patch_claude, but remembers which API key each request used."""
    fake = FakeClaude(*scripts)
    fake.keys = []

    def client(api_key):
        fake.keys.append(api_key)
        return fake

    monkeypatch.setattr(claude, "_client", client)
    return fake


def key_url(lab):
    return f"/api/labs/{lab.pk}/ai-key/"


def set_lab_key(lab, cap="10.00", key=LAB_KEY, provider="anthropic"):
    row = LabAIKey(lab=lab, provider=provider, monthly_cap_usd=Decimal(cap))
    row.set_key(key)
    row.save()
    return row


def own_key(user, key=OWN_KEY):
    row = AIProviderKey(user=user, provider="anthropic")
    row.set_key(key)
    row.save()


# ---------------------------------------------------------------- which key a turn uses


def test_own_key_wins_over_the_lab_key(world, monkeypatch):
    set_lab_key(world.lab_a)
    own_key(world.u.contrib)
    fake = fake_claude(monkeypatch, claude_message([text("Hi")]))
    c = api(world.u.contrib)
    events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert fake.keys == [OWN_KEY]
    assert not LabAIUsage.objects.for_lab(world.lab_a).exists()  # nothing billed to the lab


def test_lab_key_is_used_and_the_turn_is_recorded(world, monkeypatch):
    set_lab_key(world.lab_a)
    fake = fake_claude(monkeypatch, claude_message([text("Hi")]))
    c = api(world.u.contrib)
    cfg = c.get(f"/api/labs/{world.lab_a.pk}/assistant/config/").json()
    assert cfg["lab_key"] == {
        "provider": "anthropic",
        "label": "Anthropic (Claude)",
        "own_key_wins": False,
        "limit_reached": False,
    }
    assert [p["has_key"] for p in cfg["providers"]] == [True, False]
    evs = events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert ("done", {"type": "done"}) in evs and "error" not in [k for k, _ in evs]
    assert fake.keys == [LAB_KEY]
    row = LabAIUsage.objects.for_lab(world.lab_a).get(user=world.u.contrib)
    # claude_message's default usage: 100 in and 20 out on Opus 5.5 ($4 and $20 per million)
    assert row.cost_usd == Decimal("0.0008")
    assert (row.input_tokens, row.output_tokens) == (100, 20)
    assert row.month == lab_keys.this_month()


def test_policy_must_allow_the_assistant_for_the_lab_key(world, monkeypatch):
    set_lab_key(world.lab_a)
    world.lab_a.ai_policy = AiPolicy.MCP
    world.lab_a.save()
    c = api(world.u.contrib)
    assert c.get(f"/api/labs/{world.lab_a.pk}/assistant/config/").json()["lab_key"] is None


def test_at_the_cap_the_lab_key_stops_with_a_plain_message(world, monkeypatch):
    set_lab_key(world.lab_a, cap="1.00")
    LabAIUsage.objects.create(
        lab=world.lab_a, user=world.u.pi, month=lab_keys.this_month(), cost_usd=Decimal("1.00")
    )
    fake = fake_claude(monkeypatch)
    c = api(world.u.contrib)
    conv = new_conv(c, world.lab_a)
    r = send(c, world.lab_a, conv)
    assert r.status_code == 400
    assert r.json() == {
        "detail": "Your lab has reached this month's AI limit. Ask your PI, or add your own key "
        "in Settings, under AI.",
        "code": "lab_limit",
    }
    assert fake.keys == []
    cfg = c.get(f"/api/labs/{world.lab_a.pk}/assistant/config/").json()
    assert cfg["lab_key"]["limit_reached"] is True
    # last month's spend does not count
    LabAIUsage.objects.for_lab(world.lab_a).update(month="2000-01-01")
    fake_claude(monkeypatch, claude_message([text("Hi")]))
    assert send(c, world.lab_a, conv).status_code == 200


def test_the_cap_is_checked_again_before_each_step(world, monkeypatch):
    set_lab_key(world.lab_a, cap="1.00")
    big = {"output_tokens": 60000}  # 60000 x $20 per million = $1.20, over the cap
    fake = fake_claude(
        monkeypatch,
        claude_message([tool_use("t1", "list_labs", {})], stop="tool_use", usage=big),
        claude_message([text("never sent")]),
    )
    c = api(world.u.contrib)
    evs = events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    errors = [d for k, d in evs if k == "error"]
    assert errors and errors[0]["code"] == "lab_limit"
    assert len(fake.keys) == 1


def test_a_removed_lab_key_stops_a_running_answer(world, monkeypatch):
    row = set_lab_key(world.lab_a)
    fake = fake_claude(
        monkeypatch,
        claude_message([tool_use("t1", "list_labs", {})], stop="tool_use"),
        claude_message([text("never sent")]),
    )
    real = lab_keys.record_usage

    def then_remove(*args, **kwargs):
        real(*args, **kwargs)
        LabAIKey.objects.for_lab(world.lab_a).filter(pk=row.pk).delete()

    monkeypatch.setattr(lab_keys, "record_usage", then_remove)
    c = api(world.u.contrib)
    evs = events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert [d["code"] for k, d in evs if k == "error"] == ["no_key"]
    assert len(fake.keys) == 1


def test_lab_a_key_is_never_used_in_lab_b(world, join, monkeypatch):
    set_lab_key(world.lab_b, key=LAB_KEY)
    join(world.u.contrib, world.lab_b, LabRole.MEMBER)
    fake = fake_claude(monkeypatch, claude_message([text("Hi")]))
    c = api(world.u.contrib)
    r = send(c, world.lab_a, new_conv(c, world.lab_a))
    assert r.status_code == 400 and r.json()["code"] == "no_key"
    assert c.get(f"/api/labs/{world.lab_a.pk}/assistant/config/").json()["lab_key"] is None
    assert fake.keys == []
    # and spend in Lab B never counts against Lab A's cap
    set_lab_key(world.lab_a, cap="1.00", key=LAB_A_KEY)
    LabAIUsage.objects.create(
        lab=world.lab_b, user=world.u.contrib, month=lab_keys.this_month(), cost_usd=5
    )
    events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert fake.keys == [LAB_A_KEY]
    assert lab_keys.spent(world.lab_a) == Decimal("0.0008")


# ---------------------------------------------------------------- managing the key


def test_pi_sets_replaces_caps_and_removes_the_key_with_audit(world):
    c = api(world.u.pi)
    body = {"provider": "anthropic", "api_key": LAB_KEY, "monthly_cap_usd": "25"}
    r = c.put(key_url(world.lab_a), body, "application/json")
    assert r.status_code == 200, r.content
    got = r.json()
    assert got["saved"] and got["last4"] == LAB_KEY[-4:] and got["monthly_cap_usd"] == "25.00"
    assert got["spent_usd"] == "0.00" and got["usage"] == []
    assert LAB_KEY not in r.content.decode()

    r = c.put(key_url(world.lab_a), {**body, "monthly_cap_usd": "30"}, "application/json")
    assert r.status_code == 200
    r = c.patch(key_url(world.lab_a), {"monthly_cap_usd": "40"}, "application/json")
    assert r.json()["monthly_cap_usd"] == "40.00"
    c.patch(key_url(world.lab_a), {"monthly_cap_usd": "40"}, "application/json")  # no change
    assert c.delete(key_url(world.lab_a)).status_code == 204
    assert c.delete(key_url(world.lab_a)).status_code == 404
    r = c.patch(key_url(world.lab_a), {"monthly_cap_usd": "5"}, "application/json")
    assert r.status_code == 404
    assert c.get(key_url(world.lab_a)).json()["saved"] is False

    actions = list(
        AuditEvent.objects.filter(lab=world.lab_a, action__startswith="lab_ai_key")
        .order_by("occurred_at")
        .values_list("action", "metadata")
    )
    assert actions == [
        (AuditAction.LAB_AI_KEY_SET, {"provider": "anthropic", "monthly_cap_usd": "25.00"}),
        (AuditAction.LAB_AI_KEY_REPLACED, {"provider": "anthropic", "monthly_cap_usd": "30.00"}),
        (AuditAction.LAB_AI_CAP_CHANGED, {"from": "25.00", "to": "30.00"}),
        (AuditAction.LAB_AI_CAP_CHANGED, {"from": "30.00", "to": "40.00"}),
        (AuditAction.LAB_AI_KEY_REMOVED, {"provider": "anthropic"}),
    ]


def test_a_cap_is_required_and_the_key_is_checked(world):
    c = api(world.u.pi)
    r = c.put(
        key_url(world.lab_a), {"provider": "anthropic", "api_key": LAB_KEY}, "application/json"
    )
    assert r.status_code == 400 and "monthly_cap_usd" in r.json()
    r = c.put(
        key_url(world.lab_a),
        {"provider": "openai", "api_key": LAB_KEY, "monthly_cap_usd": "5"},
        "application/json",
    )
    assert r.status_code == 400 and "api_key" in r.json()
    assert not LabAIKey.objects.for_lab(world.lab_a).exists()


def test_members_cannot_set_or_read_the_key(world):
    set_lab_key(world.lab_a)
    for user in (world.u.contrib, world.u.viewer, world.u.other):
        c = api(user)
        expected = 404 if user is world.u.other else 403
        assert c.get(key_url(world.lab_a)).status_code == expected
        body = {"provider": "anthropic", "api_key": OWN_KEY, "monthly_cap_usd": "5"}
        assert c.put(key_url(world.lab_a), body, "application/json").status_code == expected
        assert c.patch(key_url(world.lab_a), body, "application/json").status_code == expected
        assert c.delete(key_url(world.lab_a)).status_code == expected
    cfg = api(world.u.contrib).get(f"/api/labs/{world.lab_a.pk}/assistant/config/")
    assert LAB_KEY[-4:] not in cfg.content.decode()
    assert LabAIKey.objects.for_lab(world.lab_a).get().api_key() == LAB_KEY


def test_usage_per_person_and_total(world, monkeypatch):
    set_lab_key(world.lab_a)
    month = lab_keys.this_month()
    for user, cost in ((world.u.pi, "0.25"), (world.u.contrib, "1.5")):
        LabAIUsage.objects.create(
            lab=world.lab_a, user=user, month=month, cost_usd=Decimal(cost), input_tokens=7
        )
    LabAIUsage.objects.create(lab=world.lab_a, user=world.u.viewer, month="2000-01-01", cost_usd=9)
    got = api(world.u.pi).get(key_url(world.lab_a)).json()
    assert got["spent_usd"] == "1.75"
    assert [(u["name"], u["cost_usd"]) for u in got["usage"]] == [
        ("Contrib", "1.50"),
        ("Pi", "0.25"),
    ]


# ---------------------------------------------------------------- usage maths


def test_cost_matches_the_panel_estimate():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_read_tokens": 2000,
        "cache_write_tokens": 400,
    }
    # Sonnet 5.5: $2 in, $10 out per million. 1000*2 + 2000*0.2 + 400*2.5 + 500*10 = 8400
    assert catalog.cost(usage, "claude-sonnet-5-5") == Decimal("0.0084")
    # an unlisted model (a fallback) is priced as the conversation's model
    assert catalog.cost(usage, "claude-unknown", "claude-sonnet-5-5") == Decimal("0.0084")
    assert catalog.cost({}, "claude-sonnet-5-5") == 0


def test_record_usage_adds_up(world):
    row = set_lab_key(world.lab_a)
    turn = {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 1000}
    for _ in range(3):
        lab_keys.record_usage(row, world.u.contrib, turn, "claude-opus-5-5")
    got = LabAIUsage.objects.for_lab(world.lab_a).get(user=world.u.contrib)
    # each turn: 100*4 + 1000*0.4 + 20*20 = 1200 per million
    assert got.cost_usd == Decimal("0.0036")
    assert (got.input_tokens, got.output_tokens) == (3300, 60)


def test_rotate_re_encrypts_lab_keys(world):
    row = set_lab_key(world.lab_a)
    before = row.key_ciphertext
    assert keys.rotate_all() == 1
    row = LabAIKey.objects.for_lab(world.lab_a).get()
    assert row.api_key() == LAB_KEY and row.key_ciphertext != before
    assert LAB_KEY[-4:] not in str(row) + repr(row)


def test_a_stopped_answer_is_still_charged_to_the_lab(world, monkeypatch):
    row = set_lab_key(world.lab_a)
    fake_claude(monkeypatch, claude_message([text("A long answer")]))
    c = api(world.u.contrib)
    conv = Conversation.objects.get(pk=new_conv(c, world.lab_a))
    run = chat.Run(conv, world.u.contrib, None, row)
    stream = run.send("Hello")
    next(stream)
    stream.close()  # Stop, or the browser went away, before the answer finished
    assert LabAIUsage.objects.for_lab(world.lab_a).get(user=world.u.contrib).cost_usd > 0


def test_an_unlisted_model_is_not_free():
    usage = {"output_tokens": 1_000_000}
    assert catalog.cost(usage, "claude-removed") >= catalog.cost(usage, "claude-opus-5-5") > 0
