"""Auth module boundary (ARCHITECTURE section 7). Everything allauth-specific lives here;
no other module imports allauth. App code reads `request.user`."""

import logging
import time
from types import SimpleNamespace
from urllib.parse import urlparse, urlsplit

from allauth.account import app_settings as account_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.authentication import get_authentication_records
from allauth.account.internal.flows.reauthentication import (
    did_recently_reauthenticate,
    get_reauthentication_flows,
)
from allauth.account.models import EmailAddress
from allauth.account.signals import (
    email_added,
    email_removed,
    password_changed,
    password_reset,
    user_signed_up,
)
from allauth.core import context as allauth_context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.headless.account.views import VerifyEmailView as AllauthVerifyEmailView
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.headless.internal.restkit.response import ErrorResponse
from allauth.mfa.signals import authenticator_added, authenticator_removed
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.helpers import render_authentication_error
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.base import AuthError
from allauth.socialaccount.signals import social_account_added, social_account_removed
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.http import JsonResponse
from django.test import RequestFactory
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication

from audit.models import AuditAction
from audit.services import record
from core.email import send_email
from core.models import InstitutionSSO

log = logging.getLogger("core.auth")


class SessionAuthentication(authentication.SessionAuthentication):
    """Session auth that makes DRF answer 401 (not 403) to anonymous requests (D21)."""

    def authenticate_header(self, request):
        return "Session"


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.auth.SessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}


class AccountAdapter(DefaultAccountAdapter):
    def pre_authenticate(self, request, **credentials):
        """D156: password sign-in is refused for domains whose institution requires SSO."""
        super().pre_authenticate(request, **credentials)
        _refuse_password(credentials.get("email") or "")

    def authenticate(self, request, **credentials):
        """D202: a password login that proves the account belongs to someone with a verified
        address at a require-SSO institution is refused with the same message as D156 (a reauth,
        where the person is already signed in, is not a login)."""
        user = super().authenticate(request, **credentials)
        if user is not None and not request.user.is_authenticated:
            cfg = _required_sso(user, "password")
            if cfg is not None:
                raise _sso_error(cfg)
        return user

    def pre_login(self, request, user, *, signal_kwargs=None, **kwargs):
        """D202: whatever the method (password, Google, another institution's SSO), a person with
        ANY verified address at a require-SSO institution signs in through that institution only.
        Otherwise a secondary address, or a Google account, would walk around `require_sso`."""
        response = super().pre_login(request, user, signal_kwargs=signal_kwargs, **kwargs)
        if response is not None:
            return response
        social = (signal_kwargs or {}).get("sociallogin")
        method = social.account.provider if social else "password"
        cfg = _required_sso(user, method)
        if cfg is None:
            return None
        log.warning("login by %s refused: %s requires SSO", method, cfg.slug)
        if social is not None:  # a provider callback: land on the SPA's error page
            return render_authentication_error(
                request,
                social.provider,
                error=AuthError.DENIED,
                extra_context={"state": social.state},
            )
        return ErrorResponse(request, exception=_sso_error(cfg), status=400)

    def validate_unique_email(self, email):
        """Called by password signup (not by adding an address, nor by SSO signup)."""
        _refuse_password(email)
        return super().validate_unique_email(email)

    def send_mail(self, template_prefix, email, context):
        """Every allauth email goes through core.email. The verification and reset links get
        their own templates; the rest reuse allauth's text inside `account_notice`."""
        name = template_prefix.rsplit("/", 1)[-1]
        if name in ("email_confirmation", "email_confirmation_signup"):
            user = context.get("user")
            if name == "email_confirmation" and user and not _is_primary(user, email):
                # An address added to an existing account (D72): name the account it would join.
                primary = EmailAddress.objects.filter(user=user, primary=True).first()
                account = primary.email if primary else user.email
                ctx = {"url": context["activate_url"], "account": account, "email": email}
                send_email("email_verification_added", email, ctx)
            else:
                send_email("email_verification", email, {"url": context["activate_url"]})
        elif name == "password_reset_key":
            send_email("password_reset", email, {"url": context["password_reset_url"]})
        else:
            request = allauth_context.request
            if request is None:  # on-commit signals (MFA, email notices) can outlive the request
                host = urlparse(settings.FRONTEND_URL).netloc
                request = RequestFactory().get("/", HTTP_HOST=host)
            with allauth_context.request_context(request):
                ctx = {
                    "request": request,
                    "email": email,
                    "current_site": get_current_site(request),
                }
                msg = self.render_mail(template_prefix, email, {**ctx, **context})
            send_email("account_notice", email, {"subject": msg.subject, "message": msg.body})


