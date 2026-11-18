"""Projects that already track participants but have no data columns yet get the default Consent
form column, so their contributors can record consent (new studies of people get it in
projects.services.create_project). Projects with columns, and projects with no participants (older
projects all default to a study of people), are left as they are."""

from django.db import migrations
from django.db.models import Exists, OuterRef


def add_consent_column(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    Component = apps.get_model("participants", "Component")
    Participant = apps.get_model("participants", "Participant")
    bare = (
        Project.objects.filter(deleted_at__isnull=True, study_types__contains=["human"])
        .filter(Exists(Participant.objects.filter(project_id=OuterRef("id"))))
        .exclude(id__in=Component.objects.values("project_id"))
    )
    Component.objects.bulk_create(
        Component(
            lab_id=p.lab_id,
            project_id=p.id,
            name="Consent form",
            key="consent-form",
            category="consent",
            template_origin="default",
        )
        for p in bare.only("id", "lab_id")
    )


def remove_unused_consent_column(apps, schema_editor):
    Component = apps.get_model("participants", "Component")
    Component.objects.filter(
        key="consent-form", template_origin="default", cells__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0004_participantcomponent_decision_inclusionrule_and_more"),
        ("projects", "0014_project_study_types"),
    ]

    operations = [migrations.RunPython(add_consent_column, remove_unused_consent_column)]
