import django.db.models.deletion
from django.db import migrations, models

from core.lab_db import LabForeignKey


class Migration(migrations.Migration):
    dependencies = [("ethics", "0004_pending_dates_optional")]

    operations = [
        migrations.AddField(
            model_name="ethicsapproval",
            name="renews",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="renewals",
                to="ethics.ethicsapproval",
            ),
        ),
        LabForeignKey("ethics_ethicsapproval", "renews_id", "ethics_ethicsapproval", "SET_NULL"),
    ]
