from django.db import migrations
from django.utils.crypto import salted_hmac


def clear_revoked(apps, schema_editor):
    """Accounts revoked before Google verification item 10 still hold the Google email, scopes
    and account id. Clear them as a revoke now does (`integrations.services._retire`), and delete
    their Google Calendar settings. Nothing in Google is touched."""
    Account = apps.get_model("integrations", "ConnectedAccount")
    Sync = apps.get_model("labs", "GoogleCalendarSync")
    rows = Account.objects.filter(status="revoked").exclude(
        external_account_id__startswith="revoked:"
    )
    for row in rows.exclude(external_account_id__startswith="deleted:"):
        digest = salted_hmac(
            "integrations.retired-account", row.external_account_id, algorithm="sha256"
        )
        row.external_account_id = f"revoked:{digest.hexdigest()}"
        row.external_email = ""
        row.granted_scopes = []
        row.save(update_fields=["external_account_id", "external_email", "granted_scopes"])
    Sync.objects.filter(account__status="revoked").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0004_webhook"),
        ("labs", "0024_calendar_push_off_by_default"),
    ]

    operations = [migrations.RunPython(clear_revoked, migrations.RunPython.noop)]
