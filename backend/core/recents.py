"""Recent items that point at something deleted or no longer visible are dropped, and the
saved list is cleaned up the next time the person's account is read."""

import re

from core.models import User

_ID = r"([0-9a-f-]{36})"
_PROJECT = re.compile(rf"/labs/{_ID}/projects/{_ID}(?:/|$)")
_DOCUMENT = re.compile(rf"/labs/{_ID}/projects/{_ID}/documents/{_ID}(?:/|$)")
_APPROVAL = re.compile(rf"/labs/{_ID}/ethics/{_ID}(?:/|$)")
_RECORD = re.compile(rf"/labs/{_ID}/projects/{_ID}/workflow/\w+/(\w+)/{_ID}(?:/|$)")


def _exists(user, url, labs) -> bool:
    from documents.models import Document
    from ethics.models import EthicsApproval
    from labs.models import Lab
    from projects.models import Project
    from provenance.serializers import PLURAL
    from provenance.services import SPECS

    def lab_of(lab_id):
        if lab_id not in labs:
            labs[lab_id] = Lab.objects.filter(pk=lab_id).first()
        return labs[lab_id]

    for pattern, model, extra in (
        (_RECORD, None, {}),
        (_DOCUMENT, Document, {"deleted_at__isnull": True}),
        (_APPROVAL, EthicsApproval, {"deleted_at__isnull": True}),
        (_PROJECT, Project, {"deleted_at__isnull": True}),
    ):
        m = pattern.match(url)
        if not m:
            continue
        lab = lab_of(m.group(1))
        if lab is None:
            return False
        if pattern is _RECORD:
            spec = SPECS.get(next((k for k, v in PLURAL.items() if v == m.group(3)), ""))
            return bool(
                spec and spec.model.objects.visible_to(user, lab).filter(pk=m.group(4)).exists()
            )
        pk = m.group(m.lastindex)
        return model.objects.visible_to(user, lab).filter(pk=pk, **extra).exists()
    return True  # a page that is not a project, document, record or approval


def prune_recents(user) -> None:
    saved = (user.preferences or {}).get("recents")
    if not saved:
        return
    labs: dict = {}
    kept = [r for r in saved if _exists(user, r["url"], labs)]
    if len(kept) != len(saved):
        user.preferences = {**user.preferences, "recents": kept}
        User.objects.filter(pk=user.pk).update(preferences=user.preferences)
