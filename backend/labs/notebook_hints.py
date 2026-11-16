"""What a notebook entry says about inventory and protocols (D332). The author reads their own
text here, nothing more: a hint is a suggestion the author accepts with one click, and nothing is
taken from stock until they do. A personal notebook is never read for anyone else.

- "10 mL ethanol" or "2 g of NaCl" names an item and an amount in a unit that fits it.
  Each such mention gets a fixed request id, so accepting it twice takes stock once.
- A mention that looks like a use already logged by hand is flagged as a possible duplicate.
- Where the text names a protocol, amounts that differ from the protocol's are noted as changes.
"""

import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from labs.models import InventoryItem, InventoryUsage, Protocol, ProtocolReagent
from labs.units import convert

NAMESPACE = uuid.UUID("5f1c7a52-2d3e-4b0e-9a54-6f2f0b7c1d10")
AMOUNT = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*([A-Za-zµμ]{1,12})\b\s*(?:of\s+)?", re.UNICODE)
MAX_HINTS = 50
SNIPPET = 90


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _snippet(body: str, start: int, end: int) -> str:
    lo, hi = max(0, start - 25), min(len(body), end + 40)
    return re.sub(r"\s+", " ", body[lo:hi]).strip()[:SNIPPET]


def mentions(body: str, items) -> list[dict]:
    """Every "amount unit [of] item" in `body` whose unit fits the item, in text order."""
    names = sorted(((i.name.strip(), i) for i in items if i.name.strip()), key=lambda x: -len(x[0]))
    out, seen = [], {}
    for m in AMOUNT.finditer(body):
        amount = _dec(m.group(1))
        if amount is None or amount <= 0:
            continue
        rest = body[m.end() :]
        for name, item in names:
            if rest[: len(name)].casefold() != name.casefold():
                continue
            nxt = rest[len(name) : len(name) + 1]
            if nxt.isalnum():  # "ethanolamine" is not "ethanol"
                continue
            if convert(amount, m.group(2), item.unit) is None:
                continue
            key = (item.pk, str(amount), m.group(2).casefold())
            seen[key] = seen.get(key, 0) + 1
            out.append(
                {
                    "item": item,
                    "amount": amount,
                    "unit": m.group(2),
                    "n": seen[key],
                    "snippet": _snippet(body, m.start(), m.end() + len(name)),
                }
            )
            break
        if len(out) >= MAX_HINTS:
            break
    return out


def request_id(entry, hint) -> uuid.UUID:
    """The same mention always has the same id, so a second click cannot take stock twice."""
    key = f"{entry.pk}:{hint['item'].pk}:{hint['amount']}:{hint['unit'].casefold()}:{hint['n']}"
    return uuid.uuid5(NAMESPACE, key)


def hints_for(entry, *, user, protocols_visible_to) -> dict:
    """{"uses": [...], "protocol_changes": [...]} for one entry, read by its author or a reader."""
    lab = entry.lab_id
    items = list(InventoryItem.objects.for_lab(lab))
    found = mentions(entry.body, items)
    uses = []
    for h in found:
        rid = request_id(entry, h)
        item = h["item"]
        deducted = convert(h["amount"], h["unit"], item.unit)
        row = {
            "request_id": str(rid),
            "item": str(item.pk),
            "item_name": item.name,
            "item_unit": item.unit,
            "stock": str(item.quantity),
            "amount": str(h["amount"]),
            "unit": h["unit"],
            "snippet": h["snippet"],
            "status": "new",
        }
        done = InventoryUsage.objects.for_lab(lab).filter(request_id=rid).first()
        if done is not None:
            row["status"] = "reversed" if done.reversed_at else "logged"
        else:
            near = (
                InventoryUsage.objects.for_lab(lab)
                .filter(
                    item=item,
                    used_by=user,
                    reversed_at__isnull=True,
                    deducted=deducted,
                    created_at__date__gte=entry.entry_date - timedelta(days=1),
                    created_at__date__lte=entry.entry_date + timedelta(days=1),
                )
                .exclude(note__startswith="From notebook")
                .first()
            )
            if near is not None:
                row["status"] = "possible_duplicate"
                row["duplicate_of"] = near.created_at.isoformat()
            elif deducted is not None and deducted > item.quantity:
                row["status"] = "not_enough"
        uses.append(row)

    changes = []
    text = entry.body.casefold()
    for protocol in protocols_visible_to:
        if protocol.name.casefold() not in text:
            continue
        lines = (
            ProtocolReagent.objects.for_lab(lab).filter(protocol=protocol).select_related("item")
        )
        for line in lines:
            mine = [h for h in found if h["item"].pk == line.item_id]
            for h in mine:
                a = convert(h["amount"], h["unit"], line.item.unit)
                b = convert(line.amount, line.unit, line.item.unit)
                if a is not None and b is not None and a != b:
                    changes.append(
                        {
                            "protocol": protocol.name,
                            "item_name": line.item.name,
                            "protocol_amount": f"{line.amount.normalize():f} {line.unit}".strip(),
                            "noted_amount": f"{h['amount'].normalize():f} {h['unit']}".strip(),
                        }
                    )
    return {"uses": uses, "protocol_changes": changes}


def similar_protocols(protocols) -> dict:
    """protocol id -> names of other protocols in the same list that look like it: the same
    name, or mostly the same reagents. Lets a lab spot duplicates before they pile up."""
    sets = {p.pk: {r.item_id for r in p.reagents.all()} for p in protocols}
    out = {p.pk: [] for p in protocols}
    for a in protocols:
        for b in protocols:
            if a.pk == b.pk:
                continue
            same_name = a.name.strip().casefold() == b.name.strip().casefold()
            sa, sb = sets[a.pk], sets[b.pk]
            overlap = len(sa & sb) / len(sa | sb) if sa and sb else 0
            if same_name or (len(sa & sb) >= 2 and overlap >= 0.7):
                out[a.pk].append(b.name)
    return out


def protocols_of(project_ids, lab_id):
    return Protocol.objects.for_lab(lab_id).filter(project_id__in=project_ids)
