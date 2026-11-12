"""The lab's AI key and its monthly cap (VISION A5). A PI or lab admin (manage_lab, the same
permission as the lab's AI policy) sets one provider key for the lab. It is checked, stored and
hidden exactly like a personal key (assistant/ai/keys.py). A person's own key for the
conversation's provider always wins; otherwise the lab key is used while this month's lab spend is
under the cap. Spend is each turn's tokens at list price (catalog.cost), per person per month."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from assistant.ai import catalog, keys
from assistant.ai.types import ProviderError
from assistant.models import AIProviderKey, LabAIKey, LabAIUsage
from audit.models import AuditAction
from audit.services import record

LIMIT_MESSAGE = (
    "Your lab has reached this month's AI limit. Ask your PI, or add your own key in Settings, "
    "under AI."
)
GONE_MESSAGE = "Your lab's AI key was removed. Add your own key in Settings, under AI."


class Unavailable(Exception):
    """The lab key cannot be used for this turn: the cap is reached, or the key is gone."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def this_month():
    return timezone.localdate().replace(day=1)


def get(lab) -> LabAIKey | None:
    return LabAIKey.objects.for_lab(lab).first()


def spent(lab) -> Decimal:
    total = (
        LabAIUsage.objects.for_lab(lab).filter(month=this_month()).aggregate(s=Sum("cost_usd"))["s"]
    )
    return total or Decimal(0)


def under_cap(row: LabAIKey) -> bool:
    return spent(row.lab_id) < row.monthly_cap_usd


def usage(lab) -> list[dict]:
    """This month, per person, most spent first."""
    rows = (
        LabAIUsage.objects.for_lab(lab)
        .filter(month=this_month())
        .select_related("user")
        .order_by("-cost_usd")
    )
    return [
        {
            "user": r.user_id,
            "name": r.user.display_name or r.user.email,
            "cost_usd": r.cost_usd,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }
        for r in rows
    ]


# ---------------------------------------------------------------- which key a turn uses


def key_for(user, lab, provider):
    """The person's own key wins; then the lab's key for this provider while under the cap. None
    when there is neither. The caller has already checked that the lab allows the assistant."""
    own = AIProviderKey.objects.filter(user=user, provider=provider).first()
    if own is not None:
        return own
    row = LabAIKey.objects.for_lab(lab).filter(provider=provider).first()
    if row is None:
        return None
    if not under_cap(row):
        raise Unavailable("lab_limit", LIMIT_MESSAGE)
    return row


def recheck(row: LabAIKey) -> LabAIKey:
    """Before each model call of a running answer: the key may have been removed or replaced, or
    the cap reached, since the answer started."""
    fresh = LabAIKey.objects.for_lab(row.lab_id).filter(provider=row.provider).first()
    if fresh is None:
        raise Unavailable("no_key", GONE_MESSAGE)
    if not under_cap(fresh):
        raise Unavailable("lab_limit", LIMIT_MESSAGE)
    return fresh


def record_usage(row: LabAIKey, user, turn_usage: dict, *models) -> None:
    """Add one turn's cost and tokens to this person's row for this month."""
    cost = catalog.cost(turn_usage, *models)
    tokens_in = sum(int(turn_usage.get(k) or 0) for k in catalog.USAGE_KEYS if k != "output_tokens")
    tokens_out = int(turn_usage.get("output_tokens") or 0)
    scope = dict(user=user, month=this_month())
    add = dict(
        cost_usd=F("cost_usd") + cost,
        input_tokens=F("input_tokens") + tokens_in,
        output_tokens=F("output_tokens") + tokens_out,
    )
    if LabAIUsage.objects.for_lab(row.lab_id).filter(**scope).update(**add):
        return
    try:
        with transaction.atomic():
            LabAIUsage.objects.create(
                lab_id=row.lab_id,
                cost_usd=cost,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                **scope,
            )
    except IntegrityError:  # another turn created the row first
        LabAIUsage.objects.for_lab(row.lab_id).filter(**scope).update(**add)


# ---------------------------------------------------------------- set, cap, remove


@sensitive_variables()  # all locals, wrapper arguments included
def save(lab, user, provider, raw: str, cap: Decimal, *, request=None) -> LabAIKey:
    """Check the key with the provider first (outside any transaction), then store it."""
    api_key = keys.clean(provider, raw)
    try:
        keys.check(provider, api_key)
    except ProviderError as exc:
        raise ValidationError({"api_key": exc.message}) from None
    with transaction.atomic():
        row = LabAIKey.objects.for_lab(lab).select_for_update().first()
        replaced = row is not None
        old_cap = row.monthly_cap_usd if replaced else None
        row = row or LabAIKey(lab=lab)
        row.provider = provider
        row.set_key(api_key)
        row.monthly_cap_usd = cap
        row.save()
        action = AuditAction.LAB_AI_KEY_REPLACED if replaced else AuditAction.LAB_AI_KEY_SET
        meta = {"provider": provider, "monthly_cap_usd": str(cap)}
        record(action, actor=user, lab=lab, request=request, metadata=meta)
        if replaced and old_cap != cap:
            _cap_changed(lab, user, old_cap, cap, request)
    return row


@transaction.atomic
def set_cap(lab, user, cap: Decimal, *, request=None) -> LabAIKey | None:
    row = LabAIKey.objects.for_lab(lab).select_for_update().first()
    if row is not None and row.monthly_cap_usd != cap:
        old = row.monthly_cap_usd
        row.monthly_cap_usd = cap
        row.save(update_fields=["monthly_cap_usd", "updated_at"])
        _cap_changed(lab, user, old, cap, request)
    return row


@transaction.atomic
def remove(lab, user, *, request=None) -> bool:
    row = LabAIKey.objects.for_lab(lab).select_for_update().first()
    if row is None:
        return False
    provider = row.provider
    row.delete()
    record(
        AuditAction.LAB_AI_KEY_REMOVED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"provider": provider},
    )
    return True


def _cap_changed(lab, user, old, new, request):
    record(
        AuditAction.LAB_AI_CAP_CHANGED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"from": str(old), "to": str(new)},
    )
