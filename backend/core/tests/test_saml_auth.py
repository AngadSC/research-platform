"""Institutional SAML sign-in (D152 to D157). No real IdP: a test key pair signs responses the
way Shibboleth would, and python3-saml validates them for real (signature, audience,
destination, InResponseTo, time window)."""

import base64
import datetime as dt
import json
import re
import uuid
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, RequestFactory
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from audit.models import AuditAction, AuditEvent
from core.admin import InstitutionSSOAdmin
from core.auth import fetch_idp_metadata, login_methods_for_email
from core.models import Institution, InstitutionSSO, User

pytestmark = pytest.mark.django_db

BASE = "/_allauth/browser/v1"
CALLBACK = "/account/provider/callback"
IDP = "https://idp.test/idp/shibboleth"
ACS = "http://localhost/accounts/saml/ualberta/acs/"
OID = {
    "mail": "urn:oid:0.9.2342.19200300.100.1.3",
    "givenName": "urn:oid:2.5.4.42",
    "sn": "urn:oid:2.5.4.4",
    "eppn": "urn:oid:1.3.6.1.4.1.5923.1.1.1.6",
}


def _keypair(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pem_key, cert.public_bytes(serialization.Encoding.PEM).decode()


IDP_KEY, IDP_CERT = _keypair("idp.test")
OTHER_KEY, OTHER_CERT = _keypair("attacker.test")


@pytest.fixture
def sso(db):
    inst = Institution.objects.create(name="University of Alberta")
    return InstitutionSSO.objects.create(
        institution=inst,
        slug="ualberta",
        enabled=True,
        email_domains=["ualberta.ca"],
        idp_entity_id=IDP,
        idp_sso_url="https://idp.test/idp/profile/SAML2/Redirect/SSO",
        idp_x509cert=IDP_CERT,
    )


def sp_entity():
    return f"{settings.FRONTEND_URL}/accounts/saml/ualberta/metadata/"


def start(client):
    """The SPA's form POST; returns the AuthnRequest ID the IdP must answer."""
    client.get(f"{BASE}/config")
    form = {"provider": "saml:ualberta", "process": "login", "callback_url": CALLBACK}
    resp = client.post(f"{BASE}/auth/provider/redirect", form)
    assert resp.status_code == 302, resp.content
    to_idp = urlparse(resp["Location"])
    assert to_idp.netloc == "idp.test"
    xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(parse_qs(to_idp.query)["SAMLRequest"][0])
    return re.search(r'ID="([^"]+)"', xml.decode() if isinstance(xml, bytes) else xml)[1]


def _ts(delta=0):
    t = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=delta)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def saml_response(
    in_response_to,
    *,
    email="ada@ualberta.ca",
    eppn="ada@ualberta.ca",
    audience=None,
    expires_in=300,
    key=IDP_KEY,
    cert=IDP_CERT,
    sign=True,
    tamper=None,
):
    irt = f' InResponseTo="{in_response_to}"' if in_response_to else ""  # None: IdP-initiated
    attrs = {OID["mail"]: email, OID["givenName"]: "Ada", OID["sn"]: "Lovelace", OID["eppn"]: eppn}
    attr_xml = "".join(
        f'<saml:Attribute Name="{n}" NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri">'
        f"<saml:AttributeValue>{v}</saml:AttributeValue></saml:Attribute>"
        for n, v in attrs.items()
    )
    assertion = (
        '<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="_a{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_ts()}">'
        f"<saml:Issuer>{IDP}</saml:Issuer>"
        "<saml:Subject>"
        '<saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">'
        "_t1</saml:NameID>"
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData NotOnOrAfter="{_ts(expires_in)}" Recipient="{ACS}" '
        f"{irt}/>"
        "</saml:SubjectConfirmation></saml:Subject>"
        f'<saml:Conditions NotBefore="{_ts(-60)}" NotOnOrAfter="{_ts(expires_in)}">'
        f"<saml:AudienceRestriction><saml:Audience>{audience or sp_entity()}</saml:Audience>"
        "</saml:AudienceRestriction></saml:Conditions>"
        f'<saml:AuthnStatement AuthnInstant="{_ts()}" SessionIndex="_s1"><saml:AuthnContext>'
        "<saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:"
        "PasswordProtectedTransport</saml:AuthnContextClassRef></saml:AuthnContext>"
        "</saml:AuthnStatement>"
        f"<saml:AttributeStatement>{attr_xml}</saml:AttributeStatement>"
        "</saml:Assertion>"
    )
    if sign:
        assertion = OneLogin_Saml2_Utils.add_sign(assertion, key, cert).decode()
        assertion = re.sub(r"^<\?xml[^>]*>\s*", "", assertion)
    if tamper:
        assertion = assertion.replace(*tamper)
    xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="_r{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_ts()}" Destination="{ACS}" '
        f"{irt}>"
        f"<saml:Issuer>{IDP}</saml:Issuer>"
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
        f"</samlp:Status>{assertion}</samlp:Response>"
    )
    return base64.b64encode(xml.encode()).decode()


