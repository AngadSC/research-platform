"""The provider registry (ARCHITECTURE section 9): code, not a database table.

`ENABLED` is the one list of providers. Adding a provider is a new module in
`integrations/providers/` plus one line here (see `integrations/providers/README.md`).

A provider's endpoints, hosts and scopes live in its module and only there. Nothing from a client
or the database can change where a credential is sent: the HTTP client attaches it only to a URL
whose host is in that provider's `api_hosts` or is the account's own instance host.
"""

from importlib import import_module

from django.core.exceptions import ImproperlyConfigured

from integrations.providers import (  # noqa: F401 - re-exported for callers and tests
    CONNECT_FIELDS,
    LINK_METHODS,
    TARGETS,
    AuthType,
    Category,
    ConnectField,
    Provider,
)

ENABLED = [
    "google_drive",
    "github",
    "gitlab",
    "overleaf",
    "onedrive",
    "dropbox",
    "box",
    "redcap",
    "qualtrics",
    "protocols_io",
    "zotero",
    "zenodo",
    "figshare",
    "osf",
    "borealis",
    "frdr",
    "todoist",
    "trello",
    "monday",
]

PROVIDERS: dict[str, Provider] = {}
for _module in ENABLED:
    _provider = import_module(f"integrations.providers.{_module}").PROVIDER
    if _provider.name in PROVIDERS:
        raise ImproperlyConfigured(f"Two integration providers are named {_provider.name}.")
    PROVIDERS[_provider.name] = _provider


def get(name: str) -> Provider:
    """The registered provider, or KeyError."""
    return PROVIDERS[name]
