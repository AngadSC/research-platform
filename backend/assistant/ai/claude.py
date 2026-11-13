"""Claude adapter: the Anthropic Messages API through the official `anthropic` SDK (D189).

Choices, each recorded in DECISIONS:
- A manual tool loop (chat.py) rather than the SDK tool runner: the loop must stop for the
  person's approval before a write, persist every content block, and stream to the browser.
- `stream_turn` streams one model call (`messages.stream`) and returns the finished turn.
- thinking {"type": "adaptive"} and an explicit output_config.effort; tool_choice auto (forced
  choice is a 400 on these models); no assistant prefill; every tool has eager_input_streaming and
  its parsed input is validated by the tool layer before it runs.
- Refusal fallback: beta `server-side-fallback-2026-07-01` with `fallbacks: "default"`, on unless
  the person turned it off; never sent for Haiku (it has no server-side fallback).
- Assistant content is stored and replayed unchanged, thinking blocks included. The one exception
  is the API's own rule for a turn that fell back mid-output (see `replay`)."""

import anthropic
from django.views.decorators.debug import sensitive_variables

from assistant.ai import catalog
from assistant.ai.types import ProviderError, ToolCall, TurnResult, provider_error

LABEL = "Anthropic"
BETA_FALLBACK = "server-side-fallback-2026-07-01"
STOPS = {"end_turn": "end", "stop_sequence": "end", "pause_turn": "pause"}
CODE_RESULTS = {"bash_code_execution_tool_result", "text_editor_code_execution_tool_result"}
MAX_JSON_RETRIES = 2  # a tool input the SDK could not parse at all: re-issue the turn, bounded


def _client(api_key: str):
    return anthropic.Anthropic(
        api_key=api_key, max_retries=2, timeout=anthropic.Timeout(120.0, connect=10.0)
    )


def tool_params(definitions: list[dict]) -> list[dict]:
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "input_schema": d["input_schema"],
            "eager_input_streaming": True,
        }
        for d in definitions
    ]


def _last_fallback(content: list) -> int:
    return max((i for i, b in enumerate(content) if b.get("type") == "fallback"), default=-1)


def tool_calls(content: list) -> list[ToolCall]:
    """Only blocks of the final attempt can run: a tool_use before a fallback marker belongs to
    the declined attempt."""
    return [
        ToolCall(b["id"], b["name"], b.get("input"))
        for b in content[_last_fallback(content) + 1 :]
        if b.get("type") == "tool_use"
    ]


def tool_results(results: list[tuple[ToolCall, bool, str]]) -> list[dict]:
    """ALL results of a turn, in one user message; failures carry is_error."""
    return [
        {"type": "tool_result", "tool_use_id": call.id, "content": text}
        | ({} if ok else {"is_error": True})
        for call, ok, text in results
    ]


def refuse_results(content: list, ids: set, text: str) -> list:
    """The same results with those calls' output replaced by `text`."""
    return [
        b | {"content": text} if b.get("type") == "tool_result" and b["tool_use_id"] in ids else b
        for b in content
    ]


def refuse_code_output(content: list, text: str) -> list:
    """The turn with what code printed or read replaced by `text` (its input was flagged since)."""
    bash = {"type": "bash_code_execution_result", "stdout": text, "stderr": "", "return_code": 0}
    editor = {"type": "text_editor_code_execution_tool_result_error", "error_code": "unavailable"}
    return [
        (
            b | {"content": bash | {"content": []}}
            if b.get("type") == "bash_code_execution_tool_result"
            else (
                b | {"content": editor}
                if b.get("type") == "text_editor_code_execution_tool_result"
                else b
            )
        )
        for b in content
    ]


def drop_thinking(content: list) -> list:
    """The turn without its thinking blocks (they are bound to the history they came from)."""
    return [b for b in content if b.get("type") not in ("thinking", "redacted_thinking")]


def results_of(content: list) -> dict[str, tuple[bool, str]]:
    """call id -> (succeeded, text), for the timeline."""
    return {
        b["tool_use_id"]: (not b.get("is_error"), str(b.get("content", "")))
        for b in content
        if b.get("type") == "tool_result"
    }


