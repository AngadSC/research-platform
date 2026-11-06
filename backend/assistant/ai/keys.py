"""A person's own provider API keys (D187). Per user, encrypted with the integrations MultiFernet
(D63), checked with one free provider call when saved, never returned (only the last 4 characters),
never logged, audited or put in an error. `sensitive_variables` keeps the plaintext out of Django's
debug and error-report pages."""

import re

from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from assistant.ai import catalog, claude, openai_responses
from assistant.ai.types import ProviderError
from assistant.models import AIProviderKey, Provider
from audit.models import AuditAction
from audit.services import record
from core.permissions import labs_for

CHECKERS = {Provider.ANTHROPIC: claude, Provider.OPENAI: openai_responses}
# Shapes only, so a pasted sentence or the wrong provider's key is caught before any network call.
SHAPE = {
    Provider.ANTHROPIC: re.compile(r"^sk-ant-[A-Za-z0-9_\-]{16,380}$"),
    Provider.OPENAI: re.compile(r"^sk-(?!ant-)[A-Za-z0-9_\-]{16,380}$"),
}
WRONG_SHAPE = "That does not look like a {label} API key."


@sensitive_variables()  # all locals, wrapper arguments included
def clean(provider, raw: str) -> str:
    raw = (raw or "").strip()
    if not SHAPE[provider].match(raw):
        raise ValidationError({"api_key": WRONG_SHAPE.format(label=catalog.LABELS[provider])})
    return raw


@sensitive_variables()  # all locals, wrapper arguments included
def check(provider, api_key: str) -> None:
    """The cheap provider call. A seam for tests, which never reach the network."""
    CHECKERS[provider].check_key(api_key)


def status(user) -> list[dict]:
    """One entry per provider: saved or not, and the last 4 characters. Nothing else."""
    rows = {k.provider: k for k in AIProviderKey.objects.filter(user=user)}
    return [
        {
            "provider": p,
            "label": catalog.LABELS[p],
            "saved": p in rows,
            "last4": rows[p].last4 if p in rows else "",
            "updated_at": rows[p].updated_at if p in rows else None,
            "refusal_fallback": rows[p].refusal_fallback if p in rows else True,
        }
        for p in Provider.values
    ]


@sensitive_variables()  # all locals, wrapper arguments included
def save(user, provider, raw: str, *, request=None) -> AIProviderKey:
    """Check the key with the provider first (outside any transaction), then store it."""
    api_key = clean(provider, raw)
    try:
        check(provider, api_key)
    except ProviderError as exc:
        # a 4xx from the provider means the key is no good; a 5xx or a network error means we
        # could not tell, and nothing is stored either way
        raise ValidationError({"api_key": exc.message}) from None
    with transaction.atomic():
        row, _ = AIProviderKey.objects.select_for_update().get_or_create(
            user=user, provider=provider
        )
        row.set_key(api_key)
        row.last_tested_at = timezone.now()
        row.save()
        _audit(AuditAction.AI_KEY_SAVED, user, provider, request)
    return row


def set_fallback(user, provider, enabled: bool) -> AIProviderKey | None:
    row = AIProviderKey.objects.filter(user=user, provider=provider).first()
    if row is not None:
        row.refusal_fallback = enabled
        row.save(update_fields=["refusal_fallback", "updated_at"])
    return row


@transaction.atomic
def remove(user, provider, *, request=None) -> bool:
    deleted, _ = AIProviderKey.objects.filter(user=user, provider=provider).delete()
    if deleted:
        _audit(AuditAction.AI_KEY_REMOVED, user, provider, request)
    return bool(deleted)


def _audit(action, user, provider, request):
    """Keys belong to the person, not a lab; audit events need a lab, so one per lab they are in."""
    for lab in labs_for(user):
        record(action, actor=user, lab=lab, request=request, metadata={"provider": provider})


def rotate_all() -> int:
    """Re-encrypt every stored key under the newest INTEGRATION_ENCRYPTION_KEYS key (D63)."""
    from integrations import crypto

    n = 0
    for row in AIProviderKey.objects.all():
        row.key_ciphertext = crypto.rotate(row.key_ciphertext)
        row.save(update_fields=["key_ciphertext", "updated_at"])
        n += 1
    return n
