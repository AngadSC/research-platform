"""Getting-started checklist (D234). Each step is worked out from the lab's real data on every
read, so nothing can drift. Dismissing is per person and per lab, kept in `User.preferences`."""

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from core.models import User
from core.permissions import Perm, can
from core.views import LabScopedViewMixin
from ethics.models import EthicsApproval
from integrations import registry
from integrations.models import AccountStatus, ConnectedAccount
from labs.models import Invite, LabMembership
from projects.models import Project
from training.models import TrainingRequirement

DISMISSED = "getting_started_dismissed"  # a list of lab ids; only this view writes it


def checklist(user, lab) -> dict:
    """The steps say only "done" or "not done", never anything about the rows behind them."""
    projects = Project.objects.for_lab(lab).filter(deleted_at__isnull=True)
    rows = [
        (
            "members",
            Perm.MANAGE_MEMBERS,
            LabMembership.objects.for_lab(lab).count() > 1
            or Invite.objects.for_lab(lab).filter(revoked_at__isnull=True).exists(),
        ),
        ("project", Perm.CREATE_PROJECT, projects.exists()),
        (
            "ethics",
            Perm.EDIT_ETHICS,
            EthicsApproval.objects.for_lab(lab)
            .filter(deleted_at__isnull=True, projects__in=projects)
            .exists(),
        ),
        (
            "drive",
            Perm.MANAGE_INTEGRATIONS,
            ConnectedAccount.objects.for_lab(lab)
            .filter(provider="google_drive", status=AccountStatus.ACTIVE)
            .exists(),
        ),
        ("training", Perm.MANAGE_TRAINING, TrainingRequirement.objects.for_lab(lab).exists()),
    ]
    if not registry.get("google_drive").configured:  # nothing could ever tick it
        rows = [r for r in rows if r[0] != "drive"]
    return {
        "steps": [{"key": k, "done": done, "can_act": can(user, p, lab)} for k, p, done in rows],
        "dismissed": str(lab.pk) in user.preferences.get(DISMISSED, []),
    }


@transaction.atomic
def set_dismissed(user, lab, dismissed: bool) -> None:
    locked = User.objects.select_for_update().get(pk=user.pk)
    ids = [i for i in locked.preferences.get(DISMISSED, []) if i != str(lab.pk)]
    locked.preferences[DISMISSED] = [*ids, str(lab.pk)] if dismissed else ids
    locked.save(update_fields=["preferences"])
    user.preferences = locked.preferences


class StepSerializer(serializers.Serializer):
    key = serializers.CharField()
    done = serializers.BooleanField()
    can_act = serializers.BooleanField()  # may this person do the step themselves


class GettingStartedSerializer(serializers.Serializer):
    steps = StepSerializer(many=True)
    dismissed = serializers.BooleanField()


class GettingStartedInputSerializer(serializers.Serializer):
    dismissed = serializers.BooleanField()


class GettingStartedView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = GettingStartedSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}

    @extend_schema(responses=GettingStartedSerializer)
    def get(self, request, lab_id):
        return Response(checklist(request.user, request.lab))

    @extend_schema(request=GettingStartedInputSerializer, responses=GettingStartedSerializer)
    def post(self, request, lab_id):
        ser = GettingStartedInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        set_dismissed(request.user, request.lab, ser.validated_data["dismissed"])
        return Response(checklist(request.user, request.lab))
