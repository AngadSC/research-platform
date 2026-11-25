"""Seed a full-size fake lab (core.seed_full): 20 people, 9 projects and every area of the app
filled in, plus fake connections for every integration. Runs once; a rerun only resets the
passwords. Same guard as seed_pilot: DEBUG on, or QA_PASSWORD set (D246)."""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import User
from core.seed_full import integrations, operations, people, research
from labs.models import Lab

DEV_PASSWORD = "seed-password-not-secret"  # noqa: S105 (dev-only, same as seed_pilot)


class Command(BaseCommand):
    help = "Seed a full-size fake lab with 20 people and 9 projects (DEBUG or QA_PASSWORD)."

    def handle(self, *args, **options):
        qa_password = os.environ.get("QA_PASSWORD", "")
        if not settings.DEBUG and not qa_password:
            raise CommandError("seed_full_lab runs with DEBUG=True, or with QA_PASSWORD set.")
        password = qa_password or DEV_PASSWORD
        if Lab.objects.filter(name=people.LAB_NAME).exists():
            self.stdout.write(f"{people.LAB_NAME} already exists; resetting passwords only.")
        else:
            with transaction.atomic():
                ctx = people.build(password)
                for part in (research, operations, integrations):
                    part.seed(ctx)
                people.archive(ctx)
            self.stdout.write(f"Seeded {people.LAB_NAME}.")
        self.reset_logins(password)
        shown = "the QA_PASSWORD setting" if qa_password else DEV_PASSWORD
        self.stdout.write(f"Logins (password: {shown}):")
        for key, (_, role, title) in people.PEOPLE.items():
            self.stdout.write(f"  {people.email(key):28} {role:10} {title}")

    def reset_logins(self, password):
        from allauth.mfa.models import Authenticator

        for user in User.objects.filter(email__in=[people.email(k) for k in people.PEOPLE]):
            user.set_password(password)
            user.save(update_fields=["password"])
            Authenticator.objects.filter(user=user).delete()
