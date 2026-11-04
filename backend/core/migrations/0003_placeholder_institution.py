from django.db import migrations

NAME = "PLACEHOLDER INSTITUTION (fake, replace me)"


def create(apps, schema_editor):
    apps.get_model("core", "Institution").objects.get_or_create(name=NAME)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_institution_user_display_name_and_more")]
    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
