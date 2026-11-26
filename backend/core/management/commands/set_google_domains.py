"""List the email domains whose accounts are an institution's Google Workspace, so email-first
sign-in offers "Continue with your <institution> Google account" for them (when no SAML owns the
domain). With no domains, clears the list. The institution is created if it does not exist.

    manage.py set_google_domains "University of Alberta" ualberta.ca"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.models import Institution


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("institution")
        parser.add_argument("domains", nargs="*")

    def handle(self, *args, **opts):
        name = opts["institution"]
        inst = Institution.objects.filter(name__iexact=name).first() or Institution(name=name)
        inst.google_domains = opts["domains"]
        try:
            inst.full_clean()
        except ValidationError as exc:
            raise CommandError(exc.messages) from None
        inst.save()
        self.stdout.write(f"{inst.name}: Google domains {inst.google_domains}")
