"""Two guards on the in-app assistant's loop: what it replays to the provider each turn (an item
flagged "Contains participant data" after it was read is withheld), and the lab key's monthly cap
counting calls that are running at the same moment."""

import json
from decimal import Decimal

import pytest

from assistant import privacy
from assistant.ai import lab_keys
from assistant.models import Conversation, LabAIReservation, LabAIUsage
from assistant.tests import test_assistant
from assistant.tests.fakes import (
    claude_message,
    o_call,
    o_message,
    openai_response,
    patch_claude,
    patch_openai,
    text,
    tool_use,
)
from assistant.tests.test_assistant import api, events, new_conv, send
from assistant.tests.test_lab_key import fake_claude, set_lab_key
from documents import services as document_services

pytestmark = pytest.mark.django_db
SECRET = "SECRETFINDING"
keyed = test_assistant.keyed  # the fixture: both providers' keys saved for every user


def make_doc(world):
    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": f"{SECRET} 42"}]}]
    return document_services.create_document(
        project=world.p1, user=world.u.pi, title="Interview notes", content=blocks
    )


def args(world, doc):
    return {"lab_id": str(world.lab_a.pk), "document_id": str(doc.pk)}


# ---------------------------------------------------------------- replay


def test_a_document_flagged_after_it_was_read_is_withheld_from_the_next_turn(keyed, monkeypatch):
    doc = make_doc(keyed)
    fake = patch_claude(
        monkeypatch,
        claude_message([tool_use("toolu_1", "get_document", args(keyed, doc))], stop="tool_use"),
        claude_message([text("Read it")]),
        claude_message([text("Next")]),
        claude_message([text("Last")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    events(send(c, keyed.lab_a, conv))
    assert SECRET in json.dumps(fake.calls[1]["messages"])  # the model was given the text

    events(send(c, keyed.lab_a, conv, "And now?"))
    assert SECRET in json.dumps(fake.calls[2]["messages"])  # not flagged yet: still replayed

    privacy.set_flag(doc, True, user=keyed.u.pi)
    events(send(c, keyed.lab_a, conv, "Again?"))
    sent = json.dumps(fake.calls[3]["messages"])
    assert SECRET not in sent and privacy.REFUSAL in sent
    # only the copy sent is changed: the stored log keeps what was read
    assert SECRET in json.dumps(list(Conversation.objects.get(pk=conv).messages.values("content")))


def test_withholding_drops_thinking_blocks_so_the_edited_history_is_not_rejected(
    keyed, monkeypatch
):
    doc = make_doc(keyed)
    think = {"type": "thinking", "thinking": "", "signature": "sig"}
    fake = patch_claude(
        monkeypatch,
        claude_message(
            [think, tool_use("toolu_1", "get_document", args(keyed, doc))], stop="tool_use"
        ),
        claude_message([think, text("Read it")]),
        claude_message([text("Next")]),
        claude_message([text("Last")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    events(send(c, keyed.lab_a, conv))
    events(send(c, keyed.lab_a, conv, "And now?"))
    assert '"signature"' in json.dumps(fake.calls[2]["messages"])  # untouched history keeps them
    privacy.set_flag(doc, True, user=keyed.u.pi)
    events(send(c, keyed.lab_a, conv, "Again?"))
    assert '"signature"' not in json.dumps(fake.calls[3]["messages"])


def test_a_withheld_result_stays_withheld_after_the_flag_is_cleared(keyed, monkeypatch):
    doc = make_doc(keyed)
    think = {"type": "thinking", "thinking": "", "signature": "sig"}
    fake = patch_claude(
        monkeypatch,
        claude_message(
            [think, tool_use("toolu_1", "get_document", args(keyed, doc))], stop="tool_use"
        ),
        claude_message([think, text("Read it")]),
        claude_message([think, text("Withheld")]),
        claude_message([text("Still")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    events(send(c, keyed.lab_a, conv))
    privacy.set_flag(doc, True, user=keyed.u.pi)
    events(send(c, keyed.lab_a, conv, "Again?"))
    privacy.set_flag(doc, False, user=keyed.u.pi)  # the history sent must not flip back
    events(send(c, keyed.lab_a, conv, "And now?"))
    sent = json.dumps(fake.calls[3]["messages"])
    assert SECRET not in sent and privacy.REFUSAL in sent and '"signature"' not in sent


def test_a_document_deleted_after_it_was_read_is_withheld_too(keyed, monkeypatch):
    doc = make_doc(keyed)
    fake = patch_claude(
        monkeypatch,
        claude_message([tool_use("toolu_1", "get_document", args(keyed, doc))], stop="tool_use"),
        claude_message([text("Read it")]),
        claude_message([text("Next")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    events(send(c, keyed.lab_a, conv))
    doc.deleted_at = doc.created_at
    doc.save()
    events(send(c, keyed.lab_a, conv, "Again?"))
    assert SECRET not in json.dumps(fake.calls[2]["messages"])


def test_the_same_holds_for_the_openai_history(keyed, monkeypatch):
    doc = make_doc(keyed)
    fake = patch_openai(
        monkeypatch,
        openai_response([o_call("call_1", "get_document", json.dumps(args(keyed, doc)))]),
        openai_response([o_message("Read it")]),
        openai_response([o_message("Next")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a, provider="openai")
    events(send(c, keyed.lab_a, conv))
    assert SECRET in json.dumps(fake.calls[1]["input"], default=str)
    privacy.set_flag(doc, True, user=keyed.u.pi)
    events(send(c, keyed.lab_a, conv, "Again?"))
    sent = json.dumps(fake.calls[2]["input"], default=str)
    assert SECRET not in sent and privacy.REFUSAL in sent


def test_a_search_result_naming_an_item_flagged_since_is_withheld(keyed, monkeypatch):
    doc = make_doc(keyed)
    search = {"lab_id": str(keyed.lab_a.pk), "query": SECRET}
    fake = patch_claude(
        monkeypatch,
        claude_message([tool_use("toolu_1", "search", search)], stop="tool_use"),
        claude_message([text("Found it")]),
        claude_message([text("Next")]),
    )
    c = api(keyed.u.pi)
    conv = new_conv(c, keyed.lab_a)
    events(send(c, keyed.lab_a, conv))
    assert "Interview notes" in json.dumps(fake.calls[1]["messages"])
    privacy.set_flag(doc, True, user=keyed.u.pi)
    events(send(c, keyed.lab_a, conv, "Again?"))
    sent = json.dumps(fake.calls[2]["messages"])
    assert "Interview notes" not in sent and privacy.REFUSAL in sent


# ---------------------------------------------------------------- the lab key's cap


def test_a_running_call_counts_against_the_cap_until_it_is_settled(world):
    row = set_lab_key(world.lab_a, cap="1.00")
    big = {"output_tokens": 30000}  # 30000 x $20 per million = $0.60
    row, first = lab_keys.reserve(row, big, "claude-opus-5-5")
    assert lab_keys.pending(world.lab_a) == Decimal("0.6")
    row, second = lab_keys.reserve(row, big, "claude-opus-5-5")  # $0.60 pending, under the cap
    with pytest.raises(lab_keys.Unavailable) as exc:  # $1.20 pending: a third must wait
        lab_keys.reserve(row, big, "claude-opus-5-5")
    assert exc.value.code == "lab_limit"
    assert not lab_keys.under_cap(row)
    # settling replaces the estimate with what the call really cost
    lab_keys.record_usage(row, world.u.contrib, {"output_tokens": 1000}, "claude-opus-5-5")
    first.delete()
    second.delete()
    assert lab_keys.pending(world.lab_a) == 0 and lab_keys.spent(world.lab_a) == Decimal("0.02")
    lab_keys.reserve(row, big, "claude-opus-5-5")


def test_an_old_hold_that_was_never_released_stops_counting(world, settings):
    row = set_lab_key(world.lab_a, cap="1.00")
    hold = LabAIReservation.objects.create(lab=world.lab_a, cost_usd=Decimal("5"))
    assert not lab_keys.under_cap(row)
    settings.ASSISTANT_LOCK_TTL = -1  # every hold is older than the limit
    assert lab_keys.under_cap(row)
    hold.delete()


def test_a_turn_holds_its_estimate_during_the_call_and_leaves_nothing_after(world, monkeypatch):
    set_lab_key(world.lab_a)
    seen = []
    fake = fake_claude(monkeypatch, claude_message([text("Hi")]))
    stream = fake.stream

    def spy(**kwargs):
        seen.append(lab_keys.pending(world.lab_a))
        return stream(**kwargs)

    fake.stream = spy
    c = api(world.u.contrib)
    events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert seen and seen[0] > 0  # a second answer starting now would have seen this call's hold
    assert not LabAIReservation.objects.for_lab(world.lab_a).exists()  # released once settled
    assert LabAIUsage.objects.for_lab(world.lab_a).get(user=world.u.contrib).cost_usd > 0


def test_a_failed_call_releases_its_hold(world, monkeypatch):
    import anthropic
    import httpx2 as httpx

    set_lab_key(world.lab_a)
    boom = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.test"))
    fake_claude(monkeypatch, boom)
    c = api(world.u.contrib)
    events(send(c, world.lab_a, new_conv(c, world.lab_a)))
    assert not LabAIReservation.objects.for_lab(world.lab_a).exists()
