"""Google sign-in (ARCHITECTURE section 7, D62). Google is mocked completely: no network."""

from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.socialaccount.models import SocialAccount
from django.test import Client

from audit.models import AuditAction, AuditEvent
from core.models import User

pytestmark = pytest.mark.django_db

BASE = "/_allauth/browser/v1"
CALLBACK = "/account/provider/callback"
GOOGLE_APP = {"client_id": "test-client", "secret": "test-secret"}


def _providers(apps):
    return {"google": {"SCOPE": ["openid", "email", "profile"], "APPS": apps}}


@pytest.fixture
def google(settings):
    settings.SOCIALACCOUNT_PROVIDERS = _providers([GOOGLE_APP])


def csrf(client):
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def google_login(client, *, email, verified, sub="google-1", process="login", **claims):
    """The SPA's form POST to the provider redirect, then Google's redirect back."""
    client.get(f"{BASE}/config")
    form = {"provider": "google", "callback_url": CALLBACK, "process": process}
    resp = client.post(f"{BASE}/auth/provider/redirect", form)
    assert resp.status_code == 302, resp.content
    to_google = urlparse(resp["Location"])
    params = parse_qs(to_google.query)
    assert to_google.netloc == "accounts.google.com"
    assert sorted(params["scope"][0].split()) == ["email", "openid", "profile"]  # no Drive
    identity = {
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "given_name": "Gee",
        "family_name": "User",
        **claims,
    }
    token = {"access_token": "at", "id_token": "idt", "expires_in": 3600}
    with (
        mock.patch(
            "allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token",
            return_value=token,
        ),
        mock.patch(
            "allauth.socialaccount.providers.google.views._verify_and_decode",
            return_value=identity,
        ),
    ):
        back = client.get(
            "/accounts/google/login/callback/",
            {"code": "c", "state": params["state"][0]},
        )
    assert back.status_code == 302
    return back["Location"]


def session_user(client):
    resp = client.get(f"{BASE}/auth/session")
    return resp.json()["data"]["user"]["id"] if resp.status_code == 200 else None


def test_provider_hidden_without_client_id(settings):
    settings.SOCIALACCOUNT_PROVIDERS = _providers([])
    assert Client().get(f"{BASE}/config").json()["data"]["socialaccount"]["providers"] == []
    settings.SOCIALACCOUNT_PROVIDERS = _providers([GOOGLE_APP])
    providers = Client().get(f"{BASE}/config").json()["data"]["socialaccount"]["providers"]
    assert [p["id"] for p in providers] == ["google"]


def test_new_user_via_google(google):
    client = Client()
    assert google_login(client, email="New@Example.com", verified=True) == CALLBACK
    user = User.objects.get(email__iexact="new@example.com")
    assert session_user(client) == str(user.pk)
    assert user.display_name == "Gee User" and not user.has_usable_password()
    assert EmailAddress.objects.get(user=user).verified
    assert SocialAccount.objects.get(user=user).uid == "google-1"
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_SOCIAL_CONNECTED, actor=user).exists()


@pytest.mark.parametrize("primary", [True, False])
def test_links_to_verified_address(google, make_user, verify_email, primary):
    user = make_user(email="me@example.com")
    verify_email(user)
    if not primary:
        verify_email(user, email="alt@example.com")
    client = Client()
    google_email = "ME@example.com" if primary else "Alt@Example.com"
    assert google_login(client, email=google_email, verified=True, hd="example.com") == CALLBACK
    assert session_user(client) == str(user.pk)
    assert SocialAccount.objects.get().user == user
    assert User.objects.count() == 1
    user.refresh_from_db()
    assert user.has_usable_password()


def test_google_unverified_email_never_links(google, make_user, verify_email):
    user = make_user(email="me@example.com")
    verify_email(user)
    client = Client()
    google_login(client, email="me@example.com", verified=False)
    assert session_user(client) is None
    assert not SocialAccount.objects.exists() and User.objects.count() == 1


def test_unverified_local_address_never_links(google, make_user, verify_email):
    owner = make_user(email="me@example.com")
    verify_email(owner)
    squatter = make_user(email="sq@example.com")
    verify_email(squatter)
    verify_email(squatter, verified=False, email="victim@example.com")
    client = Client()
    assert google_login(client, email="victim@example.com", verified=True) == CALLBACK
    # D62: no link and no second account; the SPA sees the same pending verify_email stage as
    # an email signup for a taken address.
    flows = client.get(f"{BASE}/auth/session").json()["data"]["flows"]
    assert {"id": "verify_email", "is_pending": True} in flows
    assert session_user(client) is None
    assert not SocialAccount.objects.exists() and User.objects.count() == 2
    squatter.refresh_from_db()
    assert squatter.has_usable_password()


