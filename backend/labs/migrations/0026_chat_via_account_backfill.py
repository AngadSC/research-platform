from django.db import migrations


def backfill(apps, schema_editor):
    """D376: every Google message so far came in through its chat's link (checked on the live site
    before this ran), so it is credited to that link's connection."""
    Bridge = apps.get_model("labs", "GoogleChatBridge")
    LabChat = apps.get_model("labs", "LabChatMessage")
    ProjectChat = apps.get_model("projects", "ChatMessage")
    for b in Bridge.objects.all():
        if b.project_id is None:
            rows = LabChat.objects.filter(lab_id=b.lab_id)
        else:
            rows = ProjectChat.objects.filter(lab_id=b.lab_id, project_id=b.project_id)
        rows.filter(source="google_chat", via_account__isnull=True).update(
            via_account_id=b.account_id
        )


class Migration(migrations.Migration):
    # Its own migration (own transaction): Postgres refuses the new index in 0025 once rows were
    # updated in the same transaction ("pending trigger events").
    dependencies = [("labs", "0025_chat_via_account")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