def post_acs(client, response):
    """The IdP's auto-submitted form to the ACS, then allauth's same-site hop to finish."""
    resp = client.post("/accounts/saml/ualberta/acs/", {"SAMLResponse": response})
    assert resp.status_code == 302
    return client.get(resp["Location"])


def saml_login(client=None, **kw):
    client = client or Client(HTTP_HOST="localhost")
    final = post_acs(client, saml_response(start(client), **kw))
    return client, final


def session_user(client):
    resp = client.get(f"{BASE}/auth/session")
    return resp.json()["data"]["user"]["id"] if resp.status_code == 200 else None


# ---- routing


def test_login_methods_routing(sso):
    assert login_methods_for_email("Ada@UAlberta.ca") == ["saml:ualberta", "password"]
    assert login_methods_for_email("ada@gmail.com") == ["password"]
    assert login_methods_for_email("ada@cs.ualberta.ca") == ["password"]  # exact domains only
    sso.require_sso = True
    sso.save()
    assert login_methods_for_email("ada@ualberta.ca") == ["saml:ualberta"]
    sso.enabled = False
    sso.save()
    assert login_methods_for_email("ada@ualberta.ca") == ["password"]


def test_login_methods_endpoint(sso):
    url = "/api/auth/login-methods/"
    resp = Client(HTTP_HOST="localhost").post(url, {"email": "ada@ualberta.ca"}, "application/json")
    assert resp.json() == {
        "methods": ["saml:ualberta", "password"],
        "institution": "University of Alberta",
    }
    resp = Client(HTTP_HOST="localhost").post(url, {"email": "ada@example.com"}, "application/json")
    assert resp.json() == {"methods": ["password"], "institution": None}
    assert (
        Client(HTTP_HOST="localhost").post(url, {"email": "nope"}, "application/json").status_code
        == 400
    )


def test_headless_config_lists_enabled_institutions_only(sso):
    providers = (
        Client(HTTP_HOST="localhost")
        .get(f"{BASE}/config")
        .json()["data"]["socialaccount"]["providers"]
    )
    assert {"id": "saml:ualberta", "name": "University of Alberta"}.items() <= next(
        p for p in providers if p["id"] == "saml:ualberta"
    ).items()
    sso.enabled = False
    sso.save()
    providers = (
        Client(HTTP_HOST="localhost")
        .get(f"{BASE}/config")
        .json()["data"]["socialaccount"]["providers"]
    )
    assert not [p for p in providers if p["id"].startswith("saml:")]


# ---- accounts and linking


def test_new_user_via_sso(sso):
    client, final = saml_login()
    assert final.status_code == 302 and final["Location"] == CALLBACK
    user = User.objects.get(email="ada@ualberta.ca")
    assert session_user(client) == str(user.pk)
    assert user.display_name == "Ada Lovelace" and not user.has_usable_password()
    assert EmailAddress.objects.get(user=user).verified  # the IdP is authoritative (D154)
    assert SocialAccount.objects.get(user=user).uid == "ada@ualberta.ca"  # ePPN, not NameID
    login = AuditEvent.objects.get(action=AuditAction.AUTH_LOGIN, actor=user)
    assert login.metadata == {"method": "saml:ualberta"}
    # A returning user is found by (provider, uid).
    client2, _ = saml_login()
    assert session_user(client2) == str(user.pk) and User.objects.count() == 1


