"""Fake provider SDK clients, patched in at the client boundary (`claude._client` and
`openai_responses._client`). Tests never make a network call: the real SDK response types are built
from dicts, so the adapters parse exactly what the SDK would give them."""

from types import SimpleNamespace

from anthropic.types.beta import BetaMessage
from openai.types.responses import Response

CANARY_KEY = "sk-ant-api03-CANARYKEYabcdefghijklmnop1234"
OPENAI_CANARY = "sk-proj-CANARYOPENAIabcdefghijklmnop5678"
LAB_CANARY = "sk-ant-api03-CANARYLABKEYabcdefghijklmn9753"  # a lab's key (VISION A5)

# ---------------------------------------------------------------- Claude


def claude_message(content, stop="end_turn", model="claude-opus-5-5", usage=None, **extra):
    return BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 20, **(usage or {})},
            **extra,
        }
    )


def text(t):
    return {"type": "text", "text": t, "citations": None}


def tool_use(id_, name, args):
    return {"type": "tool_use", "id": id_, "name": name, "input": args}


class _Manager:
    def __init__(self, script):
        self.script = script

    def __enter__(self):
        if isinstance(self.script, Exception):
            raise self.script
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.script.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)
            elif block.type == "tool_use":
                yield SimpleNamespace(
                    type="content_block_start",
                    content_block=SimpleNamespace(type="tool_use", name=block.name),
                )
            else:
                yield SimpleNamespace(type="content_block_delta")

    def get_final_message(self):
        return self.script


class FakeClaude:
    """Each `stream()` call pops the next script: a BetaMessage, or an Exception to raise."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.calls = []  # the keyword arguments of every request
        self.beta = SimpleNamespace(messages=self)
        self.messages = self
        self.models = SimpleNamespace(list=self._list)
        self.listed = []
        self.list_error = None  # raised by models.list: the key check made when a key is saved

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _Manager(self.scripts.pop(0))

    def _list(self, **kwargs):
        self.listed.append(kwargs)
        if self.list_error is not None:
            raise self.list_error

    def with_options(self, **kwargs):
        return self


def patch_claude(monkeypatch, *scripts):
    from assistant.ai import claude

    fake = FakeClaude(*scripts)
    monkeypatch.setattr(claude, "_client", lambda api_key: fake)
    return fake


# ---------------------------------------------------------------- OpenAI


def openai_response(output, status="completed", model="gpt-6.1-sol", usage=None, **extra):
    return Response.model_validate(
        {
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "model": model,
            "output": output,
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "status": status,
            "usage": {
                "input_tokens": 120,
                "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 0},
                "output_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 150,
                **(usage or {}),
            },
            **extra,
        }
    )


def o_message(t):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": t, "annotations": []}],
    }


def o_call(call_id, name, args_json):
    return {
        "id": f"fc_{call_id}",
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": args_json,
        "status": "completed",
    }


class _OpenAIStream:
    def __init__(self, response):
        self.response = response
        self.closed = False

    def __iter__(self):
        for item in self.response.output:
            if item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        yield SimpleNamespace(type="response.output_text.delta", delta=part.text)
            elif item.type == "function_call":
                yield SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(type="function_call", name=item.name),
                )
        kind = (
            "response.completed" if self.response.status == "completed" else "response.incomplete"
        )
        yield SimpleNamespace(type=kind, response=self.response)

    def close(self):
        self.closed = True


class FakeOpenAI:
    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)
        self.models = SimpleNamespace(list=self._list)
        self.list_error = None
        self.listed = 0

    def _list(self, **kwargs):
        self.listed += 1
        if self.list_error is not None:
            raise self.list_error

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        script = self.scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        return _OpenAIStream(script)

    def with_options(self, **kwargs):
        return self


def patch_openai(monkeypatch, *scripts):
    from assistant.ai import openai_responses

    fake = FakeOpenAI(*scripts)
    monkeypatch.setattr(openai_responses, "_client", lambda api_key: fake)
    return fake
