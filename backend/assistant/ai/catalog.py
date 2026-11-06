"""Providers, models and the knobs we send (D187, D189). One place to change a model id.

Claude ids are exactly the strings in Anthropic's docs, with no date suffix. OpenAI ids were read
from developers.openai.com/api/docs/models on 2026-11-05 (the docs say GPT-6 models need the
Responses API for tool calling, which is what the OpenAI adapter uses). Prices are USD per million
tokens, list price, used only for the "about $x" estimate shown next to a message."""

from assistant.models import Provider

MODELS = {
    Provider.ANTHROPIC: [
        {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "input": 4.0, "output": 20.0},
        {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "input": 2.0, "output": 10.0},
        {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "input": 0.10, "output": 0.50},
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
