from django.db import migrations

from core.lab_db import LabForeignKey


class Migration(migrations.Migration):
    """D31/D141: a Google Chat link's connection is in the same lab, enforced by the database."""

    dependencies = [
        ("labs", "0011_chat_reactions"),
        ("integrations", "0004_webhook"),
    ]

    operations = [
        LabForeignKey("labs_googlechatbridge", "account_id", "integrations_connectedaccount", "CASCADE"),
    ]
