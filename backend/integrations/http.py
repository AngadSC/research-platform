"""The one outbound HTTP client for integrations (ARCHITECTURE section 9, D67, D82).

- HTTPS only, port 443, no userinfo, and only to hosts in the provider's `api_hosts` or the
  account's own instance host. A redirect to another origin is refused, never followed;
  same-origin redirects are followed for GET and HEAD only.
- SSRF (D82): every request resolves its host, refuses it unless every address is public, and
  connects to the address it checked (`PinnedAdapter`), so DNS rebinding between the check and
  the connect can't win. Proxy settings from the environment are ignored for the same reason.
  Instance URLs are also checked when they are entered (`validate_instance_url`).
- Time and size (D120): every response is streamed under a total wall-clock deadline
  (`INTEGRATION_HTTP_DEADLINE`, or the job value in `budget(per_request=...)`) and a body cap
  (`INTEGRATION_HTTP_MAX_BYTES`), and always closed. `budget()` / `interactive` bound a whole
  endpoint, retries and backoff included. The per-read timeout alone is not a limit: a server
  can drip one byte every few seconds forever.
- Idempotent methods retry on network errors and 429/5xx with exponential backoff
  (Retry-After honoured, capped), never past the deadline.
- With an `account`, its credentials are attached (`provider.sign`). OAuth: an expiring token is
  refreshed first, and a 401 triggers one refresh and one retry; a refused refresh marks the
  account. API key: a 401 means the key was revoked, and marks the account the same way.
- Logs carry method, host, path and status only: never headers, bodies or query strings.
  Exception messages follow the same rule.
"""

import contextlib
import contextvars
import functools
import ipaddress
import logging
import re
import socket
import threading
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from requests.adapters import HTTPAdapter

from integrations.providers import AuthType

log = logging.getLogger("integrations.http")

TIMEOUT = (5, 20)  # connect, read (seconds): per socket operation, not a total (D120)
MAX_ATTEMPTS = 3
BACKOFF = 0.5  # seconds, doubled per attempt
MAX_SLEEP = 8
MAX_REDIRECTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
REFRESH_MARGIN = timedelta(seconds=60)


class IntegrationError(Exception):
    """Safe to show and log: messages never contain tokens, bodies or query strings."""


class AccountUnavailable(IntegrationError):
    """The connected account is not active (expired, revoked or in error): reconnect it."""


class InstanceURLError(IntegrationError):
    """An instance URL was refused. `code` is safe to return: `invalid_instance_url` (malformed,
    not https on 443, an IP literal, unresolvable or not public: one code, so the API is no DNS
    oracle for internal names) or `instance_not_allowed` (outside the deployment allowlist)."""

    def __init__(self, code):
        super().__init__(f"The service address was refused: {code}")
        self.code = code


# ---- SSRF: which addresses may be reached (D82)


def is_public_ip(value) -> bool:
    """True only for a globally routable unicast address. Refuses private, loopback,
    link-local, multicast, reserved, unspecified, site-local and shared (CGNAT) addresses, IPv4
    and IPv6. Cloud metadata endpoints (169.254.169.254, fd00:ec2::254, 100.100.100.200,
    192.0.0.192) fall in those ranges, and `ipaddress` counts every IPv6 form that embeds an
    IPv4 address (IPv4-mapped, 6to4, Teredo, NAT64) as non-global; test_ssrf.py pins all of it."""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        return False
    # `is_global` already excludes private, loopback, link-local, unspecified and CGNAT; it
    # still counts multicast, some reserved IPv6 blocks and IPv6 site-local as global.
    site_local = ip.version == 6 and ip.is_site_local
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or site_local)