def _is_primary(user, email: str) -> bool:
    return EmailAddress.objects.filter(user=user, email__iexact=email, primary=True).exists()


class VerifyEmailView(AllauthVerifyEmailView):
    """D72: a non-primary (added) address can only be confirmed by a request logged in as the
    account it was added to. Signup addresses are primary and still confirm logged out."""

    def post(self, request, *args, **kwargs):
        address = self.input.verification.email_address if not self.process else None
        if address and not address.primary and request.user != address.user:
            err = ValidationError(
                "Sign in to the account you added this address to, then open the link again.",
                code="sign_in_required",
            )
            return ErrorResponse(request, exception=err, status=403)
        return super().post(request, *args, **kwargs)


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user):  # D35 user shape
        return {"id": str(user.pk), "email": user.email, "display_name": user.display_name}


GOOGLE_MAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def list_apps(self, request, provider=None, client_id=None):
        """Enabled `InstitutionSSO` rows become allauth SAML apps, built in memory like
        settings-based apps (D152). `provider` may be "saml" or one app's "saml:<slug>"."""
        apps = super().list_apps(request, provider=provider, client_id=client_id)
        for cfg in InstitutionSSO.objects.filter(enabled=True).select_related("institution"):
            if provider in (None, "saml", cfg.provider_id) and client_id in (None, cfg.slug):
                apps.append(_saml_app(cfg))
        return apps

    def authenticate_by_email(self, sociallogin):
        """D62: link only when the provider says the email is verified AND it is a verified
        address of a local account. allauth's default also matches unverified local addresses
        (and then wipes the password); we never link those. No match means a new account."""
        provider = sociallogin.account.provider
        if provider.startswith("saml:"):  # D154: an IdP vouches only for its own domains
            cfg = _sso_config(provider)
            vouched = set(cfg.email_domains) if cfg else set()
        else:  # D73: Google only vouches for gmail.com and its own Workspace domain
            hd = str(sociallogin.account.extra_data.get("hd") or "").lower()
            vouched = GOOGLE_MAIL_DOMAINS | ({hd} if hd else set())
        for addr in sociallogin.email_addresses:
            if not addr.verified or _domain(addr.email) not in vouched:
                continue
            local = (
                EmailAddress.objects.filter(email__iexact=addr.email, verified=True)
                .select_related("user")
                .first()
            )
            if local:
                return local.user, local.email
        return None

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        name = f"{data.get('first_name') or ''} {data.get('last_name') or ''}".strip()
        user.display_name = name[:120]  # left blank when absent: the app asks at first sign-in
        return user

    def pre_social_login(self, request, sociallogin):
        """D154: a SAML login must assert an email in one of its institution's domains, on every
        login (new, linked or returning). Anything else is refused before any account is
        touched, and the SPA's callback page gets ?error=denied."""
        provider = sociallogin.account.provider
        if not provider.startswith("saml:"):
            return
        cfg = _sso_config(provider)
        emails = [a.email for a in sociallogin.email_addresses]
        if cfg and emails and all(_domain(e) in cfg.email_domains for e in emails):
            return
        log.warning(
            "SAML login refused for %s: email domain %s", provider, [_domain(e) for e in emails]
        )
        raise ImmediateHttpResponse(
            render_authentication_error(
                request,
                sociallogin.provider,
                error=AuthError.DENIED,
                extra_context={"state": sociallogin.state},
            )
        )


# ---- Institutional SSO (SAML 2.0, D152 to D157)


def _sso_config(provider_id: str):
    slug = provider_id.removeprefix("saml:")
    return InstitutionSSO.objects.filter(enabled=True, slug=slug).first()


def sso_for_email(email: str):
    """The enabled institution SSO that owns this address's domain (exact match), or None."""
    domain = _domain(email)
    if not domain:
        return None
    return (
        InstitutionSSO.objects.filter(enabled=True, email_domains__contains=[domain])
        .select_related("institution")
        .first()
    )


def sp_urls(slug: str) -> dict:
    """What the institution's IT registers (D155). The entity ID is fixed to FRONTEND_URL so it
    never depends on the Host a request came in on."""
    base = f"{settings.FRONTEND_URL}/accounts/saml/{slug}"
    return {
        "entity_id": f"{base}/metadata/",
        "metadata": f"{base}/metadata/",
        "acs": f"{base}/acs/",
    }


