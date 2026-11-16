from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0011_chat_google_source")]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="external_avatar",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
