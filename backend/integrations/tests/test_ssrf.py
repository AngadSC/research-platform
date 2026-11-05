"""SSRF defences for instance URLs and every outbound request (ARCHITECTURE section 9, D82).

Each defence has a test that isolates it (everything else would pass), so removing that one
defence fails a test: https only, port 443, no userinfo, no IP literal, resolution at connect
time, resolution on every request, the address checks, the pinned connection (DNS rebinding),
the per-account host allowlist, same-host redirects, and the deployment allowlist."""

import dataclasses

import pytest
import requests
import urllib3.util.connection
from django.test import Client

from integrations import http, registry, services
from integrations.http import InstanceURLError, IntegrationError
from integrations.models import AccountStatus, ConnectedAccount
from integrations.tests.conftest import make_request
from integrations.tests.fake import FAKE, FAKE_KEY, response

PUBLIC = "93.184.216.34"
PUBLIC6 = "2606:4700:4700::1111"
INSTANCE = "https://git.fake.test"

REFUSED = [
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.1",
    "127.0.0.1",
    "127.1.2.3",
    "0.0.0.0",
    "169.254.169.254",  # AWS, GCP, Azure metadata
    "169.254.170.2",  # ECS task metadata
    "100.100.100.200",  # Alibaba metadata (CGNAT range)
    "100.64.0.1",
    "192.0.0.192",  # Oracle metadata
    "224.0.0.1",
    "239.255.255.250",
    "240.0.0.1",
    "255.255.255.255",
    "198.18.0.1",
    "192.0.2.1",
    "::1",
    "::",
    "fe80::1",
    "fe80::1%eth0",
    "fc00::1",
    "fd00:ec2::254",  # AWS IPv6 metadata
    "fec0::1",
    "ff02::1",
    "200::1",
    "2001:db8::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
    "::ffff:169.254.169.254",
    "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
    "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    "2002:7f00:1::",  # 6to4 of 127.0.0.1
    "2002:a00:1::",  # 6to4 of 10.0.0.1
    "not an address",
]


@pytest.mark.parametrize("address", REFUSED)
def test_non_public_addresses_are_refused(address):
    assert not http.is_public_ip(address)


@pytest.mark.parametrize("address", [PUBLIC, "8.8.8.8", "1.1.1.1", PUBLIC6])
def test_public_addresses_are_allowed(address):
    assert http.is_public_ip(address)


@pytest.mark.parametrize(
    "host",
    ["10.0.0.1", "127.1", "0x7f.0.0.1", "2130706433", "::1", "93.184.216.34", "localhost", ""],
)
def test_ip_literals_and_bare_names_are_not_dns_names(host):
    assert not http.dns_name_ok(host)


@pytest.mark.parametrize("host", ["git.uni.edu", "redcap.med.example.org", "xn--bcher-kva.example"])
def test_dns_names(host):
    assert http.dns_name_ok(host)


# ---- instance URLs, checked when entered


@pytest.fixture
def resolves(monkeypatch):
    """Point every name at the given addresses (default: one public address)."""
    answer = {"addresses": [PUBLIC], "calls": []}

    def resolve(host):
        answer["calls"].append(host)
        value = answer["addresses"]
        if isinstance(value, Exception):
            raise value
        return value(host) if callable(value) else list(value)

    monkeypatch.setattr(http, "_resolve", resolve)
    return answer


def check(url, provider=FAKE_KEY):
    return http.validate_instance_url(url, provider)


def test_a_good_instance_url_is_normalised(resolves):
    assert check("https://Git.Uni.Edu/redcap/api/") == "https://git.uni.edu/redcap/api"
    assert check("https://git.uni.edu:443") == "https://git.uni.edu"


@pytest.mark.parametrize(
    "url",
    [
        "http://git.uni.edu",  # https only
        "ftp://git.uni.edu",
        "//git.uni.edu",
    ],
)
def test_instance_url_must_be_https(resolves, url):
    with pytest.raises(InstanceURLError):
        check(url)


@pytest.mark.parametrize("url", ["https://git.uni.edu:8443", "https://git.uni.edu:80"])
def test_instance_url_must_use_port_443(resolves, url):
    with pytest.raises(InstanceURLError):
        check(url)


@pytest.mark.parametrize(
    "url", ["https://user:pw@git.uni.edu", "https://user@git.uni.edu", "https://@git.uni.edu"]
)
def test_instance_url_has_no_userinfo(resolves, url):
    with pytest.raises(InstanceURLError):
        check(url)


@pytest.mark.parametrize(
    "url",
    [
        f"https://{PUBLIC}",  # public, so only the IP-literal rule refuses it
        f"https://[{PUBLIC6}]",
        "https://1572395042",  # 93.184.216.34 as one number
        "https://0x5d.0xb8.0xd8.0x22",
    ],
)
def test_instance_url_is_not_an_ip_literal(resolves, url):
    resolves["addresses"] = lambda host: [PUBLIC]
    with pytest.raises(InstanceURLError):
        check(url)