def test_links_existing_verified_password_account(sso, make_user, verify_email):
    user = make_user(email="ada@ualberta.ca")
    verify_email(user)
    client, _ = saml_login()
    assert session_user(client) == str(user.pk)
    assert SocialAccount.objects.get().user == user and User.objects.count() == 1
    user.refresh_from_db()
    assert user.has_usable_password()  # D154: linking keeps the password
    linked = AuditEvent.objects.get(action=AuditAction.AUTH_SOCIAL_CONNECTED, actor=user)
    assert linked.metadata == {"provider": "saml:ualberta"}


def test_links_verified_secondary_address(sso, make_user, verify_email):
    user = make_user(email="ada@gmail.com")
    verify_email(user)
    verify_email(user, email="ada@ualberta.ca")
    client, _ = saml_login()
    assert session_user(client) == str(user.pk)


def test_unverified_local_address_never_links(sso, make_user, verify_email):
    squatter = make_user(email="sq@example.com")
    verify_email(squatter)
    verify_email(squatter, verified=False, email="ada@ualberta.ca")
    client, _ = saml_login()
    assert session_user(client) is None
    assert not SocialAccount.objects.exists() and User.objects.count() == 1
    squatter.refresh_from_db()
    assert squatter.has_usable_password()


@pytest.mark.parametrize("email", ["ada@gmail.com", "ada@ualberta.ca.evil.com", ""])
def test_email_outside_configured_domains_is_refused(sso, make_user, verify_email, email):
    victim = make_user(email="ada@gmail.com")
    verify_email(victim)
    client, final = saml_login(email=email)
    assert "error=denied" in final["Location"]
    assert session_user(client) is None
    assert not SocialAccount.objects.exists() and User.objects.count() == 1


# ---- the response itself


@pytest.mark.parametrize(
    "bad",
    [
        {"sign": False},
        {
            "tamper": (
                "ada@ualberta.ca</saml:AttributeValue>",
                "eve@ualberta.ca</saml:AttributeValue>",
            )
        },
        {"key": OTHER_KEY, "cert": OTHER_CERT},
        {"key": OTHER_KEY},  # claims the IdP's cert, signed with another key
        {"audience": "https://someone-else.example/sp"},
        {"expires_in": -600},  # past the 300 s clock drift
    ],
    ids=["unsigned", "tampered", "wrong-key", "wrong-key-right-cert", "audience", "expired"],
)
def test_bad_responses_are_rejected(sso, bad):
    client, final = saml_login(**bad)
    assert final.status_code == 302 and "error=" in final["Location"]
    assert session_user(client) is None and not User.objects.exists()


def test_replayed_response_is_rejected(sso):
    client = Client(HTTP_HOST="localhost")
    response = saml_response(start(client))
    post_acs(client, response)
    first = session_user(client)
    assert first
    other = Client(HTTP_HOST="localhost")  # an attacker's browser: no stashed request state
    assert post_acs(other, response).status_code == 403
    assert session_user(other) is None
    client.delete(f"{BASE}/auth/session")
    assert post_acs(client, response).status_code == 403  # same browser, state used up
    assert session_user(client) is None


def test_idp_initiated_login_is_rejected(sso):
    client = Client(HTTP_HOST="localhost")
    final = post_acs(client, saml_response(None))
    assert session_user(client) is None and not User.objects.exists()
    assert "error=" in final["Location"]


# ---- require SSO (D156)


def test_require_sso_blocks_password_login_and_signup(sso, make_user, verify_email):
    user = make_user(email="ada@ualberta.ca")
    verify_email(user)
    sso.require_sso = True
    sso.save()
    client = Client(HTTP_HOST="localhost")
    client.get(f"{BASE}/config")
    csrf = {"X-CSRFToken": client.cookies["csrftoken"].value}
    body = {"email": "ada@ualberta.ca", "password": "pw"}
    resp = client.post(f"{BASE}/auth/login", body, "application/json", headers=csrf)
    assert resp.status_code == 400
    assert "sign in with University of Alberta" in resp.content.decode()
    body = {"email": "bob@ualberta.ca", "password": "a-long-passphrase-1"}
    resp = client.post(f"{BASE}/auth/signup", body, "application/json", headers=csrf)
    assert resp.status_code == 400 and not User.objects.filter(email="bob@ualberta.ca").exists()
    # Other domains are untouched, and SSO itself still works.
    other = make_user(email="x@example.com")
    verify_email(other)
    body = {"email": "x@example.com", "password": "pw"}
    assert (
        client.post(f"{BASE}/auth/login", body, "application/json", headers=csrf).status_code == 200
    )
    client2, _ = saml_login()
    assert session_user(client2) == str(user.pk)


