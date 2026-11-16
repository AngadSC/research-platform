from django.db import migrations, models


class Migration(migrations.Migration):
    """A Google message is unique within one project's chat, not across the whole lab, so the same
    conversation can be imported into more than one project."""

    dependencies = [("projects", "0012_chat_external_avatar")]

    operations = [
        migrations.RemoveConstraint(
            model_name="chatmessage", name="chatmessage_one_per_external"
        ),
        migrations.AddConstraint(
            model_name="chatmessage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id", ""), _negated=True),
                fields=("project", "external_id"),
                name="chatmessage_one_per_project_external",
            ),
        ),
    ]
