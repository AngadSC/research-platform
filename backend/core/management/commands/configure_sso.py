"""Create or update an institution's SAML sign-in from a JSON file (D153), then print the SP
details to send to its IT. The production path: the Django admin is DEBUG-only (D41).

    {"institution": "University of Alberta", "slug": "ualberta", "enabled": true,
     "email_domains": ["ualberta.ca"], "idp_metadata_url": "https://...",
     "require_sso": false}

Any other InstitutionSSO field (idp_entity_id, idp_sso_url, idp_x509cert, attribute_mapping)
may be given too. With a metadata URL, the IdP fields are fetched on every run."""

import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.auth import sp_urls
from core.models import Institution, InstitutionSSO

FIELDS = {f.name for f in InstitutionSSO._meta.concrete_fields} - {
    "id",
    "institution",
    "updated_at",
}


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON file")

    @transaction.atomic
    def handle(self, *args, **opts):
        with open(opts["path"], encoding="utf-8") as f:
            data = json.load(f)
        unknown = set(data) - FIELDS - {"institution"}
        if unknown or not data.get("institution") or not data.get("slug"):
            raise CommandError(f"Need institution and slug; unknown keys: {sorted(unknown)}")
        name = data.pop("institution")
        inst = Institution.objects.filter(name__iexact=name).first()
        inst = inst or Institution.objects.create(name=name)
        cfg = InstitutionSSO.objects.filter(institution=inst).first() or InstitutionSSO(
            institution=inst
        )
        for key, value in data.items():
            setattr(cfg, key, value)
        try:
            cfg.full_clean()
        except ValidationError as exc:
            raise CommandError(exc.messages) from None
        cfg.save()
        state = "enabled" if cfg.enabled else "disabled"
        self.stdout.write(f"Saved {cfg} ({state}), domains {cfg.email_domains}.")
        for key, url in sp_urls(cfg.slug).items():
            self.stdout.write(f"  SP {key}: {url}")
