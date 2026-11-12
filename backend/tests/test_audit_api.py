from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit import views
from audit.models import AuditAction
from audit.services import record
from labs.models import LabRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(make_lab, make_user, join):
    lab, other = make_lab("A"), make_lab("B")
    pi = make_user()
    join(pi, lab, LabRole.PI)
    return lab, other, pi


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def get(user, lab, **params):
    return client_for(user).get(f"/api/labs/{lab.pk}/audit-events/", params)


def test_shape_scope_order_and_cursor(setup, make_user, monkeypatch):
    lab, other, pi = setup
    for _ in range(3):
        record(AuditAction.LAB_UPDATED, actor=pi, lab=lab, target=lab)
    record(AuditAction.LAB_UPDATED, actor=None, lab=lab)
    record(AuditAction.LAB_UPDATED, actor=make_user(), lab=other)
    data = get(pi, lab).json()
    assert len(data["results"]) == 4 and data["next"] is None  # other lab's event is hidden
    first = data["results"][0]
    assert set(first) == {
        "id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "target_label",
        "created_at",
        "metadata",
    }
    assert first["actor"] is None  # newest first: the system event
    assert data["results"][1]["actor"]["email"] == pi.email
    monkeypatch.setattr(views.AuditCursorPagination, "page_size", 2)
    page = get(pi, lab).json()
    assert len(page["results"]) == 2 and page["next"]
    assert len(client_for(pi).get(page["next"]).json()["results"]) == 2


def test_filters_and_read_only(setup, make_user):
    lab, _, pi = setup
    e = record(AuditAction.LAB_UPDATED, actor=pi, lab=lab, target=lab)
    record(AuditAction.LAB_CREATED, actor=make_user(), lab=lab)

    def ids(**p):
        return [r["id"] for r in get(pi, lab, **p).json()["results"]]

    assert ids(action="lab.updated") == [str(e.id)]
    assert str(e.id) in ids(actor=str(pi.pk))  # also holds pi's own audit_log.viewed rows
    assert ids(target_type="labs.Lab", target_id=str(lab.pk)) == [str(e.id)]
    today = timezone.localdate()
    assert len(ids(date_from=today.isoformat(), date_to=today.isoformat())) >= 2
    assert ids(date_from=(today + timedelta(days=1)).isoformat()) == []
    assert get(pi, lab, action="bogus").status_code == 400
    url = f"/api/labs/{lab.pk}/audit-events/"
    for m in ("post", "put", "patch", "delete"):
        assert getattr(client_for(pi), m)(url).status_code in (403, 405)  # never 2xx
