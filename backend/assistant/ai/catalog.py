"""Providers, models and the knobs we send (D187, D189). One place to change a model id.

Claude ids are exactly the strings in Anthropic's docs, with no date suffix, checked again on
2026-11-10 (D245): Opus 5.5, Sonnet 5.5 and Haiku 5.5 are current, and Fable 5.2 replaced Fable
5.1 at a lower price. Fable takes the same request as the others here (adaptive thinking, an
explicit effort, auto tool choice, the server-side fallback). OpenAI ids were read
from developers.openai.com/api/docs/models on 2026-11-05 (the docs say GPT-6 models need the
Responses API for tool calling, which is what the OpenAI adapter uses). Prices are USD per million
tokens, list price, used for the "about $x" estimate shown next to a message and for the lab
key's monthly cap (`cost`)."""

from decimal import Decimal

from assistant.models import Provider

MODELS = {
    Provider.ANTHROPIC: [
        {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "input": 4.0, "output": 20.0},
        {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "input": 2.0, "output": 10.0},
        {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "input": 0.10, "output": 0.50},
        {"id": "claude-fable-5-2", "label": "Claude Fable 5.2", "input": 8.0, "output": 40.0},
    ],
    Provider.OPENAI: [
        {"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol", "input": 2.0, "output": 10.0},
        {"id": "gpt-6-astra", "label": "GPT-6 Astra", "input": 10.0, "output": 50.0},
        {"id": "gpt-6.1-terra", "label": "GPT-6.1 Terra", "input": 1.0, "output": 5.0},
        {"id": "gpt-6-luna", "label": "GPT-6 Luna", "input": 0.10, "output": 0.50},
    ],
}
DEFAULT_MODEL = {Provider.ANTHROPIC: "claude-opus-5-5", Provider.OPENAI: "gpt-6.1-sol"}
LABELS = {Provider.ANTHROPIC: "Anthropic (Claude)", Provider.OPENAI: "OpenAI"}

# Claude: output_config.effort. Multistep tool use is what this assistant does, and Anthropic's
# guidance for it is `medium` (`low` is for plain chat); medium is also Opus 5.5's own default,
# but it is sent explicitly so a changed default never changes our cost.
CLAUDE_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 16000
MAX_STEPS = 8  # model calls per user message (a step is one call plus its tool results)
MAX_TEXT = 8000  # characters in one user message
MAX_MESSAGES = 200  # per conversation

# Claude models without server-side fallback (the parameter would be rejected or do nothing).
NO_FALLBACK = {"claude-haiku-5-5"}


def model_ids(provider) -> list[str]:
    return [m["id"] for m in MODELS[provider]]


def cost(usage: dict, *models: str) -> Decimal:
    """USD at list price for one turn's tokens, the same sum as the panel's estimate
    (frontend/src/lib/assistant.ts): cached reads at a tenth, cache writes at 1.25 times. Priced
    by the first listed model in `models` (the model that answered, then the conversation's)."""
    listed = {m["id"]: m for ms in MODELS.values() for m in ms}
    price = next((listed[m] for m in models if m in listed), None)
    if price is None:  # fail closed: an unlisted model is priced as the dearest one
        price = max(listed.values(), key=lambda m: Decimal(str(m["output"])))
    p_in, p_out = Decimal(str(price["input"])), Decimal(str(price["output"]))
    u = {k: int(usage.get(k) or 0) for k in USAGE_KEYS}
    total = (
        u["input_tokens"] * p_in
        + u["cache_read_tokens"] * p_in / 10
        + u["cache_write_tokens"] * p_in * Decimal("1.25")
        + u["output_tokens"] * p_out
    )
    return total / 1_000_000


USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
