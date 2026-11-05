"""Integration providers: a code-level registry, not a database table (ARCHITECTURE section 9).

A provider's endpoints and allowed scopes live here and only here. Nothing from a client or the
database can change where a token is sent: the HTTP client attaches an account's token only to a
URL whose host is in that provider's `api_hosts`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from django.conf import settings


class AuthType(StrEnum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    LINK_ONLY = "link_only"


@dataclass(frozen=True)
class Provider:
    name: str  # registry key, stored on ConnectedAccount.provider / ExternalLink.provider
    label: str
    auth_type: AuthType
    scopes: tuple[str, ...] = ()  # the only scopes that may ever be requested
    icon: str = ""
    authorize_url: str = ""
    token_url: str = ""
    revoke_url: str = ""
    identity_url: str = ""  # GET with the new token; parse_identity -> (external id, email)
    api_hosts: frozenset[str] = frozenset()  # hosts an account token may be sent to
    authorize_params: dict = field(default_factory=dict)  # fixed extra authorize-URL params
    parse_identity: Callable[[dict], tuple[str, str]] | None = None
    # Reads one item's metadata for a new ExternalLink: `(account, external_id) -> dict | None`
    # with keys title, url, mime_type, modified_at (datetime), version, checksum; None when the
    # item does not exist. Uses `integrations.http.send` with `account`; may raise IntegrationError.
    fetch_item: Callable | None = None
    # What an `external_id` may look like, checked before it is stored or sent anywhere. A
    # provider that builds a URL from an id must still `urllib.parse.quote(id, safe="")` it.
    external_id_pattern: str = r"^[A-Za-z0-9_.-]{1,255}$"

    def client(self) -> tuple[str, str]:
        """(client_id, client_secret) from settings; empty strings when not configured."""
        conf = settings.INTEGRATION_CLIENTS.get(self.name, {})
        return conf.get("client_id", ""), conf.get("client_secret", "")

    def valid_external_id(self, value) -> bool:
        return isinstance(value, str) and re.fullmatch(self.external_id_pattern, value) is not None

    @property
    def configured(self) -> bool:
        return self.auth_type != AuthType.OAUTH2 or all(self.client())


def _google_identity(data: dict) -> tuple[str, str]:
    # Drive `about` works with drive.file alone, so no openid/email scope is needed (D64).
    user = data["user"]
    return str(user["permissionId"]), str(user.get("emailAddress", ""))


GOOGLE = Provider(
    name="google",
    label="Google Drive",
    auth_type=AuthType.OAUTH2,
    scopes=("https://www.googleapis.com/auth/drive.file",),
    icon="google-drive",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    identity_url="https://www.googleapis.com/drive/v3/about?fields=user(permissionId,emailAddress)",
    api_hosts=frozenset({"www.googleapis.com", "oauth2.googleapis.com"}),
    # offline + consent: always get a refresh token; include_granted_scopes: incremental auth.
    authorize_params={
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    },
    parse_identity=_google_identity,
)

PROVIDERS: dict[str, Provider] = {p.name: p for p in (GOOGLE,)}


def get(name: str) -> Provider:
    """The registered provider, or KeyError."""
    return PROVIDERS[name]
