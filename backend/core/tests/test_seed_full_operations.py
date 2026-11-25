import datetime

import pytest

from core.seed_full import operations, people
from ethics.models import EthicsApproval
from labs.models import (
    InstitutionResource,
    InventoryItem,
    InventoryOrder,
    InventoryUsage,
    Invite,
    LabEvent,
    Meeting,
    OnboardingCompletion,
    Protocol,
    Subject,
)
from training import services as training
from training.models import TrainingRecord, TrainingRequirement


@pytest.mark.django_db
def test_operations_seed():
    ctx = people.build("x")
    operations.seed(ctx)
    lab, today = ctx.lab, ctx.today

    soon = EthicsApproval.objects.for_lab(lab).filter(
        status="active", expiry_date__range=(today, today + datetime.timedelta(days=30))
    )
    assert soon.count() == 1
    statuses = set(EthicsApproval.objects.for_lab(lab).values_list("status", flat=True))
    assert {"active", "expired", "pending", "withdrawn"} <= statuses

    assert TrainingRequirement.objects.for_lab(lab).count() == 6
    cells = [
        c["status"]
        for row in training.compliance(lab, today=today)["members"]
        for c in row["cells"].values()
        if c
    ]
    assert {"done", "expiring", "expired", "missing"} <= set(cells)
    assert TrainingRecord.objects.for_lab(lab).filter(verified_at__isnull=True).exists()

    done = OnboardingCompletion.objects.for_lab(lab)
    assert (
        done.filter(user=ctx.people["liam"]).count() < done.filter(user=ctx.people["zoe"]).count()
    )

    items = InventoryItem.objects.for_lab(lab)
    assert items.count() >= 40
    assert [i for i in items if i.low_stock_at is not None and i.quantity <= i.low_stock_at]
    assert set(InventoryOrder.objects.for_lab(lab).values_list("status", flat=True)) == {
        "requested",
        "ordered",
        "received",
        "cancelled",
    }
    assert Protocol.objects.for_lab(lab).count() == 3
    assert InventoryUsage.objects.for_lab(lab).count() >= 8

    assert Meeting.objects.for_lab(lab).count() > 100
    assert LabEvent.objects.for_lab(lab).count() == 10
    assert Subject.objects.for_lab(lab).count() == 30
    assert InstitutionResource.objects.for_lab(lab).exists()
    assert Invite.objects.for_lab(lab).count() == 3