def user_content(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def text_of(content: list) -> str:
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def replay(content: list) -> list:
    """The API's rule for echoing a turn that fell back mid-output: leave out thinking,
    redacted_thinking and tool_use blocks that come before the final fallback marker. Anything
    else goes back exactly as received."""
    last = _last_fallback(content)
    if last < 0:
        return content
    drop = {"thinking", "redacted_thinking", "tool_use"}
    return [b for i, b in enumerate(content) if not (i < last and b.get("type") in drop)]


def history(messages) -> list[dict]:
    """Stored messages -> request messages. Turns that were refused or cut off stay out."""
    return [
        {"role": m.role, "content": replay(m.content) if m.role == "assistant" else m.content}
        for m in messages
        if m.in_context
    ]


def _usage(final) -> dict:
    u = final.usage
    return {
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }


def _result(final) -> TurnResult:
    stop = STOPS.get(final.stop_reason, final.stop_reason or "end")
    meta = {"request_id": getattr(final, "_request_id", None)}
    container = getattr(final, "container", None)
    meta["container"] = getattr(container, "id", None)  # code execution (VISION C1)
    iterations = getattr(final.usage, "iterations", None) or []
    meta["fallback"] = any(getattr(i, "type", "") == "fallback_message" for i in iterations)
    if stop == "refusal":  # stop_details is only meaningful on a refusal
        sd = final.stop_details
        meta["refusal"] = {
            "category": getattr(sd, "category", None),
            "explanation": getattr(sd, "explanation", None),
            "recommended_model": getattr(sd, "recommended_model", None),
        }
    return TurnResult(
        content=[b.to_dict() for b in final.content],
        stop=stop,
        model=final.model,
        usage=_usage(final),
        meta=meta,
    )


@sensitive_variables("api_key")
def stream_turn(*, api_key, model, system, messages, tools, fallback=True, container=None):
    """Generator of events {"type": "text"|"tool_start"|"tool"|"ping"|"retry", ...}; the last item
    is the TurnResult. Raises ProviderError (fixed text, retryable flag). `container` reuses a code
    execution container (VISION C1)."""
    client = _client(api_key)
    kwargs = {
        "model": model,
        "max_tokens": catalog.MAX_OUTPUT_TOKENS,
        "system": system,
        "messages": messages,
        "tools": tools,
        "tool_choice": {"type": "auto"},
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": catalog.CLAUDE_EFFORT},
        "cache_control": {"type": "ephemeral"},
    }
    if container:
        kwargs["container"] = container
    use_fallback = fallback and model not in catalog.NO_FALLBACK
    api = client.beta.messages if use_fallback else client.messages
    if use_fallback:
        kwargs |= {"betas": [BETA_FALLBACK], "fallbacks": "default"}
    attempts = 0
    while True:
        try:
            with api.stream(**kwargs) as stream:
                for event in stream:
                    block = event.content_block.type if event.type == "content_block_start" else ""
                    if event.type == "text":
                        yield {"type": "text", "delta": event.text}
                    elif block == "tool_use":
                        yield {"type": "tool_start", "name": event.content_block.name}
                    elif block == "server_tool_use":  # code execution runs on Anthropic's side
                        yield {"type": "tool_start", "name": "run_code"}
                    elif block in CODE_RESULTS:
                        yield {
                            "type": "tool",
                            "name": "run_code",
                            "title": "Ran code",
                            "status": "done",
                        }
                    else:
                        yield {"type": "ping"}
                final = stream.get_final_message()
            break
        except ValueError:
            # Eager input streaming: JSON the SDK could not parse at all. API errors are not
            # ValueErrors, so they fall through to the typed chain in `translate`.
            attempts += 1
            if attempts > MAX_JSON_RETRIES:
                raise provider_error("unknown", LABEL) from None
            yield {"type": "retry"}
        except (anthropic.BadRequestError, anthropic.NotFoundError) as exc:
            if "container" not in kwargs:
                raise translate(exc) from None
            kwargs.pop("container")  # a stale container (another org's, or expired): start anew
            yield {"type": "retry"}
        except Exception as exc:
            raise translate(exc) from None
    yield _result(final)


def translate(exc: Exception) -> ProviderError:
    """Most specific first; retryable (429, 5xx, network) apart from the rest (4xx)."""
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", 0)
    if isinstance(exc, anthropic.BadRequestError):
        text = str(getattr(exc, "message", "")).lower()
        # replaying history whose thinking signatures no longer match (tools or prompt changed)
        code = "stale" if "signature" in text and "thinking" in text else "bad_request"
        return provider_error(code, LABEL, status)
    table = [
        (anthropic.AuthenticationError, "key_invalid"),
        (anthropic.PermissionDeniedError, "key_forbidden"),
        (anthropic.NotFoundError, "model_unavailable"),
        (anthropic.RequestTooLargeError, "too_large"),
        (anthropic.UnprocessableEntityError, "bad_request"),
        (anthropic.RateLimitError, "rate_limited"),
        (anthropic.OverloadedError, "overloaded"),
        (anthropic.ServiceUnavailableError, "unavailable"),
        (anthropic.InternalServerError, "unavailable"),
        (anthropic.APITimeoutError, "timeout"),
        (anthropic.APIConnectionError, "connection"),
    ]
    for cls, code in table:
        if isinstance(exc, cls):
            wait = ""
            if cls is anthropic.RateLimitError:
                wait = exc.response.headers.get("retry-after", "")
            return provider_error(code, LABEL, status, wait)
    if isinstance(exc, anthropic.APIStatusError):
        return provider_error("billing" if status == 402 else "unknown", LABEL, status)
    return provider_error("unknown", LABEL)


@sensitive_variables()  # all locals, wrapper arguments included
def check_key(api_key: str) -> None:
    """The cheap call made when a key is saved: listing one model is free and proves the key
    works. Raises ProviderError."""
    try:
        _client(api_key).with_options(max_retries=0, timeout=15.0).models.list(limit=1)
    except Exception as exc:
        raise translate(exc) from None
