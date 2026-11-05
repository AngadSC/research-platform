"""The one outbound HTTP client for integrations (ARCHITECTURE section 9, D67).

- HTTPS only (default port), and only to hosts in the provider's `api_hosts`; a redirect to
  another host is refused, never followed. Same-host redirects are followed for GET and HEAD only.
- Connect and read timeouts; idempotent methods retry on network errors and 429/5xx with
  exponential backoff (Retry-After honoured, capped).
- With an `account`, its bearer token is attached; an expiring token is refreshed first, and a
  401 triggers one refresh and one retry. A refresh the provider refuses marks the account and
  is audited (`services.refresh_access_token`).
- Logs carry method, host, path and status only: never headers, bodies or query strings.
  Exception messages follow the same rule.
"""

import logging
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

import requests
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

log = logging.getLogger("integrations.http")

TIMEOUT = (5, 20)  # connect, read (seconds)
MAX_ATTEMPTS = 3
BACKOFF = 0.5  # seconds, doubled per attempt
MAX_SLEEP = 8
MAX_REDIRECTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
REFRESH_MARGIN = timedelta(seconds=60)

_session = requests.Session()  # tests swap this for a fake transport


class IntegrationError(Exception):
    """Safe to show and log: messages never contain tokens, bodies or query strings."""


class AccountUnavailable(IntegrationError):
    """The connected account is not active (expired, revoked or in error): reconnect it."""


def _origin(url):
    parts = urlsplit(url)
    return parts.scheme, (parts.hostname or "").lower(), parts.port


def _check_url(url, provider):
    scheme, host, port = _origin(url)
    if scheme != "https" or host not in provider.api_hosts or port not in (None, 443):
        raise IntegrationError(f"{provider.label}: refused a request to a host it does not own")


def _sleep_for(attempt, resp):
    delay = BACKOFF * 2**attempt
    retry_after = resp.headers.get("Retry-After", "") if resp is not None else ""
    if retry_after.isdigit():
        delay = int(retry_after)
    time.sleep(min(delay, MAX_SLEEP))


def _follow(method, url, provider, kwargs):
    origin = _origin(url)
    for _ in range(MAX_REDIRECTS + 1):
        resp = _session.request(method, url, timeout=TIMEOUT, allow_redirects=False, **kwargs)
        if not resp.is_redirect or method not in ("GET", "HEAD"):
            return resp
        url = urljoin(url, resp.headers["Location"])
        if _origin(url) != origin:
            raise IntegrationError(f"{provider.label}: refused a redirect to another host")
    raise IntegrationError(f"{provider.label}: too many redirects")


@sensitive_variables("kwargs")
def _send_with_retries(method, url, provider, kwargs):
    host = _origin(url)[1]
    retry = method in IDEMPOTENT
    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        resp = None
        try:
            resp = _follow(method, url, provider, kwargs)
        except requests.RequestException as exc:
            path = urlsplit(url).path
            log.warning("integration %s %s%s failed: %s", method, host, path, type(exc).__name__)
            if not retry or last:
                # `from None`: the requests exception holds the prepared request and its headers
                raise IntegrationError(f"{provider.label} did not respond") from None
        else:
            path = urlsplit(url).path
            log.info("integration %s %s%s -> %s", method, host, path, resp.status_code)
            if resp.status_code not in RETRY_STATUSES or not retry or last:
                return resp
        _sleep_for(attempt, resp)


@sensitive_variables("headers", "auth", "kwargs")
def send(method, url, *, provider, account=None, **kwargs) -> requests.Response:
    """Send one request to `provider`. Returns the response for any status; the caller decides
    what a 403 or 404 means. Raises IntegrationError (network, refused host or redirect) or
    AccountUnavailable."""
    from integrations import services
    from integrations.models import AccountStatus, ConnectedAccount

    method = method.upper()
    _check_url(url, provider)
    headers = dict(kwargs.pop("headers", None) or {})
    if account is None:
        return _send_with_retries(method, url, provider, {**kwargs, "headers": headers})

    if account.status != AccountStatus.ACTIVE:
        raise AccountUnavailable(f"{provider.label} connection needs reconnecting")
    if account.token_expires_at and account.token_expires_at <= timezone.now() + REFRESH_MARGIN:
        services.refresh_access_token(account)
    for refreshed in (False, True):
        auth = {**headers, "Authorization": f"Bearer {account.access_token()}"}
        resp = _send_with_retries(method, url, provider, {**kwargs, "headers": auth})
        if resp.status_code != 401 or refreshed:
            break
        services.refresh_access_token(account)
    if resp.ok:
        account.last_used_at = timezone.now()
        ConnectedAccount.objects.for_lab(account.lab_id).filter(pk=account.pk).update(
            last_used_at=account.last_used_at
        )
    return resp
