"""What an integration provider is (ARCHITECTURE section 9). Each provider is one module in this
package exporting `PROVIDER`; `integrations.registry.ENABLED` lists the enabled ones. How to add
one, and the security checklist: README.md next to this file.

Everything the generic UI shows comes from these fields (the providers endpoint), so no provider
needs UI code of its own. A provider reads metadata only, never file contents (D64, D84).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

from django.conf import settings


class AuthType(StrEnum):
    OAUTH2 = "oauth2"  # the OAuth2 + PKCE flow (D65)
    API_KEY = "api_key"  # the person pastes a key (and an instance URL when needed), D81
    LINK_ONLY = "link_only"  # no account: a pasted URL plus the person's own title, D83
    PUBLIC = "public"  # no account: metadata is read without credentials, D83


class Category(StrEnum):
    """How the UI groups providers."""

    STORAGE = "storage"  # files: Drive, OneDrive, Dropbox, Box
    CODE = "code"  # GitHub, GitLab
    WRITING = "writing"  # Overleaf
    DATA_CAPTURE = "data_capture"  # REDCap, Qualtrics
    PROTOCOLS = "protocols"  # protocols.io
    REFERENCES = "references"  # Zotero
    REPOSITORY = "repository"  # Zenodo, Figshare, OSF
    TASKS = "tasks"  # Todoist, Trello, monday.com: importing tasks only (D240)
    MEETINGS = "meetings"  # Google Calendar (with Meet), Zoom: they write, see WRITERS (D253)


# What a link can hang off. "project" is the project itself (the Files tab).
# D253: the only providers that may write, and what each may write. Everything else reads
# metadata only (D84); the registry test holds every provider to this list.
WRITERS = {
    "google_calendar": frozenset({"calendar_events", "meet_links"}),
    "zoom": frozenset({"zoom_meetings"}),
}

TARGETS = ("project", "document", "dataset", "analysis", "result", "manuscript", "decision")
LINK_METHODS = ("picker", "search", "paste_url")


@dataclass(frozen=True)
class ConnectField:
    """One field of an API-key connect form. Values are write-only: never echoed back (D81)."""

    name: str  # api_key | secret | instance_url
    label: str
    help_text: str = ""
    required: bool = True

    @property
    def secret(self) -> bool:
        return self.name != "instance_url"


CONNECT_FIELDS = ("api_key", "secret", "instance_url")


def _bearer(kwargs: dict, key: str, secret: str) -> dict:
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "Authorization": f"Bearer {key}"}}


@dataclass(frozen=True)
class Provider:
    name: str  # registry key, stored on ConnectedAccount.provider / ExternalLink.provider
    label: str
    auth_type: AuthType
    category: Category = Category.STORAGE
    icon: str = ""  # an icon key the UI maps to an image; never a URL
    # D84: every provider declares it reads metadata only. A registry test fails otherwise, and
    # fails when a provider module names a content-download path.
    metadata_only: bool = True
    # D253: what this provider writes. Non-empty only for the names in WRITERS, and then
    # `metadata_only` is False. Such a provider links nothing (`link_targets` is empty).
    writes: frozenset[str] = frozenset()
    # How the token endpoint wants the app's own credentials: in the form body (most) or as
    # HTTP Basic auth (Zoom).
    token_auth: str = "body"
    # D262: providers that one sign-in covers, such as Google Drive and Google Calendar. Each name
    # is another provider that shares this one's grant: connecting any of them asks for all their
    # scopes in one consent and stores one account per provider with the same tokens, and
    # disconnecting any of them disconnects them all. They must share one OAuth app (`client_from`)
    # because a refresh token only works with the app that issued it.
    bundle: tuple[str, ...] = ()
    bundle_label: str = ""  # what the person sees, for example "Google"
    client_from: str = ""  # the provider whose app registration this one uses
    link_targets: frozenset[str] = frozenset({"project"})  # subset of TARGETS
    link_methods: tuple[str, ...] = ()  # subset of LINK_METHODS

    # oauth2 (D65 to D68). `scopes` are the only scopes that may ever be requested.
    scopes: tuple[str, ...] = ()
    authorize_url: str = ""
    token_url: str = ""
    revoke_url: str = ""
    identity_url: str = ""  # GET with the token; parse_identity -> (external id, email)
    authorize_params: dict = field(default_factory=dict)  # fixed extra authorize-URL params
    parse_identity: Callable[[dict], tuple[str, str]] | None = None
    # HTTP method of the OAuth identity call (Dropbox only answers POST). D100.
    identity_method: str = "GET"
    # `(token) -> bool`: revoke at the provider when a plain POST of `token` to `revoke_url`
    # is not how it works (Dropbox: bearer header; Box: client credentials). Best effort. D100.
    revoke: Callable[[str], bool] | None = None

    # api_key (D81). The connect form; `instance_url` among them iff needs_instance_url.
    connect_fields: tuple[ConnectField, ...] = ()
    needs_instance_url: bool = False  # self-hosted (REDCap, GitLab): SSRF rules apply, D82
    instance_host_pattern: str = ""  # optional regex the instance hostname must fullmatch
    # `(account) -> (external id, email or user name)`: the cheap call that validates a key.
    # Default: GET `identity_url` (a path is joined to the instance URL) and `parse_identity`.
    identify: Callable | None = None
    # `(requests kwargs, key, secret) -> kwargs`: put the credentials on a request. Default: a
    # bearer header. Used for oauth2 (key = access token, secret = "") and api_key accounts.
    sign: Callable[[dict, str, str], dict] = _bearer

    # Hosts an account's credentials may be sent to (plus the account's instance host).
    api_hosts: frozenset[str] = frozenset()
    # Hosts an item's web link may point at (https only). Required for paste_url, except for a
    # self-hosted provider, whose links are pinned to the account's instance host.
    link_hosts: frozenset[str] = frozenset()

    # `(account | None, external_id) -> dict | None`: one item's metadata, keys title, url,
    # mime_type, modified_at (datetime), version, checksum; None when it is gone. The account is
    # None for link_only and public providers. Uses `integrations.http.send`; may raise
    # IntegrationError. Optional for link_only (then links are never checked).
    fetch_item: Callable | None = None
    # `(account | None, query, target_kind) -> [dict]`: candidates with keys id, title,
    # subtitle, modified (datetime | None), url. Required for the "search" link method (D85).
    search_items: Callable | None = None
    # What an `external_id` may look like, checked before it is stored or sent anywhere. A
    # provider that builds a URL from an id must still `urllib.parse.quote(id, safe="")` it.
    external_id_pattern: str = r"^[A-Za-z0-9_.-]{1,255}$"
    # A pasted web address -> external id: a regex with an `id` group, fullmatched (D83).
    url_pattern: str = ""
    # `(target_kind, item metadata) -> {field: value}`: values for the linked record. Each is
    # written only while that field is empty, and only if the field's validators accept it
    # (D76, D86). Kinds: dataset, analysis, result, manuscript, decision.
    apply_to_target: Callable[[str, dict], dict] | None = None

    # Task import (D240). `(account) -> [{"id", "name"}]`: the lists a person can import from.
    # `(account, source_id) -> [{"title", "notes", "due_date"}]`: the tasks in one of them.
    task_sources: Callable | None = None
    fetch_tasks: Callable | None = None
    # Off and invisible unless named in INTEGRATION_OPTIONAL_PROVIDERS (D240).
    opt_in: bool = False
    # The URL path is itself a credential (webhooks): logs get the host only (D241).
    secret_url: bool = False

    @property
    def needs_account(self) -> bool:
        return self.auth_type in (AuthType.OAUTH2, AuthType.API_KEY)

    @property
    def configured(self) -> bool:
        if self.opt_in and self.name not in settings.INTEGRATION_OPTIONAL_PROVIDERS:
            return False
        return self.auth_type != AuthType.OAUTH2 or all(self.client())

    @property
    def public_config(self) -> dict:
        """Browser-safe settings (the Picker's API key and app id); {} unless all are set."""
        conf = settings.INTEGRATION_PUBLIC.get(self.name, {})
        return dict(conf) if conf and all(conf.values()) else {}

    def client(self) -> tuple[str, str]:
        """(client_id, client_secret) from settings; empty strings when not configured."""
        conf = settings.INTEGRATION_CLIENTS.get(self.client_from or self.name, {})
        return conf.get("client_id", ""), conf.get("client_secret", "")

    def valid_external_id(self, value) -> bool:
        return isinstance(value, str) and re.fullmatch(self.external_id_pattern, value) is not None

    def link_url_ok(self, url, instance_host="") -> bool:
        """True unless links are pinned (`link_hosts`, plus the account's instance host for a
        self-hosted provider) and `url` is not https on one of those hosts."""
        hosts = self.link_hosts | ({instance_host} if instance_host else set())
        if not hosts:
            return True
        try:
            parts = urlsplit(url)
            return (
                parts.scheme == "https"
                and parts.hostname in hosts
                and not parts.port
                and parts.username is None
            )
        except (ValueError, TypeError, AttributeError):
            return False

    def parse_url(self, url, instance_host="") -> str | None:
        """The external id in a pasted address, or None: it must be on a pinned link host,
        fullmatch `url_pattern` and give a valid id."""
        if not (self.url_pattern and isinstance(url, str)):
            return None
        url = url.strip()
        if not (self.link_hosts or instance_host) or not self.link_url_ok(url, instance_host):
            return None
        match = re.fullmatch(self.url_pattern, url)
        external_id = match.group("id") if match else None
        return external_id if self.valid_external_id(external_id) else None

    def api_url(self, account, path: str) -> str:
        """`path` as an absolute URL: as-is when it already is one, else under the account's
        instance URL (`/api/v4/user` -> `https://gitlab.uni.edu/api/v4/user`)."""
        if path.startswith("https://"):
            return path
        return f"{account.instance_url.rstrip('/')}/{path.lstrip('/')}"

    def identify_account(self, account) -> tuple[str, str]:
        """Validate an API key with one cheap call: (external id, email or user name)."""
        if self.identify is not None:
            return self.identify(account)
        from integrations import http  # late: http imports this package

        resp = http.send(
            "GET", self.api_url(account, self.identity_url), provider=self, account=account
        )
        if resp.status_code != 200:
            raise ValueError("identity call failed")
        return self.parse_identity(resp.json())
