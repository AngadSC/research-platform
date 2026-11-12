"""OpenAI adapter: the Responses API through the official `openai` SDK (D192).

It shares no request-building code with claude.py. OpenAI's docs say the GPT-6 models need the
Responses API for tool calling, so this is not the older Chat Completions format. Items are stored
as received and replayed; with `store=False` nothing is kept at OpenAI, so reasoning items come
back as encrypted content (`include=["reasoning.encrypted_content"]`).

Not verified against the live API (no key was available): the streaming event names, the
usage fields and the stateless replay of items were read from the installed SDK's types and
OpenAI's docs only. See docs/RUN5_NOTES.md."""

import json

import openai
from django.views.decorators.debug import sensitive_variables

from assistant.ai import catalog
from assistant.ai.types import ProviderError, ToolCall, TurnResult, provider_error

LABEL = "OpenAI"


def _client(api_key: str):
    return openai.OpenAI(
        api_key=api_key, max_retries=2, timeout=openai.Timeout(120.0, connect=10.0)
    )


def tool_params(definitions: list[dict]) -> list[dict]:
    # strict is off: our schemas have optional properties, which strict mode does not allow.
    return [
        {
            "type": "function",
            "name": d["name"],
            "description": d["description"],
            "parameters": d["input_schema"],
            "strict": False,
        }
        for d in definitions
    ]


def tool_calls(content: list) -> list[ToolCall]:
    calls = []
    for item in content:
        if item.get("type") != "function_call":
            continue
        try:
            args = json.loads(item.get("arguments") or "{}")
        except ValueError:
            args = item.get(
                "arguments"
            )  # a string: the tool layer says "Arguments must be an object"
        calls.append(ToolCall(item["call_id"], item["name"], args))
    return calls


def tool_results(results: list[tuple[ToolCall, bool, str]]) -> list[dict]:
    return [
        {
            "type": "function_call_output",
            "call_id": call.id,
            "output": text if ok else f"Error: {text}",
        }
        for call, ok, text in results
    ]


def refuse_code_output(content: list, text: str) -> list:
    return content  # no code execution on this provider


def drop_thinking(content: list) -> list:
    # OpenAI's encrypted reasoning is not bound to earlier history, and a function call replayed
    # without its reasoning item is rejected, so keep it.
    return content


def refuse_results(content: list, ids: set, text: str) -> list:
    """The same results with those calls' output replaced by `text`."""
    return [
        i | {"output": text}
        if i.get("type") == "function_call_output" and i["call_id"] in ids
        else i
        for i in content
    ]


def results_of(content: list) -> dict[str, tuple[bool, str]]:
    """call id -> (succeeded, text), for the timeline."""
    out = {}
    for i in content:
        if i.get("type") == "function_call_output":
            text = str(i.get("output", ""))
            out[i["call_id"]] = (not text.startswith("Error: "), text.removeprefix("Error: "))
    return out


def user_content(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def text_of(content: list) -> str:
    out = []
    for item in content:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    out.append(part.get("text", ""))
    return "".join(out)


def refusal_of(content: list) -> str:
    for item in content:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "refusal":
                    return part.get("refusal", "")
    return ""


def history(messages) -> list[dict]:
    """Stored messages -> Responses `input` items."""
    items: list[dict] = []
    for m in messages:
        if not m.in_context:
            continue
        if m.role == "user" and m.content and m.content[0].get("type") == "text":
            items.append({"role": "user", "content": m.content[0]["text"]})
        else:
            items.extend(m.content)
    return items


def _usage(final) -> dict:
    u = final.usage
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    return {
        "input_tokens": max((u.input_tokens or 0) - cached, 0),
        "output_tokens": u.output_tokens or 0,
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }


def _result(final) -> TurnResult:
    content = [item.model_dump(mode="json", exclude_none=True) for item in final.output]
    meta = {"request_id": getattr(final, "_request_id", None)}
    if any(i.get("type") == "function_call" for i in content):
        stop = "tool_use"
    elif final.status == "incomplete":
        reason = getattr(final.incomplete_details, "reason", "")
        stop = {"max_output_tokens": "max_tokens", "content_filter": "refusal"}.get(reason, "end")
        if stop == "refusal":
            meta["refusal"] = {"category": "content_filter", "explanation": None}
    else:
        stop = "end"
    if stop == "end" and (said := refusal_of(content)):
        meta["refusal"] = {"category": None, "explanation": said}  # in-band: text is replayable
    return TurnResult(content=content, stop=stop, model=final.model, usage=_usage(final), meta=meta)


@sensitive_variables("api_key")
def stream_turn(*, api_key, model, system, messages, tools, fallback=False):
    """Same contract as claude.stream_turn: events, then the TurnResult as the last item."""
    stream = None
    try:
        stream = _client(api_key).responses.create(
            model=model,
            instructions=system,
            input=messages,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=True,
            store=False,
            include=["reasoning.encrypted_content"],
            max_output_tokens=catalog.MAX_OUTPUT_TOKENS,
            stream=True,
        )
        final = None
        for event in stream:
            kind = event.type
            if kind == "response.output_text.delta":
                yield {"type": "text", "delta": event.delta}
            elif kind == "response.output_item.added" and event.item.type == "function_call":
                yield {"type": "tool_start", "name": event.item.name}
            elif kind in ("response.completed", "response.incomplete"):
                final = event.response
            elif kind in ("response.failed", "error"):
                raise provider_error("unavailable", LABEL)
            else:
                yield {"type": "ping"}
    except Exception as exc:
        raise translate(exc) from None
    finally:
        if stream is not None:
            stream.close()
    if final is None:
        raise provider_error("connection", LABEL)
    yield _result(final)


def translate(exc: Exception) -> ProviderError:
    """Most specific first; retryable (429, 5xx, network) apart from the rest (4xx)."""
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", 0)
    table = [
        (openai.AuthenticationError, "key_invalid"),
        (openai.PermissionDeniedError, "key_forbidden"),
        (openai.NotFoundError, "model_unavailable"),
        (openai.BadRequestError, "bad_request"),
        (openai.UnprocessableEntityError, "bad_request"),
        (openai.RateLimitError, "rate_limited"),
        (openai.InternalServerError, "unavailable"),
        (openai.APITimeoutError, "timeout"),
        (openai.APIConnectionError, "connection"),
    ]
    for cls, code in table:
        if isinstance(exc, cls):
            if cls is openai.RateLimitError and getattr(exc, "code", "") == "insufficient_quota":
                return provider_error("billing", LABEL, status)
            wait = (
                exc.response.headers.get("retry-after", "") if cls is openai.RateLimitError else ""
            )
            return provider_error(code, LABEL, status, wait)
    if isinstance(exc, openai.APIStatusError):
        return provider_error("billing" if status == 402 else "unknown", LABEL, status)
    return provider_error("unknown", LABEL)


@sensitive_variables()  # all locals, wrapper arguments included
def check_key(api_key: str) -> None:
    """The cheap call made when a key is saved: listing models is free. Raises ProviderError."""
    try:
        _client(api_key).with_options(max_retries=0, timeout=15.0).models.list()
    except Exception as exc:
        raise translate(exc) from None
