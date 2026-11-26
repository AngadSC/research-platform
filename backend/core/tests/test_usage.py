"""D379: the site-wide Usage page. Staff only (everyone else 404), counts across labs, test
accounts left out by default, and no titles or text in the answer."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from assistant.models import Conversation, Message, Role
from audit import services as audit
from audit.models import AuditAction
from core.models import Institution, User
from labs.models import Lab, LabChatMessage, LabMembership, LabRole
from projects.models import Project

URL = "/api/usage/"


def person(email, **kw):
    return User.objects.create_user(email=email, password="pw", **kw)


def get(user, query=""):
    client = APIClient()
    client.force_authenticate(user)  # no sign-in signal, so no extra auth.login events
    return client.get(URL + query)


@pytest.fixture
def world(db):
    """Two labs and three real-looking people (`.example`), plus one seed account (.test)."""
    staff = person("founder@usage.example", is_staff=True, display_name="Founder")
    inst = Institution.objects.create(name="Usage University")
    ada = person("ada@usage.example", display_name="Ada")
    bob = person("bob@usage.example", display_name="Bob")
    cy = person("cy@usage.example", display_name="Cy")
    seed = person("pi@example.test", display_name="Seed PI")
    lab_a = Lab.objects.create(institution=inst, name="Secret Lab Name A", created_by=ada)
    lab_b = Lab.objects.create(institution=inst, name="Secret Lab Name B", created_by=bob)
    LabMembership.objects.create(lab=lab_a, user=ada, role=LabRole.PI)
    LabMembership.objects.create(lab=lab_b, user=bob, role=LabRole.PI)
    LabMembership.objects.create(lab=lab_b, user=seed, role=LabRole.MEMBER)
    Project.objects.create(lab=lab_a, name="Secret Project Title", created_by=ada)
    audit.record(AuditAction.AUTH_LOGIN, actor=ada, lab=None)
    audit.record(AuditAction.AUTH_LOGIN, actor=bob, lab=None)
    audit.record(AuditAction.AUTH_LOGIN, actor=seed, lab=None)
    audit.record(AuditAction.MEMBERSHIP_INVITED, actor=ada, lab=lab_a)
    audit.record(
        AuditAction.INTEGRATION_CONNECTED, actor=bob, lab=lab_b, metadata={"provider": "zotero"}
    )
    LabChatMessage.objects.create(lab=lab_b, author=bob, body="secret chat text")
    LabChatMessage.objects.create(lab=lab_b, author=seed, body="seed chat text")
    convo = Conversation.objects.create(
        user=cy, lab=lab_a, provider="anthropic", model="m", system_prompt="-"
    )
    Message.objects.create(conversation=convo, seq=1, role=Role.USER, content=[{"t": "secret"}])
    return {"staff": staff, "ada": ada, "bob": bob, "cy": cy, "seed": seed, "lab_a": lab_a}


@pytest.mark.django_db
def test_only_active_staff_see_it(world):
    assert get(None).status_code == 401
    assert get(world["ada"]).status_code == 404  # a PI of a lab
    plain = person("plain@usage.example")
    assert get(plain).status_code == 404
    superuser_flag_only = person("su@usage.example", is_superuser=True)
    assert get(superuser_flag_only).status_code == 404
    gone = person("gone@usage.example", is_staff=True, is_active=False)
    assert get(gone).status_code == 404  # even with a session still held
    assert get(world["staff"]).status_code == 200


@pytest.mark.django_db
def test_counts_across_labs_without_test_accounts(world):
    data = get(world["staff"]).json()
    h = data["headline"]
    # founder, ada, bob, cy; the seed account is left out
    assert h["total_users"] == 4
    assert h["new_users"] == 4
    assert h["active_users"] == 3  # ada and bob signed in; cy asked the assistant
    assert h["labs_total"] == 2 and h["labs_new"] == 2
    assert h["projects_total"] == 1
    assert h["dau"] == h["wau"] == h["mau"] == 3
    today = data["daily"][-1]
    assert len(data["daily"]) == 30
    assert today["signups"] == 4 and today["sign_ins"] == 2 and today["active_users"] == 3
    funnel = {s["key"]: (s["count"], s["percent"]) for s in data["funnel"]}
    assert funnel == {
        "signed_up": (4, 100),
        "in_lab": (2, 50),
        "project": (1, 25),
        "invited": (1, 25),
        "came_back": (0, 0),
    }
    features = {f["feature"]: (f["events"], f["users"]) for f in data["features"]}
    assert features["Lab chat messages"] == (1, 1)
    assert features["AI assistant (questions asked)"] == (1, 1)
    assert features["Invites and members"] == (1, 1)
    assert features["Integrations and Google Chat"] == (1, 1)
    assert features["Tasks"] == (0, 0)
    assert data["integrations"] == [{"provider": "zotero", "connections": 1, "users": 1}]
    rows = {r["email"]: r for r in data["recent_signups"]}
    assert set(rows) == {
        "founder@usage.example",
        "ada@usage.example",
        "bob@usage.example",
        "cy@usage.example",
    }
    assert rows["ada@usage.example"]["institution"] == "Usage University"
    assert rows["ada@usage.example"]["labs"] == 1
    assert rows["ada@usage.example"]["events"] == 2  # sign-in and invite
    assert rows["bob@usage.example"]["events"] == 3  # sign-in, connect, chat message
    assert rows["founder@usage.example"]["last_active"] is None
    assert rows["cy@usage.example"]["last_active"] == str(timezone.now().date())
    assert len(data["retention"]) == 8 and data["retention"][-1]["users"] == 4
    assert data["retention"][-1]["weeks"] == []
    body = str(data)
    for secret in ("Secret Lab Name", "Secret Project Title", "secret chat", "seed chat"):
        assert secret not in body


@pytest.mark.django_db
def test_include_test_and_window(world):
    data = get(world["staff"], "?include_test=1&days=7").json()
    assert data["include_test"] is True and len(data["daily"]) == 7
    assert data["headline"]["total_users"] == 5
    assert data["headline"]["active_users"] == 4
    features = {f["feature"]: f["events"] for f in data["features"]}
    assert features["Lab chat messages"] == 2


@pytest.mark.django_db
def test_window_and_came_back(world):
    ada = world["ada"]
    User.objects.filter(pk=ada.pk).update(date_joined=timezone.now() - timedelta(days=10))
    data = get(world["staff"], "?days=7").json()
    assert data["headline"]["new_users"] == 3  # ada joined before the window
    data = get(world["staff"], "?days=30").json()
    funnel = {s["key"]: s["count"] for s in data["funnel"]}
    assert funnel["came_back"] == 1  # ada joined 10 days ago and signed in today


@pytest.mark.django_db
def test_bad_window_is_400(world):
    assert get(world["staff"], "?days=365").status_code == 400


@pytest.mark.django_db
def test_me_says_who_is_staff_and_cannot_be_changed(world):
    client = APIClient()
    client.force_authenticate(world["ada"])
    assert client.get("/api/me/").json()["site_staff"] is False
    client.patch("/api/me/", {"site_staff": True, "is_staff": True}, format="json")
    world["ada"].refresh_from_db()
    assert world["ada"].is_staff is False
    client.force_authenticate(world["staff"])
    assert client.get("/api/me/").json()["site_staff"] is True


def test_url_is_named():
    assert reverse("core:usage") == URL
