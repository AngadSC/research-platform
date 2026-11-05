from django.db import migrations, models

from documents.text import extract_text


def backfill(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    for doc in Document._base_manager.all().iterator():
        doc.search_text = extract_text(doc.content)
        doc.save(update_fields=["search_text"])


class Migration(migrations.Migration):
    dependencies = [("documents", "0004_alter_attachment_ethics_approval")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="search_text",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
