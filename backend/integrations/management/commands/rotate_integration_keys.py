"""Re-encrypt stored integration tokens and people's AI provider keys (D187) under the newest
INTEGRATION_ENCRYPTION_KEYS key (D63)."""

from django.core.management.base import BaseCommand

from assistant.ai.keys import rotate_all
from integrations.services import rotate_token_encryption
from integrations.webhooks import rotate_keys


class Command(BaseCommand):
    help = "Re-encrypt integration tokens with the first INTEGRATION_ENCRYPTION_KEYS key."

    def handle(self, *args, **options):
        self.stdout.write(f"Re-encrypted tokens of {rotate_token_encryption()} account(s).")
        self.stdout.write(f"Re-encrypted {rotate_all()} AI provider key(s).")
        self.stdout.write(f"Re-encrypted {rotate_keys()} webhook(s).")
