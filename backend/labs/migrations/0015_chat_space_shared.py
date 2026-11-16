from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("labs", "0014_chat_external_avatar")]

    operations = [
        # Several chats may now link to the same Google Chat conversation.
        migrations.RemoveConstraint(model_name="googlechatbridge", name="gchatbridge_space_once"),
    ]
