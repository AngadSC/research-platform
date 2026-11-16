from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("labs", "0013_google_chat_per_project")]

    operations = [
        migrations.AddField(
            model_name="labchatmessage",
            name="external_avatar",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
