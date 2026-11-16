from django.db import migrations

from core.lab_db import LabForeignKey


class Migration(migrations.Migration):
    """D31/D141: a subject's project is in the same lab, enforced by the database."""

    dependencies = [
        ("labs", "0017_subject"),
        ("projects", "0014_project_study_types"),
    ]

    operations = [
        LabForeignKey("labs_subject", "project_id", "projects_project", "CASCADE"),
    ]
