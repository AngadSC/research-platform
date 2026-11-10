from django.db import migrations


def blank_fragment_names(apps, schema_editor):
    """Sign-up used to fill an empty name with the start of the email address (D224)."""
    User = apps.get_model("core", "User")
    for user in User.objects.exclude(display_name="").only("email", "display_name").iterator():
        if user.display_name == user.email.split("@")[0]:
            user.display_name = ""
            user.save(update_fields=["display_name"])


class Migration(migrations.Migration):
    dependencies = [("core", "0009_institutionsso")]

    operations = [migrations.RunPython(blank_fragment_names, migrations.RunPython.noop)]