def _saml_app(cfg: InstitutionSSO) -> SocialApp:
    return SocialApp(
        provider="saml",
        provider_id=cfg.provider_id,
        client_id=cfg.slug,
        name=cfg.institution.name,
        settings={
            "idp": {
                "entity_id": cfg.idp_entity_id,
                "sso_url": cfg.idp_sso_url,
                "x509cert": cfg.idp_x509cert,
            },
            "sp": {"entity_id": sp_urls(cfg.slug)["entity_id"]},
            "attribute_mapping": cfg.attribute_mapping,
            # D154: the IdP is authoritative for its own domains, so those addresses arrive
            # verified; any other domain is refused in pre_social_login anyway.
            "verified_email": list(cfg.email_domains),
            "advanced": {
                # D155: python3-saml strict mode checks signature, audience, destination,
                # InResponseTo and NotBefore/NotOnOrAfter (300 s clock drift, fixed in
                # python3-saml). allauth pops the stashed request state, so a replayed response
                # finds no state and is refused, and IdP-initiated logins are refused.
                "strict": True,
                "want_assertion_signed": True,
                "reject_idp_initiated_sso": True,
                "reject_deprecated_algorithm": True,
                # python3-saml stamps SP metadata validUntil = now + 2 days; an IdP that keeps a
                # saved copy (Shibboleth does) would drop us after that. Ten years instead.
                "metadata_valid_until": int(time.time()) + 10 * 365 * 24 * 3600,
            },
        },
    )


def fetch_idp_metadata(cfg: InstitutionSSO) -> None:
    """D153: fill the IdP fields from `idp_metadata_url`. https only, through the integrations
    HTTP client (public addresses only, pinned connection, no cross-host redirects, deadline
    and size cap). Only ever called when a superuser saves the config, never during sign-in."""
    from onelogin.saml2.constants import OneLogin_Saml2_Constants
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

    from integrations.http import IntegrationError, budget, send

    url = cfg.idp_metadata_url
    host = urlsplit(url).hostname or ""
    if not url.startswith("https://") or not host:
        raise ValidationError({"idp_metadata_url": "Must be an https URL."})
    fetcher = SimpleNamespace(label="IdP metadata", api_hosts=frozenset({host.lower()}))
    try:
        with budget(30):
            resp = send("GET", url, provider=fetcher)
    except IntegrationError as exc:
        raise ValidationError({"idp_metadata_url": str(exc)}) from None
    if resp.status_code != 200:
        raise ValidationError({"idp_metadata_url": f"HTTP {resp.status_code}"})
    try:
        idp = OneLogin_Saml2_IdPMetadataParser.parse(
            resp.content,
            entity_id=cfg.idp_entity_id or None,
            required_sso_binding=OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
        ).get("idp", {})
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same answer
        raise ValidationError({"idp_metadata_url": f"Not SAML metadata: {exc}"}) from None
    # ponytail: one signing cert. allauth passes only `x509cert` to python3-saml, so during an
    # IdP key rollover re-save (refetch) at the switch; multi-cert needs an allauth change.
    certs = idp.get("x509certMulti", {}).get("signing") or [idp.get("x509cert", "")]
    if not idp.get("entityId") or not idp.get("singleSignOnService", {}).get("url") or not certs[0]:
        raise ValidationError({"idp_metadata_url": "No IdP with a redirect SSO URL and cert."})
    cfg.idp_entity_id = idp["entityId"]
    cfg.idp_sso_url = idp["singleSignOnService"]["url"]
    cfg.idp_x509cert = certs[0]


def _sso_error(cfg) -> ValidationError:
    name = cfg.institution.name
    msg = f"{name} addresses sign in with {name}. Go back and choose Continue with {name}."
    return ValidationError(msg, code="sso_required")


def _refuse_password(email: str) -> None:
    cfg = sso_for_email(email)
    if cfg and cfg.require_sso:
        raise _sso_error(cfg)


def _required_sso(user, provider: str):
    """D202: the require-SSO institution this user must sign in through, or None when they may
    use `provider` ("password", "google", "saml:<slug>"). A match is any verified address of the
    user, so one institution's SSO does not unlock another's addresses."""
    emails = {
        user.email,
        *EmailAddress.objects.filter(user=user, verified=True).values_list("email", flat=True),
    }
    required = [
        cfg
        for domain in sorted({_domain(e) for e in emails} - {""})
        if (cfg := sso_for_email(f"x@{domain}")) is not None and cfg.require_sso
    ]
    if not required or provider in {cfg.provider_id for cfg in required}:
        return None
    return required[0]


def login_methods_for_email(email: str) -> list[str]:
    """SSO routing (D156): ["saml:<slug>"] for a domain whose institution requires SSO,
    ["saml:<slug>", "password"] when SSO is offered but optional, else ["password"]."""
    cfg = sso_for_email(email)
    if cfg is None:
        return ["password"]
    return [cfg.provider_id] if cfg.require_sso else [cfg.provider_id, "password"]


