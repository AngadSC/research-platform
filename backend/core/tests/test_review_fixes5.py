"""Run 5 review fixes in the auth layer: SAML single logout is off (D201) and require-SSO cannot
be walked around with a secondary address, Google or another institution's SSO (D202)."""

import pytest
from django.test import Client

from core.auth import _required_sso
from core.models import Institution, InstitutionSSO
from core.tests.test_google_auth import google, google_login, session_user  # noqa: F401
from core.tests.test_saml_auth import BASE, saml_login, sso  # noqa: F401

pytestmark = pytest.mark.django_db


def password_login(email):
    client = Client(HTTP_HOST="localhost")
    client.get(f"{BASE}/config")
    csrf = {"X-CSRFToken": client.cookies["csrftoken"].value}
    body = {"email": email, "password": "pw"}
    resp = client.post(f"{BASE}/auth/login", body, "application/json", headers=csrf)
    return client, resp


def test_saml_single_logout_endpoint_is_not_served(sso):
    client, _ = saml_login()
    assert session_user(client)
    for method in (client.get, client.post):
        assert method("/accounts/saml/ualberta/sls/", {"SAMLRequest": "x"}).status_code == 404
    assert session_user(client)  # an unsigned logout request cannot end a session


@pytest.fixture
def require(sso, make_user, verify_email):
    """ada: primary gmail address, plus a verified address at the require-SSO university."""
    sso.require_sso = True
    sso.save()
    user = make_user(email="ada@gmail.com")
    verify_email(user)
    verify_email(user, email="ada@ualberta.ca")
    return user


def test_password_login_with_a_secondary_sso_address_is_refused(require):
    client, resp = password_login("ada@gmail.com")
    assert resp.status_code == 400
    assert "sign in with University of Alberta" in resp.content.decode()
    assert session_user(client) is None


def test_other_people_and_optional_sso_still_use_passwords(sso, make_user, verify_email):
    plain = make_user(email="bob@gmail.com")
    verify_email(plain)
    assert password_login("bob@gmail.com")[1].status_code == 200
    both = make_user(email="ada@gmail.com")
    verify_email(both)
    verify_email(both, email="ada@ualberta.ca")
    assert password_login("ada@gmail.com")[1].status_code == 200  # require_sso is off


def test_google_login_is_refused_for_a_user_with_a_secondary_sso_address(require, google):  # noqa: F811
    client = Client(HTTP_HOST="localhost")
    google_login(client, email="ada@gmail.com", verified=True)
    assert session_user(client) is None


def test_only_the_requiring_institutions_own_sso_unlocks_its_addresses(require):
    other = Institution.objects.create(name="Other University")
    InstitutionSSO.objects.create(
        institution=other,
        slug="other",
        enabled=True,
        email_domains=["other.edu"],
        idp_entity_id="https://other.test/idp",
        idp_sso_url="https://other.test/sso",
        idp_x509cert="x",
    )
    assert _required_sso(require, "saml:ualberta") is None
    assert _required_sso(require, "saml:other").slug == "ualberta"  # another institution's SSO
    assert _required_sso(require, "google").slug == "ualberta"
    assert _required_sso(require, "password").slug == "ualberta"