@pytest.mark.parametrize(
    "url", ["https://git.uni.edu/?a=1", "https://git.uni.edu/#x", "https://git.uni.edu/a b"]
)
def test_instance_url_has_no_query_fragment_or_odd_path(resolves, url):
    with pytest.raises(InstanceURLError):
        check(url)


@pytest.mark.parametrize(
    "addresses",
    [["10.0.0.5"], ["169.254.169.254"], [PUBLIC, "127.0.0.1"], ["::ffff:10.0.0.1"], []],
)
def test_instance_url_must_resolve_to_public_addresses_when_entered(resolves, addresses):
    resolves["addresses"] = addresses
    with pytest.raises(InstanceURLError) as exc:
        check("https://git.uni.edu")
    assert exc.value.code == "invalid_instance_url"  # one code: no DNS oracle
    assert resolves["calls"] == ["git.uni.edu"]


def test_unresolvable_instance_url_is_refused(resolves):
    resolves["addresses"] = OSError("no such host")
    with pytest.raises(InstanceURLError):
        check("https://git.uni.edu")


def test_deployment_allowlist(resolves, settings):
    settings.INTEGRATION_ALLOWED_INSTANCE_HOSTS = ["git.uni.edu", "*.lab.example.org"]
    assert check("https://git.uni.edu")
    assert check("https://redcap.lab.example.org")
    for url in (
        "https://gitlab.com",
        "https://git.uni.edu.evil.test",
        "https://lab.example.org",
        "https://evillab.example.org",
    ):
        with pytest.raises(InstanceURLError) as exc:
            check(url)
        assert exc.value.code == "instance_not_allowed"


def test_provider_instance_host_pattern(resolves):
    qualtrics = dataclasses.replace(FAKE_KEY, instance_host_pattern=r"[a-z0-9]+\.qualtrics\.com")
    assert check("https://ca1.qualtrics.com", qualtrics)
    with pytest.raises(InstanceURLError):
        check("https://qualtrics.com.evil.test", qualtrics)


def test_connect_with_a_private_instance_stores_and_sends_nothing(
    lab_users, transport, resolves, monkeypatch
):
    monkeypatch.setitem(registry.PROVIDERS, FAKE_KEY.name, FAKE_KEY)
    lab, users = lab_users
    resolves["addresses"] = ["10.1.2.3"]
    c = Client()
    c.force_login(users["member"])
    resp = c.post(
        f"/api/labs/{lab.pk}/integrations/fake_key/connect/",
        {"api_key": "k", "instance_url": "https://git.uni.edu"},
        "application/json",
    )
    assert resp.status_code == 400 and resp.json()["code"] == "invalid_instance_url"
    assert transport.calls == [] and not ConnectedAccount.objects.for_lab(lab).exists()


# ---- every request: resolved, checked and pinned


class Connections:
    """Replaces urllib3's socket connect: records the address and refuses to connect, so no
    test ever touches the network."""

    def __init__(self):
        self.addresses = []

    def __call__(self, address, *args, **kwargs):
        self.addresses.append(address)
        raise OSError("test: no network")


@pytest.fixture
def real_client(monkeypatch, resolves):
    """The real session (not the fake transport) with DNS and sockets replaced."""
    monkeypatch.setattr(http, "_session", http._new_session())
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    connections = Connections()
    monkeypatch.setattr(urllib3.util.connection, "create_connection", connections)
    return connections


def test_each_request_resolves_and_refuses_a_private_address(real_client, resolves):
    resolves["addresses"] = ["127.0.0.1"]
    with pytest.raises(IntegrationError, match="not public"):
        http.send("GET", "https://api.fake.test/files/1", provider=FAKE)
    assert real_client.addresses == []  # refused before any socket
    assert resolves["calls"] == ["api.fake.test"]


def test_dns_rebinding_cannot_win(real_client, resolves):
    """Public when checked, private a moment later: the connection still goes to the address
    that was checked, and the name is never resolved again for that request."""
    answers = iter([[PUBLIC], ["127.0.0.1"], ["127.0.0.1"]])
    resolves["addresses"] = lambda host: next(answers)
    with pytest.raises(IntegrationError, match="did not respond"):
        http.send("POST", "https://api.fake.test/token", provider=FAKE)  # POST: one attempt
    assert real_client.addresses == [(PUBLIC, 443)]
    assert resolves["calls"] == ["api.fake.test"]


def test_a_retry_resolves_again_and_is_refused_after_rebinding(real_client, resolves):
    answers = iter([[PUBLIC], ["10.0.0.7"]])
    resolves["addresses"] = lambda host: next(answers)
    with pytest.raises(IntegrationError, match="not public"):
        http.send("GET", "https://api.fake.test/files/1", provider=FAKE)
    assert real_client.addresses == [(PUBLIC, 443)]  # the second attempt never connected


def test_ipv6_answers_are_pinned_too(real_client, resolves):
    resolves["addresses"] = [PUBLIC6]
    with pytest.raises(IntegrationError):
        http.send("POST", "https://api.fake.test/token", provider=FAKE)
    assert [a[0].strip("[]") for a in real_client.addresses] == [PUBLIC6]


