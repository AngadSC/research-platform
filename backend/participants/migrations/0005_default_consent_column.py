"""Studies of people that have no data columns yet get the default Consent form column, so their
contributors can record consent (new projects get it in projects.services.create_project).
Projects whose lead already set up columns are left as they are."""

from django.db import migrations


def add_consent_column(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    Component = apps.get_model("participants", "Component")
    bare = Project.objects.filter(
        deleted_at__isnull=True, study_types__contains=["human"]
    ).exclude(id__in=Component.objects.values("project_id"))
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


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0004_participantcomponent_decision_inclusionrule_and_more"),
        ("projects", "0014_project_study_types"),
    ]

    operations = [migrations.RunPython(add_consent_column, migrations.RunPython.noop)]