def test_google_claims_an_abandoned_password_signup(google, make_user, verify_email, mailoutbox):
    """D265: someone signed up with a password but never confirmed; Google proves the address,
    so it links, confirms the address, wipes the password and sends no email."""
    user = make_user(email="me@gmail.com")
    verify_email(user, verified=False)
    client = Client()
    assert google_login(client, email="me@gmail.com", verified=True) == CALLBACK
    assert session_user(client) == str(user.pk)
    assert User.objects.count() == 1 and SocialAccount.objects.get().user == user
    user.refresh_from_db()
    assert not user.has_usable_password()  # whoever typed that password is locked out
    assert EmailAddress.objects.get(user=user).verified
    assert not [m for m in mailoutbox if "confirm" in m.subject.lower()]


def test_unverified_added_address_never_links_even_when_vouched(google, make_user, verify_email):
    """D72 still holds: an address added to someone else's account is never claimed."""
    squatter = make_user(email="sq@example.com")
    verify_email(squatter)
    verify_email(squatter, verified=False, email="victim@gmail.com")
    client = Client()
    google_login(client, email="victim@gmail.com", verified=True)
    assert session_user(client) is None
    assert not SocialAccount.objects.exists()
    squatter.refresh_from_db()
    assert squatter.has_usable_password()


def test_disconnect_needs_a_password(google):
    client = Client()
    google_login(client, email="g@example.com", verified=True)
    user = User.objects.get(email="g@example.com")
    body = {"provider": "google", "account": "google-1"}
    url = f"{BASE}/account/providers"
    resp = client.delete(url, body, "application/json", headers=csrf(client))
    assert resp.status_code == 400 and SocialAccount.objects.filter(user=user).exists()
    user.set_password("a-new-pass-123")
    user.save()
    client.force_login(user, backend="allauth.account.auth_backends.AuthenticationBackend")
    reauth(client, "a-new-pass-123")  # D74: disconnecting needs a recent password check
    resp = client.delete(url, body, "application/json", headers=csrf(client))
    assert resp.status_code == 200, resp.content
    assert not SocialAccount.objects.exists()
    disconnected = AuditEvent.objects.filter(action=AuditAction.AUTH_SOCIAL_DISCONNECTED)
    assert disconnected.filter(actor=user).count() == 1


def test_extra_email_add_verify_remove_and_no_double_claim(
    make_user, verify_email, django_capture_on_commit_callbacks
):
    taken = make_user(email="taken@example.com")
    verify_email(taken)
    user = make_user(email="u@example.com")
    verify_email(user)
    client = Client()
    client.get(f"{BASE}/config")
    login = {"email": "u@example.com", "password": "pw"}
    resp = client.post(f"{BASE}/auth/login", login, "application/json", headers=csrf(client))
    assert resp.status_code == 200
    client.post(
        f"{BASE}/auth/reauthenticate", {"password": "pw"}, "application/json", headers=csrf(client)
    )
    url = f"{BASE}/account/email"
    with django_capture_on_commit_callbacks(execute=True):
        for email in ("extra@example.com", "taken@example.com"):
            resp = client.post(url, {"email": email}, "application/json", headers=csrf(client))
            assert resp.status_code == 200, resp.content
    for email in ("extra@example.com", "taken@example.com"):
        key = EmailConfirmationHMAC(EmailAddress.objects.get(user=user, email=email)).key
        client.post(
            f"{BASE}/auth/email/verify", {"key": key}, "application/json", headers=csrf(client)
        )
    mine = dict(EmailAddress.objects.filter(user=user).values_list("email", "verified"))
    assert mine == {"u@example.com": True, "extra@example.com": True, "taken@example.com": False}
    assert EmailAddress.objects.get(user=taken).verified
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.delete(
            url, {"email": "extra@example.com"}, "application/json", headers=csrf(client)
        )
    assert resp.status_code == 200, resp.content
    added = AuditEvent.objects.filter(action=AuditAction.AUTH_EMAIL_ADDED, actor=user)
    assert added.count() == 2
    removed = AuditEvent.objects.get(action=AuditAction.AUTH_EMAIL_REMOVED, actor=user)
    assert removed.metadata["email"] == "extra@example.com"


