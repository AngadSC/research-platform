"""The in-app assistant's tool loop (D190, D191). Provider-neutral: it asks an adapter
(claude.py or openai_responses.py) for one model turn at a time and runs the tools through the
shared tool layer (assistant/tools.py), the same code the MCP server uses.

The conversation is the only state. Every turn is appended to `Message` as the provider sent it,
and a write waiting for the person's approval is simply an assistant turn whose tool calls have no
results yet, so a page reload, a second tab or a restart all see the same thing."""

import json
import logging
import re
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from assistant import code_exec, privacy, tools
from assistant.ai import catalog, claude, lab_keys, openai_responses
from assistant.ai.types import ProviderError, ToolCall, TurnResult, provider_error
from assistant.models import Conversation, LabAIKey, Message, Provider, Role
from labs.models import AiPolicy, Lab

log = logging.getLogger(__name__)

ADAPTERS = {Provider.ANTHROPIC: claude, Provider.OPENAI: openai_responses}
DECLINED = "The person declined this action."
MAX_STREAMS = 3  # open assistant streams per person, so they cannot starve the web workers


class Busy(Exception):
    """This conversation, this person, or the whole server is already at its stream limit."""


class PolicyOff(Exception):
    """The lab's AI policy does not allow the in-app assistant."""


def lab_allows(lab_id) -> bool:
    """D188: the in-app assistant needs the policy `full`; `mcp` and `off` refuse it."""
    return Lab.objects.filter(pk=lab_id, ai_policy=AiPolicy.FULL).exists()


# ---------------------------------------------------------------- locks and caps (D196)


class Lease:
    """The cache slots one running stream owns: its conversation lock, one of the person's
    `MAX_STREAMS` slots and one of the server's `ASSISTANT_MAX_STREAMS` slots. Each holds a token
    and a TTL. `touch` (the heartbeat) extends all of them while the stream is alive, so none can
    expire mid-stream; a crashed worker stops touching and its slots free themselves after the
    TTL. Slots, not counters: a counter that a crash never decrements would leak for ever once
    other streams keep refreshing it. ponytail: get-then-delete is not atomic; a slot that expired
    and was re-taken in that instant could be freed early (harmless: the cap is soft by one)."""

    def __init__(self, token, keys):
        self.token, self.keys = token, keys

    def touch(self) -> None:
        for key in self.keys:
            if cache.get(key) == self.token:
                cache.touch(key, settings.ASSISTANT_LOCK_TTL)

    def release(self) -> None:
        for key in self.keys:
            if cache.get(key) == self.token:
                cache.delete(key)


def acquire(conv) -> Lease:
    """One stream per conversation, a few per person, a fixed number on the whole server (set
    well below the gunicorn thread count so ordinary requests always find a free thread)."""
    token, held = uuid.uuid4().hex, []
    ttl = settings.ASSISTANT_LOCK_TTL

    def take(keys, message):
        for key in keys:
            if cache.add(key, token, ttl):
                held.append(key)
                return
        Lease(token, held).release()
        raise Busy(message)

    take([f"asst-lock:{conv.pk}"], "This conversation is already answering.")
    take(
        [f"asst-user:{conv.user_id}:{i}" for i in range(MAX_STREAMS)],
        "Too many assistant chats are answering at once. Wait for one to finish.",
    )
    take(
        [f"asst-all:{i}" for i in range(settings.ASSISTANT_MAX_STREAMS)],
        "The assistant is busy right now. Try again in a minute.",
    )
    return Lease(token, held)


# ---------------------------------------------------------------- state read from the log


def adapter_for(conv):
    return ADAPTERS[conv.provider]


def _messages(conv) -> list[Message]:
    return list(conv.messages.all())


def _pending_calls(conv, messages=None) -> list[ToolCall]:
    """Tool calls of the last assistant turn that have no results yet (empty when the log ends
    on anything else)."""
    messages = messages if messages is not None else _messages(conv)
    last = messages[-1] if messages else None
    if last is None or last.role != Role.ASSISTANT or not last.in_context:
        return []
    return adapter_for(conv).tool_calls(last.content)


def tool_info(name):
    t = tools.TOOLS.get(name)
    return {"title": t.title if t else name, "write": bool(t and t.write)}


