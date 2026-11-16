from django.db import migrations

from core.lab_db import LabForeignKey


class Migration(migrations.Migration):
    """D31/D141: a notebook entry's project is in the same lab, enforced by the database."""

    dependencies = [("labs", "0019_notebookentry")]

    operations = [
        LabForeignKey("labs_notebookentry", "project_id", "projects_project", "CASCADE"),
    ]