def recent_auth_required(request):
    """D194: None when this session signed in or re-checked the password (and TOTP code, if any)
    in the last REAUTHENTICATION_TIMEOUT seconds; otherwise a 401 with allauth's own flows body,
    which the SPA's `useReauth` already turns into a password prompt and a retry (D74). A sign-in
    counts: nobody is asked twice in the same minute. Accounts with no usable password and no MFA
    can never be asked (allauth treats them as reauthenticated), exactly as in D74."""
    raw = getattr(request, "_request", request)
    if not account_settings.REAUTHENTICATION_REQUIRED or did_recently_reauthenticate(raw):
        return None
    cutoff = time.time() - account_settings.REAUTHENTICATION_TIMEOUT
    if any(r.get("at", 0) > cutoff for r in get_authentication_records(raw, raw.user)):
        return None
    # the same body allauth's headless API sends, so the SPA's `reauthFlows` reads it unchanged
    body = {"status": 401, "data": {"flows": get_reauthentication_flows(raw.user)}}
    return JsonResponse({**body, "meta": {"is_authenticated": True}}, status=401)


def has_verified_email(user, email: str) -> bool:
    """True if `email` is any verified address of the user, primary or not (D25)."""
    return EmailAddress.objects.filter(user=user, email__iexact=email, verified=True).exists()


@receiver(user_logged_in)
def _logged_in(sender, request, user, **kwargs):
    # D157: the method is the provider ("google", "saml:ualberta") or allauth's own ("password").
    steps = [r for r in get_authentication_records(request, user) if r.get("method") != "mfa"]
    meta = {"method": steps[-1].get("provider") or steps[-1]["method"]} if steps else {}
    record(AuditAction.AUTH_LOGIN, actor=user, lab=None, request=request, metadata=meta)


@receiver(user_logged_out)
def _logged_out(sender, request, user, **kwargs):
    if user is not None:
        record(AuditAction.AUTH_LOGOUT, actor=user, lab=None, request=request)


@receiver(user_login_failed)
def _login_failed(sender, credentials, request=None, **kwargs):
    # Only the identifier is kept, never the password.
    label = str(credentials.get("email") or credentials.get("username") or "")[:100]
    record(AuditAction.AUTH_LOGIN_FAILED, actor=None, lab=None, request=request, actor_label=label)


def _end_ai_access(request, user, reason):
    """D195: a changed password or removed second factor ends every AI connection and token."""
    from assistant import services

    services.revoke_all(user, reason=reason, request=request)


@receiver(password_changed)
def _password_changed(sender, request, user, **kwargs):
    record(AuditAction.AUTH_PASSWORD_CHANGED, actor=user, lab=None, request=request)
    _end_ai_access(request, user, "password_changed")


@receiver(password_reset)
def _password_reset(sender, request, user, **kwargs):
    _end_ai_access(request, user, "password_reset")


@receiver(authenticator_added)
def _mfa_added(sender, request, user, authenticator, **kwargs):
    if authenticator.type == "totp":
        record(AuditAction.AUTH_MFA_ENABLED, actor=user, lab=None, request=request)


@receiver(authenticator_removed)
def _mfa_removed(sender, request, user, authenticator, **kwargs):
    if authenticator.type == "totp":
        record(AuditAction.AUTH_MFA_DISABLED, actor=user, lab=None, request=request)
        _end_ai_access(request, user, "mfa_removed")


@receiver(email_added)
def _email_added(sender, request, user, email_address, **kwargs):
    meta = {"email": email_address.email}
    record(AuditAction.AUTH_EMAIL_ADDED, actor=user, lab=None, request=request, metadata=meta)


@receiver(email_removed)
def _email_removed(sender, request, user, email_address, **kwargs):
    meta = {"email": email_address.email}
    record(AuditAction.AUTH_EMAIL_REMOVED, actor=user, lab=None, request=request, metadata=meta)


def _social_connected(request, user, account):
    meta = {"provider": account.provider}
    record(AuditAction.AUTH_SOCIAL_CONNECTED, actor=user, lab=None, request=request, metadata=meta)


@receiver(social_account_added)
def _social_added(sender, request, sociallogin, **kwargs):
    _social_connected(request, sociallogin.user, sociallogin.account)


@receiver(user_signed_up)
def _signed_up(sender, request, user, sociallogin=None, **kwargs):
    if sociallogin is not None:  # a new account created by Google sign-in
        _social_connected(request, user, sociallogin.account)


@receiver(social_account_removed)
def _social_removed(sender, request, socialaccount, **kwargs):
    meta = {"provider": socialaccount.provider}
    user = socialaccount.user
    record(
        AuditAction.AUTH_SOCIAL_DISCONNECTED, actor=user, lab=None, request=request, metadata=meta
    )
