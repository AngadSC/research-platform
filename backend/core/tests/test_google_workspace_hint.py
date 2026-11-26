# ruff: noqa: F811 - pytest fixtures imported from sibling test modules
"""Email-first sign-in offers an institution's Google Workspace (Institution.google_domains).
The hint never decides linking: that still needs Google's verified `hd` claim (D73)."""

from io import StringIO
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.socialaccount.models import SocialAccount
from django.core.management import CommandError, call_command
from django.test import Client

from core.models import Institution, User
from core.tests.test_google_auth import (  # noqa: F401
    BASE,
    CALLBACK,
    google,
    google_login,
    session_user,
)
from core.tests.test_saml_auth import sso  # noqa: F401

pytestmark = pytest.mark.django_db
URL = "/api/auth/login-methods/"


@pytest.fixture
def workspace(db):
    inst, _ = Institution.objects.get_or_create(name="University of Alberta")
    inst.google_domains = ["ualberta.ca"]
    inst.save()
    return inst


def methods(email):
    return Client().post(URL, {"email": email}, "application/json").json()


class HintClient(Client):
    """The SPA's Google button after email-first login: the form also carries login_hint."""

    def __init__(self, hint, extra=None):
        super().__init__()
        self.hint, self.extra = hint, extra or {}

    def post(self, path, data=None, *args, **kwargs):
        if path.endswith("/auth/provider/redirect"):
            data = {**data, "login_hint": self.hint, **self.extra}
        return super().post(path, data, *args, **kwargs)


def to_google(client):
    client.get(f"{BASE}/config")
    form = {"provider": "google", "callback_url": CALLBACK, "process": "login"}
    resp = client.post(f"{BASE}/auth/provider/redirect", form)
    assert resp.status_code == 302
    return parse_qs(urlparse(resp["Location"]).query)


def test_workspace_domain_offers_google_then_password(google, workspace):
    uni = {"methods": ["google", "password"], "institution": "University of Alberta"}
    assert methods("Ada@UAlberta.ca") == uni
    assert methods("ada@cs.ualberta.ca") == {"methods": ["password"], "institution": None}
    assert methods("ada@example.test") == {"methods": ["password"], "institution": None}


def test_no_google_offer_without_google_sign_in(workspace):
    assert methods("ada@ualberta.ca") == {"methods": ["password"], "institution": None}


def test_saml_wins_over_google(google, sso):
    sso.institution.google_domains = ["ualberta.ca"]
    sso.institution.save()
    assert methods("ada@ualberta.ca")["methods"] == ["saml:ualberta", "password"]
    sso.require_sso = True
    sso.save()
    assert methods("ada@ualberta.ca")["methods"] == ["saml:ualberta"]


def test_redirect_passes_hd_and_login_hint_for_listed_domains_only(google, workspace):
    params = to_google(HintClient("Ada@UAlberta.ca"))
    assert params["hd"] == ["ualberta.ca"] and params["login_hint"] == ["Ada@UAlberta.ca"]
    assert params["access_type"] == ["online"]  # the configured params are kept
    for client in (HintClient("ada@example.test"), HintClient("not an email"), Client()):
        params = to_google(client)
        assert "hd" not in params and "login_hint" not in params
    # hd only ever comes from our list, never from the browser
    params = to_google(HintClient("ada@example.test", {"hd": "ualberta.ca"}))
    assert "hd" not in params


@pytest.mark.parametrize(
    "claims,links", [({"hd": "ualberta.ca"}, True), ({}, False), ({"hd": "other.edu"}, False)]
)
def test_hint_never_links_without_matching_hd(
    google, workspace, make_user, verify_email, claims, links
):
    """D73 unchanged: our hint is not Google vouching for the domain."""
    user = make_user(email="ada@ualberta.ca")
    verify_email(user)
    client = HintClient("ada@ualberta.ca")
    google_login(client, email="ada@ualberta.ca", verified=True, **claims)
    assert (session_user(client) == str(user.pk)) is links
    assert SocialAccount.objects.filter(user=user).exists() is links
    assert User.objects.count() == 1


def test_require_sso_still_refuses_google(google, sso, make_user, verify_email):
    sso.require_sso = True
    sso.save()
    sso.institution.google_domains = ["ualberta.ca"]
    sso.institution.save()
    user = make_user(email="ada@ualberta.ca")
    verify_email(user)
    client = HintClient("ada@ualberta.ca")
    google_login(client, email="ada@ualberta.ca", verified=True, hd="ualberta.ca")
    assert session_user(client) is None


def test_set_google_domains_command(db):
    out = StringIO()
    call_command(
        "set_google_domains", "University of Alberta", "UAlberta.ca", "@ualberta.ca", stdout=out
    )
    assert Institution.objects.get(name="University of Alberta").google_domains == ["ualberta.ca"]
    Institution.objects.create(name="Other University", google_domains=["other.test"])
    with pytest.raises(CommandError):
        call_command("set_google_domains", "university of alberta", "other.test")
    with pytest.raises(CommandError):
        call_command("set_google_domains", "University of Alberta", "not a domain")
    call_command("set_google_domains", "University of Alberta", stdout=out)
    assert Institution.objects.get(name="University of Alberta").google_domains == []