def test_tls_is_verified_against_the_hostname_not_the_address(resolves):
    request = requests.Request("GET", "https://api.fake.test/x").prepare()
    pool = http.PinnedAdapter().get_connection_with_tls_context(request, True)
    assert pool.host == PUBLIC
    assert pool.conn_kw["server_hostname"] == "api.fake.test"  # SNI
    assert pool.assert_hostname == "api.fake.test"  # certificate check


def test_host_header_names_the_host(monkeypatch, resolves):
    seen = {}

    def fake_send(self, request, **kwargs):
        seen["host"] = request.headers["Host"]
        return response(200, {})

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)
    http.PinnedAdapter().send(requests.Request("GET", "https://api.fake.test/x").prepare())
    assert seen["host"] == "api.fake.test"


def test_environment_proxies_and_netrc_are_ignored():
    assert http._session.trust_env is False


# ---- the per-account host allowlist


@pytest.fixture
def key_account(lab_users, transport, monkeypatch):
    monkeypatch.setitem(registry.PROVIDERS, FAKE_KEY.name, FAKE_KEY)
    lab, users = lab_users
    transport.on("GET", f"{INSTANCE}/api/me", response(200, {"id": 7, "username": "ada"}))
    return services.connect_with_key(
        make_request(users["member"]),
        lab,
        "fake_key",
        api_key="the-key",
        instance_url=INSTANCE,
    )


def test_credentials_go_only_to_the_accounts_own_instance(key_account, transport):
    assert key_account.status == AccountStatus.ACTIVE
    assert key_account.external_account_id == "git.fake.test:7"
    for url in (
        "https://other.fake.test/api/items/1",  # another server
        "https://api.fake.test/files/1",  # another provider's host
        "https://x@git.fake.test/api/items/1",  # userinfo
        "https://git.fake.test:8443/api/items/1",  # another port
        "http://git.fake.test/api/items/1",
    ):
        before = len(transport.calls)
        with pytest.raises(IntegrationError, match="refused a request"):
            http.send("GET", url, provider=FAKE_KEY, account=key_account)
        assert len(transport.calls) == before
    transport.on("GET", f"{INSTANCE}/api/items/1", response(200, {}))
    assert http.send("GET", f"{INSTANCE}/api/items/1", provider=FAKE_KEY, account=key_account).ok


def test_without_the_account_the_instance_host_is_not_allowed(key_account):
    with pytest.raises(IntegrationError, match="refused a request"):
        http.send("GET", f"{INSTANCE}/api/items/1", provider=FAKE_KEY)


def test_redirects_never_leave_the_instance(key_account, transport):
    transport.on(
        "GET",
        f"{INSTANCE}/api/items/1",
        response(302, headers={"Location": "https://169.254.169.254/latest/meta-data"}),
    )
    with pytest.raises(IntegrationError, match="redirect to another host"):
        http.send("GET", f"{INSTANCE}/api/items/1", provider=FAKE_KEY, account=key_account)
    assert not any("169.254" in url for _, url, _ in transport.calls)
    transport.on("GET", f"{INSTANCE}/api/items/1", response(302, headers={"Location": "/api/x"}))
    transport.on("GET", f"{INSTANCE}/api/x", response(200, {"ok": True}))
    resp = http.send("GET", f"{INSTANCE}/api/items/1", provider=FAKE_KEY, account=key_account)
    assert resp.json() == {"ok": True}


def test_a_tightened_deployment_allowlist_applies_to_existing_accounts(
    key_account, transport, settings
):
    settings.INTEGRATION_ALLOWED_INSTANCE_HOSTS = ["gitlab.uni.edu"]
    with pytest.raises(IntegrationError, match="refused a request"):
        http.send("GET", f"{INSTANCE}/api/items/1", provider=FAKE_KEY, account=key_account)


# ---- the pin depends on a requests hook (D124)


def test_requests_still_calls_the_hook_the_pin_overrides():
    """`PinnedAdapter` pins the address by overriding `get_connection_with_tls_context`, which
    requests >= 2.32.2 calls from `send`. If a requests upgrade renamed or stopped calling it,
    the override would be dead code and DNS pinning would be skipped without any error."""
    import inspect

    from requests.adapters import HTTPAdapter

    assert callable(getattr(HTTPAdapter, "get_connection_with_tls_context", None))
    assert "get_connection_with_tls_context" in inspect.getsource(HTTPAdapter.send)
    assert http.PinnedAdapter.get_connection_with_tls_context is not (
        HTTPAdapter.get_connection_with_tls_context
    )


def test_requests_is_pinned_at_or_above_the_hook_version():
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "requirements.txt").read_text()
    match = re.search(r"^requests(==|>=)(\d+)\.(\d+)\.(\d+)", text, re.M)
    assert match, "requests must be pinned in requirements.txt"
    assert tuple(map(int, match.groups()[1:])) >= (2, 32, 2)
    assert tuple(map(int, requests.__version__.split(".")[:3])) >= (2, 32, 2)