def awaiting_approval(conv, messages=None) -> list[dict]:
    """The write calls the person must approve or decline. A call whose arguments fail the tool's
    schema is not offered: it is answered with an error instead."""
    out = []
    ctx = tools.Context(  # only to resolve names the way this person may see them (D198)
        user=conv.user, lab_ids=frozenset({str(conv.lab_id)}), can_write=False, via="in_app"
    )
    for call in _pending_calls(conv, messages):
        t = tools.TOOLS.get(call.name)
        if t is None or not t.write:
            continue
        try:
            tools.validate_args(call.name, call.arguments)
        except tools.ToolError:
            continue
        described = tools.describe_call(ctx, call.name, call.arguments)
        if call.name == code_exec.SAVE:
            described["preview"] += code_exec.preview(conv, call.arguments)
        out.append(
            {"id": call.id, "name": call.name, "title": t.title, "arguments": call.arguments}
            | described
        )
    return out


# ---------------------------------------------------------------- timeline (what the UI shows)


def _add(acc, usage):
    for k, v in (usage or {}).items():
        acc[k] = acc.get(k, 0) + v


_PAGE_PREFIX = re.compile(r"\A\[The person is looking at: [^\]]*\]\n\n")


def page_prefix(page) -> str:
    """One line naming the open page by kind and ids (already validated), put before the message
    so the system prompt, which must not change, stays as it is."""
    if not page:
        return ""
    where = page["kind"] if page["kind"] == "lab" else f"{page['kind']} {page['id']}"
    if page["kind"] not in ("lab", "project") and page.get("project"):
        where += f" in project {page['project']}"
    return f"[The person is looking at: {where}]\n\n"


def timeline(conv) -> list[dict]:
    """The log as the panel draws it: user text, assistant text with the model that answered and
    the tokens used, and one row per tool call with its outcome."""
    adapter = adapter_for(conv)
    messages = _messages(conv)
    results = {}
    for m in messages:
        if m.role == Role.USER and not (m.content and m.content[0].get("type") == "text"):
            results |= adapter.results_of(m.content)
    pending = {p["id"] for p in awaiting_approval(conv, messages)}
    code_results = code_exec.results_by_id(messages)
    items, acc = [], {}
    for m in messages:
        if m.role == Role.USER:
            if m.content and m.content[0].get("type") == "text":
                acc = {}
                items.append(
                    {
                        "id": m.pk,
                        "kind": "user",
                        "text": _PAGE_PREFIX.sub("", adapter.text_of(m.content)),
                    }
                )
            continue
        _add(acc, m.usage)
        items += code_exec.items(conv, m, code_results)  # VISION C1: code it ran, files made
        text = adapter.text_of(m.content)
        refusal = m.meta.get("refusal")
        truncated = m.stop_reason == "max_tokens"
        if text or refusal or truncated:
            items.append(
                {
                    "id": m.pk,
                    "kind": "assistant",
                    "text": text,
                    "model": m.model,
                    "usage": dict(acc),
                    "stop_reason": m.stop_reason,
                    "fallback": bool(m.meta.get("fallback")),
                    "refusal": refusal or None,
                    "truncated": truncated,
                }
            )
            acc = {}
        if m.in_context:
            for call in adapter.tool_calls(m.content):
                ok_text = results.get(call.id)
                if ok_text is None:
                    status = "pending" if call.id in pending else "running"
                else:
                    ok, body = ok_text
                    status = "declined" if body == DECLINED else ("done" if ok else "error")
                items.append(
                    {
                        "id": f"{m.pk}:{call.id}",
                        "kind": "tool",
                        "call_id": call.id,
                        "name": call.name,
                        "title": tool_info(call.name)["title"],
                        "write": tool_info(call.name)["write"],
                        "arguments": call.arguments if isinstance(call.arguments, dict) else {},
                        "status": status,
                    }
                )
    if acc:  # tokens spent on turns that produced no text of their own (tool-only turns)
        items.append({"id": "usage", "kind": "usage", "usage": acc})
    return items


# ---------------------------------------------------------------- the loop


