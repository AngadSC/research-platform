"""Overleaf (D105, D109): link-only. The provider contract, then the address rules: only a project
address is accepted, and read or edit share links are refused with a clear message."""

import pytest

from audit.models import AuditEvent
from integrations.models import ExternalLink
from integrations.providers import overleaf
from integrations.tests.provider_contract import ProviderContract

PROJECT_ID = "0123456789abcdef01234567"
TOKEN = "abcdefghijklmnop"  # stands in for a share token; it must never be stored or echoed


class TestOverleaf(ProviderContract):
    provider = overleaf.PROVIDER
    item_id = PROJECT_ID
    item_url = f"https://www.overleaf.com/project/{PROJECT_ID}"
    target = "manuscript"
    link_title = "Thesis draft"

    def post(self, w, url, **extra):
        return w.call(
            "POST",
            f"projects/{w.project.pk}/external-links/",
            {"provider": "overleaf", "url": url, "title": "T", **extra},
        )

    def test_accepts_only_a_project_address(self):
        parse = self.provider.parse_url
        assert parse(self.item_url) == PROJECT_ID
        for bad in (
            f"http://www.overleaf.com/project/{PROJECT_ID}",
            f"https://overleaf.com/project/{PROJECT_ID}",
            f"https://www.overleaf.com.evil.test/project/{PROJECT_ID}",
            f"https://evil.test/project/{PROJECT_ID}",
            f"https://user@www.overleaf.com/project/{PROJECT_ID}",
            f"https://www.overleaf.com:8443/project/{PROJECT_ID}",
            f"https://www.overleaf.com/project/{PROJECT_ID}?x=1",
            f"https://www.overleaf.com/project/{PROJECT_ID}#frag",
            f"https://www.overleaf.com/project/{PROJECT_ID}/download/zip",
            f"https://www.overleaf.com/project/{PROJECT_ID[:-1]}",
            f"https://www.overleaf.com/project/{PROJECT_ID}0",
            f"https://www.overleaf.com/project/{PROJECT_ID.upper()}",
            "https://www.overleaf.com/project/",
            "https://www.overleaf.com/",
            "",
            None,
        ):
            assert parse(bad) is None, bad

    @pytest.mark.parametrize(
        "path", [f"/read/{TOKEN}", f"/read/{TOKEN}/", "/1234567890abcdefghij", "/12345abc"]
    )
    def test_share_links_are_refused_with_a_clear_message(self, w, path):
        resp = self.post(w, f"https://www.overleaf.com{path}")
        assert resp.status_code == 400
        message = str(resp.json()["url"])
        assert "Share the project" in message and "instead" in message
        assert not ExternalLink.objects.for_lab(w.lab).exists()
        assert w.transport.calls == []  # nothing is ever fetched for Overleaf

    def test_a_refused_share_link_is_not_echoed_logged_or_audited(self, w):
        resp = self.post(w, f"https://www.overleaf.com/read/{TOKEN}")
        seen = [
            resp.content.decode(),
            "\n".join(f"{r.getMessage()} {r.args!r}" for r in w.caplog.records),
            str(list(AuditEvent.objects.filter(lab=w.lab).values())),
        ]
        assert not any(TOKEN in text for text in seen)

    def test_other_overleaf_addresses_get_the_generic_refusal(self, w):
        resp = self.post(w, "https://www.overleaf.com/learn/latex")
        assert resp.status_code == 400
        assert "Share the project" not in resp.content.decode()

    def test_a_link_by_id_alone_has_no_address_and_is_refused(self, w):
        resp = w.call(
            "POST",
            f"projects/{w.project.pk}/external-links/",
            {"provider": "overleaf", "external_id": PROJECT_ID, "title": "T"},
        )
        assert resp.status_code == 400 and not ExternalLink.objects.for_lab(w.lab).exists()

    def test_the_stored_link_is_the_project_address_and_the_persons_title(self, w):
        link = self.post(w, self.item_url, title="My thesis").json()
        assert link["url"] == self.item_url and link["title"] == "My thesis"
        assert link["external_id"] == PROJECT_ID and w.transport.calls == []

    def test_no_account_no_credentials_no_api(self):
        p = self.provider
        assert not (p.connect_fields or p.scopes or p.api_hosts or p.fetch_item or p.search_items)
        assert p.link_hosts == {"www.overleaf.com"} and p.metadata_only
        assert p.link_methods == ("paste_url",)
        assert p.link_targets == {"project", "manuscript", "document"}
