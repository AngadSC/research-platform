"""Low-stock alerts (D331). When an item's stock falls to the level its owner set, the lab's PIs
and admins and the item's owner get a notification and an email. It fires when stock crosses
the level on the way down, at most once a day per item, so a busy day does not flood anyone."""

from django.utils import timezone

from core.models import NotificationKind
from core.notifications import notify
from labs.models import InventoryItem, LabMembership, LabRole


def _num(value) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def is_low(item) -> bool:
    return item.low_stock_at is not None and item.quantity <= item.low_stock_at


def check(item_id, lab_id, *, before) -> bool:
    """Alert if the item has just fallen to its level. `before` is the stock before the change."""
    item = (
        InventoryItem.objects.for_lab(lab_id)
        .select_related("lab", "owner")
        .filter(pk=item_id)
        .first()
    )
    if item is None or item.low_stock_at is None:
        return False
    if not (before > item.low_stock_at >= item.quantity):
        return False
    people = {
        m.user_id: m.user
        for m in LabMembership.objects.for_lab(lab_id)
        .filter(role__in=[LabRole.PI, LabRole.LAB_ADMIN])
        .select_related("user")
        if m.user.is_active
    }
    if item.owner is not None and item.owner.is_active:
        people.setdefault(item.owner_id, item.owner)
    left = f"{_num(item.quantity)} {item.unit}".strip()
    level = f"{_num(item.low_stock_at)} {item.unit}".strip()
    body = f"{left} left, at or below the alert level of {level}."
    sent = False
    for user in people.values():
        sent |= notify(
            lab=item.lab,
            recipient=user,
            kind=NotificationKind.LOW_STOCK,
            title=f"{item.name} is running low",
            body=body,
            target=item,
            dedupe_key=f"low-stock:{item.pk}:{timezone.localdate().isoformat()}",
        )
    return sent