def _resolve(host) -> list[str]:
    """Every address `host` resolves to now. Tests patch this."""
    return [info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def public_address(host) -> str:
    """Resolve `host` and return the address to connect to; refuse unless every address it
    resolves to is public (a mix is refused: the client must not pick a good one by luck)."""
    try:
        addresses = _resolve(host)
    except (OSError, UnicodeError):
        raise IntegrationError("The service's address could not be resolved") from None
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise IntegrationError("Refused a service address that is not public")
    return addresses[0]


# D124: requests >= 2.32.2 routes every connection through this method; an older or changed
# requests would silently skip the pin below, so refuse to start instead.
if not callable(getattr(HTTPAdapter, "get_connection_with_tls_context", None)):
    raise ImproperlyConfigured("requests >= 2.32.2 is required: DNS pinning would be skipped")


class PinnedAdapter(HTTPAdapter):
    """Connects to the address `public_address` approved for this request, never re-resolving,
    and still verifies TLS (SNI and certificate) against the hostname."""

    def send(self, request, **kwargs):
        request.headers["Host"] = urlsplit(request.url).hostname
        return super().send(request, **kwargs)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        host_params, pool_kwargs = self.build_connection_pool_key_attributes(request, verify, cert)
        host = host_params["host"]
        return self.poolmanager.connection_from_host(
            **{**host_params, "host": public_address(host)},
            pool_kwargs={**pool_kwargs, "server_hostname": host, "assert_hostname": host},
        )


def _new_session():
    session = requests.Session()
    session.trust_env = False  # no proxy or .netrc from the environment: it would bypass the pin
    session.mount("https://", PinnedAdapter())
    session.mount("http://", PinnedAdapter())  # refused earlier anyway
    return session


_session = _new_session()  # tests swap this for a fake transport


# ---- instance URLs (self-hosted REDCap, GitLab, ...)

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_PATH = re.compile(r"(?:/[A-Za-z0-9._~-]+)*/?")


def dns_name_ok(host) -> bool:
    """A DNS name, never an IP literal in any spelling (`10.0.0.1`, `[::1]`, `0x7f.1`,
    `2130706433`): at least two labels, and the last one starts with a letter."""
    labels = (host or "").split(".")
    return (
        len(host) <= 253
        and len(labels) >= 2
        and all(_LABEL.fullmatch(label) for label in labels)
        and labels[-1][0].isalpha()
    )


def instance_host_allowed(host, provider) -> bool:
    """The deployment allowlist (`INTEGRATION_ALLOWED_INSTANCE_HOSTS`: exact hosts or
    `*.domain`), when set, and the provider's own `instance_host_pattern`."""
    allowed = [a.lower() for a in settings.INTEGRATION_ALLOWED_INSTANCE_HOSTS]
    if allowed and not any(
        host == a or (a.startswith("*.") and host.endswith(a[1:])) for a in allowed
    ):
        return False
    pattern = provider.instance_host_pattern
    return not pattern or re.fullmatch(pattern, host) is not None


def validate_instance_url(url, provider) -> str:
    """Check an instance URL when it is entered and return it normalised (`https://host/path`,
    no trailing slash). https, port 443, no userinfo, query or fragment, a DNS name (not an IP
    literal), allowed by the deployment and the provider, and resolving to public addresses
    only. Every request re-checks the address (`PinnedAdapter`)."""
    try:
        parts = urlsplit(str(url).strip())
        port = parts.port
    except (ValueError, TypeError):
        raise InstanceURLError("invalid_instance_url") from None
    host = parts.hostname or ""
    if (
        parts.scheme != "https"
        or port not in (None, 443)
        or parts.username is not None
        or "@" in parts.netloc
        or parts.query
        or parts.fragment
        or not _PATH.fullmatch(parts.path)
        or not dns_name_ok(host)
    ):
        raise InstanceURLError("invalid_instance_url")
    if not instance_host_allowed(host, provider):
        raise InstanceURLError("instance_not_allowed")
    try:
        public_address(host)
    except IntegrationError:
        raise InstanceURLError("invalid_instance_url") from None
    return f"https://{host}{parts.path.rstrip('/')}"


# ---- time and size limits (D120)


class _Limits:
    """The clock for the current call tree. `deadline` is a monotonic time no request inside
    may pass (a whole endpoint, or one background link); `per_request` is how long one request
    may take, connect to last body byte."""

    def __init__(self, deadline=None, per_request=None):
        self.deadline, self.per_request = deadline, per_request


_limits = contextvars.ContextVar("integration_limits", default=None)


def _current() -> _Limits:
    return _limits.get() or _Limits()


@contextlib.contextmanager
def budget(total=None, *, per_request=None):
    """Bound everything sent inside to `total` seconds in all (retries and backoff included).
    Nested budgets can only tighten the outer one; `per_request` overrides the per-request
    deadline (background jobs use `INTEGRATION_JOB_HTTP_DEADLINE`)."""
    outer = _current()
    deadline = outer.deadline
    if total is not None:
        mine = time.monotonic() + total
        deadline = mine if deadline is None else min(deadline, mine)
    token = _limits.set(_Limits(deadline, per_request or outer.per_request))
    try:
        yield
    finally:
        _limits.reset(token)


def interactive(func):
    """Give an endpoint's service function one overall budget (`INTEGRATION_ENDPOINT_BUDGET`)."""

    @functools.wraps(func)
    @sensitive_variables("args", "kwargs")  # connect_with_key is called with the API key
    def wrapper(*args, **kwargs):
        with budget(settings.INTEGRATION_ENDPOINT_BUDGET):
            return func(*args, **kwargs)

    wrapper.endpoint_budget = True  # the tests check every endpoint function carries one
    return wrapper


def _request_deadline() -> float:
    """Monotonic time by which the request about to be sent must be completely done."""
    limits = _current()
    mine = time.monotonic() + (limits.per_request or settings.INTEGRATION_HTTP_DEADLINE)
    return mine if limits.deadline is None else min(mine, limits.deadline)


def _remaining(deadline, provider) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise IntegrationError(f"{provider.label} did not respond in time")
    return left


def _close(resp):
    if getattr(resp, "raw", None) is not None:
        with contextlib.suppress(Exception):
            resp.close()


def _abort(resp, fired):
    """Deadline watchdog: shut the socket down so a read blocked in another thread returns now.
    A body is read in blocks, and a block that is filled one byte at a time never times out
    per read, so only an outside clock can stop it."""
    fired.set()
    # urllib3 hands the socket to the http.client response (the connection's own `sock` is
    # already None for a body that ends when the server closes), so look there first.
    for find in (lambda: resp.raw._fp.fp.raw._sock, lambda: resp.raw._connection.sock):
        with contextlib.suppress(Exception):
            find().shutdown(socket.SHUT_RDWR)
            return


def _read_body(resp, deadline, provider):
    """Read the body into `resp` under the deadline and the size cap, then close the
    connection, whatever happens. Content-Length is checked first, then the bytes received
    (decoded, so a compression bomb counts). A response that already holds its body (a test
    transport) is left alone."""
    if resp._content is not False:
        return
    cap = settings.INTEGRATION_HTTP_MAX_BYTES
    fired, timer = threading.Event(), None
    try:
        timer = threading.Timer(_remaining(deadline, provider), _abort, (resp, fired))
        timer.daemon = True
        timer.start()
        declared = resp.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > cap:
            raise IntegrationError(f"{provider.label}: the response was too large")
        chunks, size = [], 0
        for chunk in resp.iter_content(chunk_size=8192):
            size += len(chunk)
            if size > cap:
                raise IntegrationError(f"{provider.label}: the response was too large")
            chunks.append(chunk)
            _remaining(deadline, provider)
        if fired.is_set():  # the socket was cut under us: a short read is not a whole body
            raise IntegrationError(f"{provider.label} did not respond in time")
        resp._content = b"".join(chunks)
    except (requests.RequestException, OSError):  # includes a read timeout and a cut socket
        raise IntegrationError(f"{provider.label} did not respond in time") from None
    finally:
        if timer is not None:
            timer.cancel()
        _close(resp)


# ---- sending


def _origin(url):
    parts = urlsplit(url)
    return parts.scheme, (parts.hostname or "").lower(), parts.port


def _check_url(url, provider, account=None):
    """Before a socket opens: https, port 443, no userinfo, and a host this provider owns or
    this account's own instance host (still within the deployment allowlist)."""
    refused = IntegrationError(f"{provider.label}: refused a request to a host it does not own")
    try:
        scheme, host, port = _origin(url)
        userinfo = "@" in urlsplit(url).netloc
    except (ValueError, TypeError):
        raise refused from None
    instance = account.instance_host if account is not None else ""
    if scheme != "https" or port not in (None, 443) or userinfo:
        raise refused
    if host in provider.api_hosts:
        return
    if not instance or host != instance or not instance_host_allowed(host, provider):
        raise refused


def _sleep_for(attempt, resp, deadline):
    """Back off; False (no retry) when the wait would run past the deadline."""
    delay = BACKOFF * 2**attempt
    retry_after = resp.headers.get("Retry-After", "") if resp is not None else ""
    if retry_after.isdigit():
        delay = int(retry_after)
    delay = min(delay, MAX_SLEEP)
    if time.monotonic() + delay >= deadline:
        return False
    time.sleep(delay)
    return True


@sensitive_variables("kwargs")
def _follow(method, url, provider, kwargs, deadline):
    origin = _origin(url)
    for _ in range(MAX_REDIRECTS + 1):
        left = _remaining(deadline, provider)
        timeout = (min(TIMEOUT[0], left), min(TIMEOUT[1], left))
        try:
            resp = _session.request(
                method, url, timeout=timeout, allow_redirects=False, stream=True, **kwargs
            )
        except (requests.RequestException, IntegrationError):
            raise
        except Exception as exc:  # noqa: BLE001 - the HTTP stack's frames hold the headers
            log.warning("integration %s %s failed: %s", method, origin[1], type(exc).__name__)
            raise IntegrationError(f"{provider.label}: the request failed") from None
        if not resp.is_redirect or method not in ("GET", "HEAD"):
            _read_body(resp, deadline, provider)
            return resp
        location = resp.headers.get("Location", "")
        _close(resp)
        url = urljoin(url, location)
        if _origin(url) != origin:
            raise IntegrationError(f"{provider.label}: refused a redirect to another host")
    raise IntegrationError(f"{provider.label}: too many redirects")


@sensitive_variables("kwargs")
def _send_with_retries(method, url, provider, kwargs):
    host = _origin(url)[1]
    # Callers may pass a bare stand-in (client metadata, IdP metadata) without the field.
    path = "" if getattr(provider, "secret_url", False) else urlsplit(url).path
    retry = method in IDEMPOTENT
    deadline = _request_deadline()  # one deadline for all attempts and the waits between them
    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        resp = None
        try:
            resp = _follow(method, url, provider, kwargs, deadline)
        except requests.RequestException as exc:
            log.warning("integration %s %s%s failed: %s", method, host, path, type(exc).__name__)
            if not retry or last:
                # `from None`: the requests exception holds the prepared request and its headers
                raise IntegrationError(f"{provider.label} did not respond") from None
        else:
            log.info("integration %s %s%s -> %s", method, host, path, resp.status_code)
            if resp.status_code not in RETRY_STATUSES or not retry or last:
                return resp
        if not _sleep_for(attempt, resp, deadline):
            if resp is not None:
                return resp  # out of time: the caller sees the last (retryable) status
            raise IntegrationError(f"{provider.label} did not respond in time")


@sensitive_variables("headers", "signed", "kwargs", "secret")
def send(method, url, *, provider, account=None, **kwargs) -> requests.Response:
    """Send one request to `provider`. Returns the response for any status; the caller decides
    what a 403 or 404 means. Without `account` nothing secret is attached (public metadata).
    Raises IntegrationError (network, refused host, address or redirect) or AccountUnavailable."""
    from integrations import services
    from integrations.models import AccountStatus, ConnectedAccount

    method = method.upper()
    _check_url(url, provider, account)
    headers = dict(kwargs.pop("headers", None) or {})
    if account is None:
        return _send_with_retries(method, url, provider, {**kwargs, "headers": headers})

    if account.status != AccountStatus.ACTIVE:
        raise AccountUnavailable(f"{provider.label} connection needs reconnecting")
    oauth = provider.auth_type == AuthType.OAUTH2
    if (
        oauth
        and account.token_expires_at
        and account.token_expires_at <= timezone.now() + REFRESH_MARGIN
    ):
        services.refresh_access_token(account)
    for refreshed in (False, True):
        secret = "" if oauth else account.refresh_token()
        signed = provider.sign({**kwargs, "headers": dict(headers)}, account.access_token(), secret)
        resp = _send_with_retries(method, url, provider, signed)
        if resp.status_code != 401 or refreshed:
            break
        if not oauth:  # an API key can't be refreshed: the provider revoked it (D81)
            services.key_rejected(account)
            raise AccountUnavailable(f"{provider.label} refused the key")
        services.refresh_access_token(account)
    if resp.ok:
        account.last_used_at = timezone.now()
        ConnectedAccount.objects.for_lab(account.lab_id).filter(pk=account.pk).update(
            last_used_at=account.last_used_at
        )
    return resp