class Run:
    """One streamed request: a user message, or the person's decision on pending writes."""

    def __init__(self, conv, user, request, key):
        self.conv, self.user, self.request = conv, user, request
        self.key = key
        self.adapter = adapter_for(conv)
        self.code = code_exec.on(conv)  # VISION C1: Claude chats can run code
        self.tool_params = self.adapter.tool_params(tools.definitions(in_app=self.code))
        if self.code:
            self.tool_params.append(code_exec.TOOL)
        self.seq = conv.messages.aggregate(m=Max("seq"))["m"] or 0

    # -- persistence
    def _append(self, role, content, **kw) -> Message:
        self.seq += 1
        msg = Message.objects.create(
            conversation=self.conv, seq=self.seq, role=role, content=content, **kw
        )
        Conversation.objects.filter(pk=self.conv.pk).update(updated_at=timezone.now())
        return msg

    def _context(self, can_write):
        return tools.Context(
            user=self.user,
            lab_ids=frozenset({str(self.conv.lab_id)}),
            can_write=can_write,
            via="in_app",
            client=f"in-app assistant ({self.conv.provider} {self.conv.model})",
            grant_id="",
            request=self.request,
            run=self,
        )

    # -- entry points
    def send(self, text, page=None):
        yield from self._settle()
        self._append(Role.USER, self.adapter.user_content(page_prefix(page) + text))
        yield from self._loop()

    def decide(self, decisions: dict[str, bool]):
        calls = _pending_calls(self.conv)
        yield from self._run_tools(calls, {i for i, ok in decisions.items() if ok})
        yield from self._loop()

    def _settle(self):
        """The log may end on a turn whose tool calls have no results yet: a closed tab, or a
        write the person ignored by typing instead of clicking. Every call is answered first:
        reads run, writes are declined (only the Approve button runs a write)."""
        calls = _pending_calls(self.conv)
        if calls:
            yield from self._run_tools(calls, set())

    # -- tools
    def _run_tools(self, calls, approved):
        if not lab_allows(self.conv.lab_id):
            raise PolicyOff
        results = []
        for call in calls:
            t = tools.TOOLS.get(call.name)
            if t is None:
                results.append((call, False, "That tool does not exist."))
            elif t.write and call.id not in approved:
                try:  # a call that was never offered (bad arguments) gets its error, not "declined"
                    tools.validate_args(call.name, call.arguments)
                    results.append((call, False, DECLINED))
                except tools.ToolError as exc:
                    results.append((call, False, str(exc)))
            else:
                results.append(self._one(call, t))
            ok = results[-1][1]
            body = results[-1][2]
            status = "declined" if body == DECLINED else ("done" if ok else "error")
            yield {
                "type": "tool",
                "id": call.id,
                "name": call.name,
                "status": status,
                "title": tool_info(call.name)["title"],
            }
        # every result of the turn goes back in ONE message, failures marked
        self._append(Role.USER, self.adapter.tool_results(results))

    def _one(self, call, t):
        try:
            out = tools.call(self._context(can_write=t.write), call.name, call.arguments)
            return (call, True, json.dumps(out, ensure_ascii=False))
        except tools.ToolError as exc:
            return (call, False, str(exc))
        except Exception:  # a bug in a tool must not end the chat; log the type only
            log.exception("assistant tool %s failed", call.name)
            return (call, False, "The tool failed unexpectedly.")

    # -- the model loop
    def _loop(self):
        for _step in range(catalog.MAX_STEPS):
            if not lab_allows(self.conv.lab_id):
                raise PolicyOff
            history = self.adapter.history(self._replayable())
            self._sent_chars = len(self.conv.system_prompt or "") + len(
                json.dumps(history, default=str)
            )
            hold = None
            if isinstance(self.key, LabAIKey):  # VISION A5: removed, replaced or at the cap?
                self.key, hold = lab_keys.reserve(self.key, self._estimate(), self.conv.model)
            result, self._done = None, False
            try:
                turn = self._turn(history)
                try:
                    for ev in turn:
                        if isinstance(ev, TurnResult):
                            result = ev
                        else:
                            yield ev
                finally:
                    turn.close()  # D196: a closed connection must close the provider's stream now
                    if result is None and isinstance(self.key, LabAIKey):
                        self._charge_unfinished()
                yield from self._finish_turn(result)
            finally:
                if hold is not None:  # the real cost is recorded by now (or the call failed)
                    hold.delete()
            if self._done:
                return
        yield {
            "type": "notice",
            "code": "step_limit",
            "message": "I stopped after several steps. Ask me to continue if you want more.",
        }

    @sensitive_variables("api_key")
    def _turn(self, history):
        try:
            api_key = self.key.api_key()
        except Exception:
            raise provider_error("key_invalid", self.adapter.LABEL) from None
        extra = {"container": code_exec.container_for(self.conv, self.key)} if self.code else {}
        yield from self.adapter.stream_turn(
            api_key=api_key,
            model=self.conv.model,
            system=self.conv.system_prompt,
            messages=history,
            tools=self.tool_params,
            fallback=getattr(self.key, "refusal_fallback", True),
            **extra,
        )

    _done = False
    _sent_chars = 0

    def _estimate(self) -> dict:
        """What a turn may cost before the provider reports it: the request at about 3 characters
        a token plus the largest possible answer. Held against the lab's cap during the call, and
        charged if the turn is cut short."""
        return {"input_tokens": self._sent_chars // 3, "output_tokens": catalog.MAX_OUTPUT_TOKENS}

    def _charge_unfinished(self):
        """A turn cut short (Stop, closed tab, deadline, provider error) is still billed to the lab
        key, but the provider only reports usage at the end, so charge the estimate."""
        lab_keys.record_usage(self.key, self.user, self._estimate(), self.conv.model)

    def _replayable(self) -> list[Message]:
        """The log as it goes back to the model. A read result stored earlier is withheld if its
        item is flagged "Contains participant data" now, or has been deleted or hidden since: its
        text is replaced by the refusal, in this copy only, before any provider adapter sees it."""
        messages = _messages(self.conv)
        calls = {
            c.id: c
            for m in messages
            if m.role == Role.ASSISTANT and m.in_context
            for c in self.adapter.tool_calls(m.content)
            if c.name in tools.REPLAY_CHECKED
        }
        if not calls:
            return messages
        ctx = self._context(can_write=False)
        edited = False
        for m in messages:
            if m.role != Role.USER or not m.in_context:
                continue
            gone = {
                i
                for i, (ok, text) in self.adapter.results_of(m.content).items()
                if ok and i in calls and not tools.still_readable(ctx, calls[i], text)
            }
            if gone:
                m.content = self.adapter.refuse_results(m.content, gone, privacy.REFUSAL)
                edited = True
        if edited:  # an edited earlier turn invalidates every later thinking block (the API
            # answers 400); dropping all of them is the allowed shape, so do that on this copy
            for m in messages:
                if m.role == Role.ASSISTANT:
                    m.content = self.adapter.drop_thinking(m.content)
        return messages

    def _finish_turn(self, result: TurnResult):
        if self.code:
            code_exec.after_turn(self, result)
        calls = self.adapter.tool_calls(result.content)
        stop = result.stop
        # A refused turn, or one cut off inside a tool call, cannot be replayed: it is kept and
        # shown, but never sent back to the model.
        replayable = stop != "refusal" and not (stop == "max_tokens" and calls)
        meta = {k: v for k, v in result.meta.items() if v not in (None, False)}
        msg = self._append(
            Role.ASSISTANT,
            result.content,
            model=result.model,
            usage=result.usage,
            stop_reason=stop,
            in_context=replayable,
            meta=meta,
        )
        if isinstance(self.key, LabAIKey):
            lab_keys.record_usage(self.key, self.user, result.usage, result.model, self.conv.model)
        yield {
            "type": "assistant",
            "id": str(msg.pk),
            "model": result.model,
            "usage": result.usage,
            "stop_reason": stop,
            "fallback": bool(result.meta.get("fallback")),
        }
        self._done = True
        if stop == "refusal":
            yield {"type": "notice", "code": "refusal", "refusal": meta.get("refusal")}
            return
        if stop == "max_tokens":
            yield {
                "type": "notice",
                "code": "max_tokens",
                "message": "The answer was cut off because it hit the length limit.",
            }
            return
        if stop == "pause":
            self._done = False
            return
        if stop != "tool_use" or not calls:
            if meta.get("refusal"):  # OpenAI says no in-band, as ordinary text
                yield {"type": "notice", "code": "refusal", "refusal": meta["refusal"]}
            return
        needs = awaiting_approval(self.conv)
        if needs:
            yield {"type": "approval_required", "calls": needs}
            return
        yield from self._run_tools(calls, set())
        self._done = False


def start_event(conv):
    return {"type": "start", "conversation_id": str(conv.pk), "model": conv.model}


def error_event(exc: ProviderError) -> dict:
    return {"type": "error", "code": exc.code, "message": exc.message, "retryable": exc.retryable}
