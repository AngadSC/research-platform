"""Auth module boundary (ARCHITECTURE section 7). Everything allauth-specific lives here;
no other module imports allauth. App code reads `request.user`."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.signals import password_changed
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.mfa.signals import authenticator_added, authenticator_removed
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication

from audit.models import AuditAction
from audit.services import record


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


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user):  # D35 user shape
        return {"id": str(user.pk), "email": user.email, "display_name": user.display_name}


def login_methods_for_email(email: str) -> list[str]:
    """Hook for SSO routing (SSO and SAML later); password only for now."""
    return ["password"]


def has_verified_email(user, email: str) -> bool:
    """True if `email` is one of the user's verified addresses (D25)."""
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