# ---- Run 2 security review fixes (D72 to D74) ----


def login(client, email, password="pw"):
    client.get(f"{BASE}/config")
    body = {"email": email, "password": password}
    resp = client.post(f"{BASE}/auth/login", body, "application/json", headers=csrf(client))
    assert resp.status_code == 200, resp.content


def reauth(client, password="pw"):
    body = {"password": password}
    resp = client.post(
        f"{BASE}/auth/reauthenticate", body, "application/json", headers=csrf(client)
    )
    assert resp.status_code == 200, resp.content


def send(client, url, body, method="post"):
    return getattr(client, method)(url, body, "application/json", headers=csrf(client))


def test_added_address_probe_chain(
    google, make_lab, make_user, join, verify_email, django_capture_on_commit_callbacks
):
    """D72: the attacker adds the victim's address; the victim's logged-out confirm fails, so
    neither Google sign-in nor an invite for that address lands in the attacker's account."""
    from django.core import mail
    from rest_framework.test import APIClient

    from labs.models import LabMembership, LabRole

    attacker = make_user(email="attacker@example.com")
    verify_email(attacker)
    client = Client()
    login(client, "attacker@example.com")
    reauth(client)
    with django_capture_on_commit_callbacks(execute=True):
        resp = send(client, f"{BASE}/account/email", {"email": "victim@gmail.com"})
    assert resp.status_code == 200, resp.content
    msg = next(m for m in mail.outbox if m.to == ["victim@gmail.com"])
    assert "attacker@example.com" in msg.body and "ignore" in msg.body  # names the account
    key = EmailConfirmationHMAC(EmailAddress.objects.get(email="victim@gmail.com")).key

    victim_browser = Client()  # logged out
    victim_browser.get(f"{BASE}/config")
    resp = send(victim_browser, f"{BASE}/auth/email/verify", {"key": key})
    assert resp.status_code == 403
    assert "Sign in to the account" in resp.json()["errors"][0]["message"]
    assert not EmailAddress.objects.get(email="victim@gmail.com").verified

    google_login(victim_browser, email="victim@gmail.com", verified=True)
    assert session_user(victim_browser) is None
    assert not SocialAccount.objects.filter(user=attacker).exists()

    lab, pi = make_lab("Lab X"), make_user()
    join(pi, lab, LabRole.PI)
    mail.outbox.clear()
    pi_api = APIClient()
    pi_api.force_login(pi)
    with django_capture_on_commit_callbacks(execute=True):
        body = {"email": "victim@gmail.com", "role": "member"}
        pi_api.post(f"/api/labs/{lab.pk}/invites/", body, "json")
    token = mail.outbox[0].body.split("/invite/")[1].split()[0]
    attacker_api = APIClient()
    attacker_api.force_login(attacker)
    assert attacker_api.post("/api/invites/accept/", {"token": token}, "json").status_code == 403
    assert not LabMembership.objects.for_lab(lab).filter(user=attacker).exists()


def test_signup_address_still_confirms_logged_out(make_user):
    user = make_user(email="new@example.com")
    address = EmailAddress.objects.create(
        user=user, email="new@example.com", primary=True, verified=False
    )
    client = Client()
    client.get(f"{BASE}/config")
    key = EmailConfirmationHMAC(address).key
    resp = send(client, f"{BASE}/auth/email/verify", {"key": key})
    assert resp.status_code in (200, 401), resp.content
    assert EmailAddress.objects.get(pk=address.pk).verified


def test_added_address_confirms_for_its_own_account(make_user, verify_email):
    user = make_user(email="u@example.com")
    verify_email(user)
    other = verify_email(user, verified=False, email="extra@example.com")
    client = Client()
    login(client, "u@example.com")
    key = EmailConfirmationHMAC(other).key
    assert send(client, f"{BASE}/auth/email/verify", {"key": key}).status_code == 200
    assert EmailAddress.objects.get(pk=other.pk).verified


@pytest.mark.parametrize(
    "email,claims,links",
    [
        ("me@gmail.com", {}, True),
        ("me@googlemail.com", {}, True),
        ("me@uni.edu", {"hd": "uni.edu"}, True),
        ("me@uni.edu", {}, False),
        ("me@uni.edu", {"hd": "other.edu"}, False),
        ("me@example.com", {"hd": "gmail.com"}, False),
    ],
)
def test_google_links_by_email_only_for_gmail_or_matching_hd(
    google, make_user, verify_email, email, claims, links
):
    """D73."""
    user = make_user(email=email)
    verify_email(user)
    client = Client()
    google_login(client, email=email, verified=True, **claims)
    assert (session_user(client) == str(user.pk)) is links
    assert SocialAccount.objects.filter(user=user).exists() is links
    assert User.objects.count() == 1


