"""Re-encrypt stored integration tokens under the newest INTEGRATION_ENCRYPTION_KEYS key (D63)."""

from django.core.management.base import BaseCommand

from integrations.services import rotate_token_encryption


class Command(BaseCommand):
    help = "Re-encrypt integration tokens with the first INTEGRATION_ENCRYPTION_KEYS key."

    def handle(self, *args, **options):
        self.stdout.write(f"Re-encrypted tokens of {rotate_token_encryption()} account(s).")