# ---- SP metadata and configuration


def test_sp_metadata(sso):
    resp = Client(HTTP_HOST="localhost").get("/accounts/saml/ualberta/metadata/")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/xml")
    xml = resp.content.decode()
    assert f'entityID="{sp_entity()}"' in xml
    assert f'Location="{ACS}"' in xml and "HTTP-POST" in xml
    assert 'WantAssertionsSigned="true"' in xml
    year = int(re.search(r'validUntil="(\d{4})', xml)[1])
    assert year >= dt.datetime.now(dt.UTC).year + 9  # not python3-saml's 2 days
    assert Client(HTTP_HOST="localhost").get("/accounts/saml/nobody/metadata/").status_code == 404
    sso.enabled = False
    sso.save()
    assert Client(HTTP_HOST="localhost").get("/accounts/saml/ualberta/metadata/").status_code == 404


METADATA = f"""<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  entityID="{IDP}"><md:IDPSSODescriptor
  protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing"><ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:X509Data><ds:X509Certificate>{"".join(IDP_CERT.splitlines()[1:-1])}</ds:X509Certificate>
  </ds:X509Data></ds:KeyInfo></md:KeyDescriptor>
  <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
  Location="https://idp.test/sso"/></md:IDPSSODescriptor></md:EntityDescriptor>"""


def test_metadata_url_fills_idp_fields_through_the_safe_client(sso):
    sso.idp_entity_id = sso.idp_sso_url = sso.idp_x509cert = ""
    sso.idp_metadata_url = "https://idp.test/metadata"
    fake = SimpleNamespace(status_code=200, content=METADATA.encode())
    with mock.patch("integrations.http.send", return_value=fake) as send:
        sso.full_clean()
    assert send.call_args.args == ("GET", "https://idp.test/metadata")
    assert send.call_args.kwargs["provider"].api_hosts == {"idp.test"}
    assert (sso.idp_entity_id, sso.idp_sso_url) == (IDP, "https://idp.test/sso")
    assert sso.idp_x509cert in IDP_CERT.replace("\n", "")
    sso.idp_metadata_url = "http://idp.test/metadata"
    with pytest.raises(ValidationError):
        sso.full_clean()
    sso.idp_metadata_url = "https://idp.test/metadata"
    with mock.patch("integrations.http.send", return_value=SimpleNamespace(status_code=404)):
        with pytest.raises(ValidationError):
            fetch_idp_metadata(sso)


def test_config_validation(sso):
    other = InstitutionSSO(
        institution=Institution.objects.create(name="Other U"),
        slug="other",
        enabled=True,
        email_domains=["UAlberta.ca"],
        idp_entity_id="x",
        idp_sso_url="https://x.test/sso",
        idp_x509cert="x",
    )
    with pytest.raises(ValidationError, match="Already routed"):
        other.full_clean()
    other.email_domains = ["@Other.CA "]
    other.full_clean()
    assert other.email_domains == ["other.ca"]
    other.idp_sso_url = "http://x.test/sso"
    with pytest.raises(ValidationError):
        other.full_clean()


def test_admin_is_superuser_only(sso, make_user):
    admin = InstitutionSSOAdmin(InstitutionSSO, None)
    request = RequestFactory().get("/")
    request.user = make_user(is_staff=True)
    assert not admin.has_module_permission(request)
    assert not admin.has_change_permission(request, sso)
    request.user = make_user(is_staff=True, is_superuser=True)
    assert admin.has_module_permission(request) and admin.has_change_permission(request, sso)


def test_configure_sso_command(tmp_path, capsys, db):
    path = tmp_path / "ualberta.json"
    config = {
        "institution": "university of alberta",
        "slug": "ualberta",
        "enabled": True,
        "email_domains": ["ualberta.ca"],
        "idp_entity_id": IDP,
        "idp_sso_url": "https://idp.test/sso",
        "idp_x509cert": IDP_CERT,
    }
    Institution.objects.create(name="University of Alberta")
    path.write_text(json.dumps(config))
    call_command("configure_sso", str(path))
    cfg = InstitutionSSO.objects.get()
    assert cfg.institution.name == "University of Alberta" and cfg.enabled
    out = capsys.readouterr().out
    assert f"SP acs: {settings.FRONTEND_URL}/accounts/saml/ualberta/acs/" in out
