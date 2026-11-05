"""The registry (ARCHITECTURE section 9, D80, D84): every enabled provider is sound, reads
metadata only and defines no content-download path; one module per provider, one line each."""

import dataclasses
from pathlib import Path

import pytest

from integrations import http, registry
from integrations.tests.fake import FAKE, FAKE_KEY, FAKE_LINK, FAKE_PUBLIC
from integrations.tests.provider_contract import content_paths, provider_problems

PROVIDERS_DIR = Path(registry.__file__).parent / "providers"


@pytest.mark.parametrize("name", registry.ENABLED)
def test_every_enabled_provider_is_sound_and_reads_metadata_only(name):
    provider = registry.PROVIDERS[name]
    assert provider.metadata_only is True
    assert provider_problems(provider) == []
    assert content_paths(provider) == [], f"{name} names a content-download path (D84)"


def test_every_provider_module_is_enabled_under_its_own_name():
    modules = {p.stem for p in PROVIDERS_DIR.glob("*.py") if p.stem != "__init__"}
    assert modules == set(registry.ENABLED), "add the module to registry.ENABLED (one line)"
    assert all(registry.get(m).name == m for m in modules)  # PROVIDER.name: the module name


@pytest.mark.parametrize("provider", [FAKE, FAKE_KEY, FAKE_LINK, FAKE_PUBLIC], ids=str)
def test_the_fake_providers_are_sound(provider):
    assert provider_problems(provider) == [] and content_paths(provider) == []


# ---- the checks themselves catch what they are for


def _download_file(account, external_id):
    resp = http.send(
        "GET",
        f"https://api.fake.test/files/{external_id}?alt=media",
        provider=FAKE,
        account=account,
    )
    return {"title": "x", "url": "https://fake.test/x", "content": resp.content}


@pytest.mark.parametrize(
    "bad",
    [
        {"fetch_item": _download_file},
        {"api_hosts": frozenset({"api.fake.test", "content.dropboxapi.com"})},
        {"api_hosts": frozenset({"files.osf.io"})},
    ],
    ids=["download in code", "content host", "waterbutler host"],
)
def test_a_content_download_path_is_caught(bad):
    assert content_paths(dataclasses.replace(FAKE, **bad))


def test_docstrings_may_say_what_is_never_done():
    """Drive's docstrings say it never calls `alt=media`; only code counts."""
    assert content_paths(registry.get("google_drive")) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"metadata_only": False}, "metadata_only"),
        ({"link_targets": frozenset({"spreadsheet"})}, "link_targets"),
        ({"link_methods": ("search",), "search_items": None}, "search needs search_items"),
        ({"url_pattern": r"https://fake\.test/(?P<x>.+)"}, "url_pattern"),
        ({"api_hosts": frozenset({"https://api.fake.test"})}, "host"),
        ({"token_url": "https://evil.test/token"}, "on api_hosts"),
        ({"scopes": ()}, "scopes"),
        ({"needs_instance_url": True}, "instance URL"),
        ({"icon": "Not An Icon"}, "icon"),
    ],
)
def test_provider_problems_are_reported(change, problem):
    problems = provider_problems(dataclasses.replace(FAKE, **change))
    assert any(problem in p for p in problems), problems


def test_api_key_and_account_less_rules():
    assert provider_problems(dataclasses.replace(FAKE_KEY, connect_fields=()))
    assert provider_problems(dataclasses.replace(FAKE_PUBLIC, fetch_item=None))
    assert provider_problems(dataclasses.replace(FAKE_LINK, link_methods=()))
    assert provider_problems(dataclasses.replace(FAKE_LINK, scopes=("x",)))
