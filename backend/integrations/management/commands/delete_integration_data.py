"""Carry out a deletion request for one person's data from connected services (Google
verification item 10; the privacy policy points here). Run by the operator:

    python manage.py delete_integration_data --email person@example.test [--lab <uuid>]
        [--chat-name "Exact Name"] [--dry-run]

For the person (their labbenchos account, matched by its primary or verified email addresses):
every connected account they own is revoked as on disconnect (tokens wiped and revoked at the
provider, best effort, unless another lab or user still uses the grant) and then anonymised for
good; their Google Calendar settings and push records are deleted; Google Chat links made with
their connection are removed; the Google profile picture saved on chat messages linked to their
account is cleared, as are their cached directory entries. Google connections at that address made
by another labbenchos user are never touched: they are listed as "skipped (connected by another
user)", by id, for the operator to follow up. `--chat-name` (with `--lab`) also deletes the Google
Chat messages stored under exactly that sender name (not blank, not the placeholder), whether or
not the person has an account. Lab records stay: linked items' titles and links, meetings and their
links, and the text of chat messages written by lab members. One `integration.data_deleted` audit
event per lab changed. `--dry-run` reports the counts and changes nothing.
"""

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from audit import services as audit
from audit.models import AuditAction
from core.models import User
from integrations import services
from integrations.models import AccountStatus, ConnectedAccount
from labs.google_chat import UNKNOWN_SENDER
from labs.models import ChatSource, GoogleCalendarSync, GoogleChatBridge, Lab, LabChatMessage
from projects.models import ChatMessage

LABEL = "operator:deletion_request"


class Command(BaseCommand):
    help = "Delete or anonymise one person's connected-service data (a deletion request)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="the person's email address")
        parser.add_argument("--lab", help="only this lab (its id)")
        parser.add_argument(
            "--chat-name",
            help="also delete Google Chat messages stored under exactly this sender name "
            "(someone with no account here); needs --lab",
        )
        parser.add_argument("--dry-run", action="store_true", help="report, change nothing")

    def handle(self, *args, email, lab=None, chat_name=None, dry_run=False, **options):
        email = email.strip()
        if "@" not in email:
            raise CommandError("Give a full email address.")
        if chat_name is not None and chat_name.strip().casefold() in (
            "",
            UNKNOWN_SENDER.casefold(),
        ):
            raise CommandError(
                "--chat-name must be a real sender name, not blank or the placeholder."
            )
        if chat_name and not lab:
            raise CommandError("--chat-name needs --lab: a name is only matched in one lab.")
        labs = Lab.objects.filter(pk=lab) if lab else Lab.objects.all()
        if lab and not labs.exists():
            raise CommandError("No lab with that id.")
        users = list(
            User.objects.filter(
                Q(email__iexact=email)
                | Q(
                    pk__in=EmailAddress.objects.filter(email__iexact=email, verified=True).values(
                        "user"
                    )
                )
            )
        )
        totals = {}
        with transaction.atomic():
            for each in labs:
                counts = self._lab(each, email, users, chat_name)
                if any(counts.values()):
                    totals[each.name] = counts
            if dry_run:
                transaction.set_rollback(True)  # also drops the provider revokes and cache work
        for name, counts in totals.items():
            self.stdout.write(f"{name}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if not totals:
            self.stdout.write("Nothing found for that address.")
        if dry_run:
            self.stdout.write("Dry run: nothing was changed.")

    def _lab(self, lab, email, users, chat_name) -> dict:
        live_rows = ConnectedAccount.objects.for_lab(lab).exclude(
            external_account_id__startswith="deleted:"
        )
        rows = list(live_rows.select_for_update().filter(user__in=users))
        # Google connections at this address made by someone else are theirs: listed, not touched.
        skipped = list(
            live_rows.filter(provider__startswith="google_")
            .filter(
                Q(external_email__iexact=email)
                | Q(external_account_id__iexact=email)  # Google Calendar is named by the email
                | Q(external_account_id=services.retired_id(email))
            )
            .exclude(user__in=users)
            .values_list("pk", flat=True)
        )
        if skipped:
            ids = ", ".join(str(i) for i in skipped)
            self.stdout.write(f"{lab.name}: skipped (connected by another user): {ids}")
        calendars = GoogleCalendarSync.objects.for_lab(lab).filter(account__in=rows).count()
        bridges = GoogleChatBridge.objects.for_lab(lab).filter(account__in=rows)
        counts = {"accounts": len(rows), "calendar_settings": calendars}
        counts["chat_links"] = bridges.count()
        bridges.delete()

        live = [r for r in rows if r.status != AccountStatus.REVOKED]
        google_ids = [r.external_account_id for r in live if r.provider == "google_chat"]
        pending = services._retire(live)
        for row in live:
            audit.record(
                AuditAction.INTEGRATION_REVOKED,
                actor=None,
                actor_label=LABEL,
                lab=lab,
                target=row,
                metadata={"provider": row.provider, "provider_revoked": False},
            )
        for row in rows:  # for good: not even the hash that lets a reconnect find the row
            row.external_account_id = f"deleted:{row.pk}"
            row.external_email = ""
            row.granted_scopes = []
            row.save()
        GoogleCalendarSync.objects.for_lab(lab).filter(account__in=rows).delete()

        pictures = 0
        for model in (LabChatMessage, ChatMessage):
            pictures += (
                model.objects.for_lab(lab)
                .filter(author__in=users, source=ChatSource.GOOGLE_CHAT)
                .exclude(external_avatar="")
                .update(external_avatar="")
            )
        counts["chat_pictures"] = pictures
        deleted = 0
        for model in (LabChatMessage, ChatMessage) if chat_name else ():
            theirs = model.objects.for_lab(lab).filter(
                author__isnull=True, source=ChatSource.GOOGLE_CHAT, external_author=chat_name
            )
            deleted += theirs.count()
            theirs.delete()
        counts["chat_messages_deleted"] = deleted

        if any(counts.values()):
            audit.record(
                AuditAction.INTEGRATION_DATA_DELETED,
                actor=None,
                actor_label=LABEL,
                lab=lab,
                metadata=counts,  # counts only: the address itself is not written down again
            )

        def after_commit():
            for snapshot, token in pending:
                services._revoke_at_provider(snapshot, token)
            cache.delete_many([f"gchat-person:{lab.pk}:{i}" for i in google_ids])

        transaction.on_commit(after_commit)
        return counts
