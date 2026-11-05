"""Auth module boundary (ARCHITECTURE section 7). Everything allauth-specific lives here;
no other module imports allauth. App code reads `request.user`."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.signals import email_added, email_removed, password_changed, user_signed_up
from allauth.core import context as allauth_context
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.mfa.signals import authenticator_added, authenticator_removed
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.signals import social_account_added, social_account_removed
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.sites.shortcuts import get_current_site
from django.dispatch import receiver
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication

from audit.models import AuditAction
from audit.services import record
from core.email import send_email


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
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        if not user.display_name:
            user.display_name = user.email.split("@")[0]
        if commit:
            user.save()
        return user

    def send_mail(self, template_prefix, email, context):
        """Every allauth email goes through core.email. The verification and reset links get
        their own templates; the rest reuse allauth's text inside `account_notice`."""
        name = template_prefix.rsplit("/", 1)[-1]
        if name in ("email_confirmation", "email_confirmation_signup"):
            send_email("email_verification", email, {"url": context["activate_url"]})
        elif name == "password_reset_key":
            send_email("password_reset", email, {"url": context["password_reset_url"]})
        else:
            request = allauth_context.request
            ctx = {"request": request, "email": email, "current_site": get_current_site(request)}
            msg = self.render_mail(template_prefix, email, {**ctx, **context})
            send_email("account_notice", email, {"subject": msg.subject, "message": msg.body})


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user):  # D35 user shape
        return {"id": str(user.pk), "email": user.email, "display_name": user.display_name}


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def authenticate_by_email(self, sociallogin):
        """D62: link only when the provider says the email is verified AND it is a verified
        address of a local account. allauth's default also matches unverified local addresses
        (and then wipes the password); we never link those. No match means a new account."""
        for addr in sociallogin.email_addresses:
            if not addr.verified:
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
        user.display_name = (name or user.email.split("@")[0])[:120]
        return user


def login_methods_for_email(email: str) -> list[str]:
    """Hook for SSO routing (SSO and SAML later); password only for now."""
    return ["password"]


def has_verified_email(user, email: str) -> bool:
    """True if `email` is any verified address of the user, primary or not (D25)."""
    return EmailAddress.objects.filter(user=user, email__iexact=email, verified=True).exists()


@receiver(user_logged_in)
def _logged_in(sender, request, user, **kwargs):
    record(AuditAction.AUTH_LOGIN, actor=user, lab=None, request=request)


@receiver(user_logged_out)
def _logged_out(sender, request, user, **kwargs):
    if user is not None:
        record(AuditAction.AUTH_LOGOUT, actor=user, lab=None, request=request)


@receiver(user_login_failed)
def _login_failed(sender, credentials, request=None, **kwargs):
    # Only the identifier is kept, never the password.
    label = str(credentials.get("email") or credentials.get("username") or "")[:100]
    record(AuditAction.AUTH_LOGIN_FAILED, actor=None, lab=None, request=request, actor_label=label)


@receiver(password_changed)
def _password_changed(sender, request, user, **kwargs):
    record(AuditAction.AUTH_PASSWORD_CHANGED, actor=user, lab=None, request=request)


@receiver(authenticator_added)
def _mfa_added(sender, request, user, authenticator, **kwargs):
    if authenticator.type == "totp":
        record(AuditAction.AUTH_MFA_ENABLED, actor=user, lab=None, request=request)


@receiver(authenticator_removed)
def _mfa_removed(sender, request, user, authenticator, **kwargs):
    if authenticator.type == "totp":
        record(AuditAction.AUTH_MFA_DISABLED, actor=user, lab=None, request=request)


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
