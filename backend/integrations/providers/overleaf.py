"""Overleaf (ARCHITECTURE section 9, D105, D109). Overleaf has no public API, so this is link-only:
the person pastes a project address and gives it a title; nothing is ever fetched. Only
`https://www.overleaf.com/project/<24 hex>` is accepted. Read and edit share-token links open the
project for anyone who holds them, and every project viewer would see the stored address, so they
are refused with a pointer to Overleaf's own sharing."""

import re
from urllib.parse import urlsplit

from rest_framework.exceptions import ValidationError

from integrations.providers import AuthType, Category, Provider

# A share link: /read/<token> (read-only) or /<digits><letters> (edit by link).
_SHARE_PATH = re.compile(r"/(?:read/[A-Za-z0-9]+|[0-9]+[A-Za-z]+)/?")
SHARE_LINK_MESSAGE = (
    "This is an Overleaf share link, and anyone who holds it can open the project. Share the "
    "project with your collaborators in Overleaf instead (Share > add people), then paste the "
    "project address that looks like https://www.overleaf.com/project/<24 characters>."
)


class _Overleaf(Provider):
    def parse_url(self, url, instance_host=""):
        parsed = super().parse_url(url, instance_host)
        if parsed is not None or not isinstance(url, str):
            return parsed
        try:
            parts = urlsplit(url.strip())
            if (
                parts.hostname in self.link_hosts
                and parts.scheme == "https"
                and _SHARE_PATH.fullmatch(parts.path)
            ):
                raise ValidationError({"url": SHARE_LINK_MESSAGE})  # never echoes the token
        except ValueError:
            pass
        return None


PROVIDER = _Overleaf(
    name="overleaf",
    label="Overleaf",
    auth_type=AuthType.LINK_ONLY,
    category=Category.WRITING,
    icon="overleaf",
    link_targets=frozenset({"project", "manuscript", "document"}),
    link_methods=("paste_url",),
    link_hosts=frozenset({"www.overleaf.com"}),
    url_pattern=r"https://www\.overleaf\.com/project/(?P<id>[a-f0-9]{24})",
    external_id_pattern=r"^[a-f0-9]{24}$",
)
