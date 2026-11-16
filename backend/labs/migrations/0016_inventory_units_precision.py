from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("labs", "0015_chat_space_shared")]

    operations = [
        migrations.AlterField(
            model_name="inventoryitem",
            name="quantity",
            field=models.DecimalField(decimal_places=6, default=1, max_digits=18),
        ),
        migrations.AlterField(
            model_name="protocolreagent",
            name="amount",
            field=models.DecimalField(decimal_places=6, max_digits=18),
        ),
        migrations.AlterField(
            model_name="inventoryusage",
            name="amount",
            field=models.DecimalField(decimal_places=6, max_digits=18),
        ),
        migrations.AlterField(
            model_name="inventoryusage",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="+",
                to="projects.project",
            ),
        ),
        migrations.AlterField(
            model_name="inventoryusage",
            name="protocol_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="inventoryusage",
            name="deducted",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="inventoryusage",
            name="note",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
