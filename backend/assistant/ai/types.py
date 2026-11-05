"""What the two adapters hand to the chat loop. These describe a finished turn, not a request
format: each adapter builds its own provider's request and keeps its own provider's content."""

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: object  # parsed JSON; validated by the tool layer before anything runs


@dataclass
class TurnResult:
    content: list  # provider-native content, stored and replayed unchanged
    stop: str  # end | tool_use | max_tokens | refusal | pause
    model: str  # the model that answered (can differ from the one asked: fallback)
    usage: dict = field(default_factory=dict)  # input_tokens, output_tokens, cache tokens
    meta: dict = field(default_factory=dict)  # refusal details, fallback flag, request id


class ProviderError(Exception):
    """A failure to show the person. `message` is fixed text we wrote, never the provider's own
    (which could echo request content). `retryable` means trying again may work."""

    def __init__(self, code: str, message: str, retryable: bool = False, status: int = 0):
        super().__init__(message)
        self.code, self.message, self.retryable, self.status = code, message, retryable, status


def provider_error(code: str, label: str, status: int = 0, retry_after: str = "") -> ProviderError:
    """Fixed, friendly text per failure class. `label` is "Anthropic" or "OpenAI"."""
    wait = (
        f" Try again in {retry_after} seconds." if retry_after.isdigit() else " Try again shortly."
    )
    table = {
        "key_invalid": (f"{label} rejected your API key. Check it in Settings > AI.", False),
        "key_forbidden": (f"Your {label} key is not allowed to do that.", False),
        "model_unavailable": (
            f"Your {label} account cannot use this model. Choose another.",
            False,
        ),
        "too_large": ("This conversation is too long for the model. Start a new one.", False),
        "bad_request": (f"{label} could not process this request.", False),
        "stale": (
            "This conversation can no longer be continued because the assistant changed since it "
            "started. Start a new one.",
            False,
        ),
        "billing": (f"{label} says there is a billing problem with your account.", False),
        "rate_limited": (f"{label} is rate limiting your key.{wait}", True),
        "overloaded": (f"{label} is overloaded right now.{wait}", True),
        "unavailable": (f"{label} had a problem on its side.{wait}", True),
        "timeout": (f"{label} took too long to answer.{wait}", True),
        "connection": (f"We could not reach {label}.{wait}", True),
        "unknown": (f"Something went wrong talking to {label}.", False),
    }
    message, retryable = table[code]
    return ProviderError(code, message, retryable, status)