def test_reauthentication_required_for_account_changes(
    make_user, verify_email, django_capture_on_commit_callbacks
):
    """D74."""
    user = make_user(email="u@example.com")
    verify_email(user)
    client = Client()
    login(client, "u@example.com")
    url = f"{BASE}/account/email"
    resp = send(client, url, {"email": "x@example.com"})
    assert resp.status_code == 401
    assert {"id": "reauthenticate"} in resp.json()["data"]["flows"]
    reauth(client)
    with django_capture_on_commit_callbacks(execute=True):
        assert send(client, url, {"email": "x@example.com"}).status_code == 200


def test_google_connect_and_disconnect_need_reauthentication(google, make_user, verify_email):
    user = make_user(email="u@example.com")
    verify_email(user)
    client = Client()
    login(client, "u@example.com")
    google_login(client, email="u@gmail.com", verified=True, sub="g2", process="connect")
    assert not SocialAccount.objects.exists()  # the callback redirected with an error
    reauth(client)
    google_login(client, email="u@gmail.com", verified=True, sub="g2", process="connect")
    assert SocialAccount.objects.filter(user=user).exists()
    client = Client()
    login(client, "u@example.com")
    body = {"provider": "google", "account": "g2"}
    resp = send(client, f"{BASE}/account/providers", body, "delete")
    assert resp.status_code == 401
    reauth(client)
    assert send(client, f"{BASE}/account/providers", body, "delete").status_code == 200


def test_reauthentication_flows_for_mfa_and_passwordless_users(make_user, verify_email):
    from allauth.mfa.models import Authenticator

    user = make_user(email="m@example.com")
    verify_email(user)
    verify_email(user, email="x@example.com")
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client = Client()
    client.get(f"{BASE}/config")
    client.force_login(user, backend="allauth.account.auth_backends.AuthenticationBackend")
    resp = send(client, f"{BASE}/account/email", {"email": "x@example.com"}, "delete")
    assert resp.status_code == 401, resp.content
    ids = [f["id"] for f in resp.json()["data"]["flows"]]
    assert "reauthenticate" in ids and "mfa_reauthenticate" in ids

    social = User.objects.create(email="g@example.com")  # no password, no MFA: nothing to prove
    social.set_unusable_password()
    social.save()
    verify_email(social)
    client = Client()
    client.get(f"{BASE}/config")
    client.force_login(social, backend="allauth.account.auth_backends.AuthenticationBackend")
    resp = send(client, f"{BASE}/account/email", {"email": "y@example.com"})
    assert resp.status_code == 200, resp.content


def test_email_change_notifies_the_owner(
    make_user, verify_email, django_capture_on_commit_callbacks
):
    from django.core import mail

    user = make_user(email="u@example.com")
    verify_email(user)
    verify_email(user, email="old@example.com")
    client = Client()
    login(client, "u@example.com")
    reauth(client)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        send(client, f"{BASE}/account/email", {"email": "old@example.com"}, "delete")
    assert any(m.to == ["u@example.com"] for m in mail.outbox)


def test_email_address_cap_and_rate_limit(make_user, verify_email):
    user = make_user(email="u@example.com")
    verify_email(user)
    for n in range(4):
        verify_email(user, email=f"e{n}@example.com")  # five in total
    client = Client()
    login(client, "u@example.com")
    reauth(client)
    url = f"{BASE}/account/email"
    resp = send(client, url, {"email": "sixth@example.com"})
    assert resp.status_code == 400 and not EmailAddress.objects.filter(email="sixth@example.com")


def test_email_management_is_rate_limited_to_five_an_hour(make_user, verify_email):
    user = make_user(email="u@example.com")
    verify_email(user)
    client = Client()
    login(client, "u@example.com")
    reauth(client)
    body = {"email": "nobody@example.com", "primary": True}
    codes = [send(client, f"{BASE}/account/email", body, "patch").status_code for _ in range(6)]
    assert codes[:5] == [400] * 5 and codes[5] == 429


def test_one_tap_token_endpoint_is_not_routed(google):
    body = {"id_token": "x", "client_id": "test-client"}
    assert Client().post("/accounts/google/login/token/", body).status_code == 404
