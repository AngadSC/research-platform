"""Permission matrix (ARCHITECTURE section 6, D32, D36). Gates every phase.

To add an endpoint in a later phase: add its model to `build_world` (for Lab A and Lab B),
its URL kwargs to `build_world().a` / `.b`, a `PAYLOADS` entry for each write method, and one
hand-written `MATRIX` row. The expected codes are never derived from the code or the role tables.
"""

from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APIClient

from core.models import Institution, User
from labs.models import Invite, Lab, LabMembership, LabRole
from projects.models import Project, ProjectMembership, ProjectRole

# Fixed order. Lab roles: outsider is the PI of Lab B and not in Lab A; pi, admin (lab_admin),
# lead, contrib, pviewer and nonproj (members); lviewer is a lab viewer. Project roles on P1:
# lead, contrib, pviewer; nonproj has none; lviewer is a contributor, capped to viewer (D19).
PERSONAS = ["anon", "outsider", "pi", "admin", "lead", "contrib", "pviewer", "nonproj", "lviewer"]

# Each exemption needs a reason.
EXEMPT_PREFIXES = [
    "/_allauth/",  # allauth headless: its own views, covered by core/tests/test_auth.py
    "/admin/",  # Django admin: staff only, not part of the API
]

# fmt: off
MATRIX: dict[tuple[str, str], str] = {
    #                                    anon outsider pi admin lead contrib pviewer nonproj lviewer
    ("GET",    "core:health"):           "2   2        2  2     2    2       2       2       2",
    ("GET",    "core:me"):               "401 2        2  2     2    2       2       2       2",
    ("PATCH",  "core:me"):               "401 2        2  2     2    2       2       2       2",
    ("GET",    "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("POST",   "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("GET",    "labs:lab-detail"):       "401 404      2  2     2    2       2       2       2",
    ("PATCH",  "labs:lab-detail"):       "401 404      2  2     403  403     403     403     403",
    ("GET",    "labs:member-list"):      "401 404      2  2     2    2       2       2       2",
    ("PATCH",  "labs:member-detail"):    "401 404      2  2     403  403     403     403     403",
    ("DELETE", "labs:member-detail"):    "401 404      2  2     403  403     403     403     403",
    ("GET",    "labs:invite-list"):      "401 404      2  2     403  403     403     403     403",
    ("POST",   "labs:invite-list"):      "401 404      2  2     403  403     403     403     403",
    ("DELETE", "labs:invite-detail"):    "401 404      2  2     403  403     403     403     403",
    ("GET",    "audit:audit-event-list"): "401 404      2  2     403  403     403     403     403",
    ("POST",   "labs:invite-preview"):   "2   2        2  2     2    2       2       2       2",
    ("POST",   "labs:invite-accept"):    "401 2        2  2     2    2       2       2       2",
}
# fmt: on


# ---------------------------------------------------------------- world

_n = iter(range(10**6))


def _user(name):
    user = User.objects.create(email=f"{name}@example.com", display_name=name)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def build_world():
    """Two labs, each with a project, a membership and a pending invite. Add each new
    lab-data model here, once for A and once for B."""
    inst, _ = Institution.objects.get_or_create(name="Matrix Institution")
    users = {name: _user(name) for name in PERSONAS if name != "anon"}
    lab_roles = {
        "pi": LabRole.PI,
        "admin": LabRole.LAB_ADMIN,
        "lead": LabRole.MEMBER,
        "contrib": LabRole.MEMBER,
        "pviewer": LabRole.MEMBER,
        "nonproj": LabRole.MEMBER,
        "lviewer": LabRole.VIEWER,
    }
    lab_a = Lab.objects.create(institution=inst, name="Lab A", created_by=users["pi"])
    memberships = {
        n: LabMembership.objects.create(lab=lab_a, user=users[n], role=r)
        for n, r in lab_roles.items()
    }
    p1 = Project.objects.create(lab=lab_a, name="P1", created_by=users["pi"])
    Project.objects.create(lab=lab_a, name="P2", created_by=users["pi"])  # nobody is on it
    for name, role in [
        ("lead", ProjectRole.LEAD),
        ("contrib", ProjectRole.CONTRIBUTOR),
        ("pviewer", ProjectRole.VIEWER),
        ("lviewer", ProjectRole.CONTRIBUTOR),
    ]:
        ProjectMembership.objects.create(lab=lab_a, project=p1, user=users[name], role=role)
    invite_a, _ = Invite.issue(
        lab=lab_a, email="invitee-a@example.com", role=LabRole.MEMBER, invited_by=users["pi"]
    )

    secret_pi = users["outsider"]
    lab_b = Lab.objects.create(institution=inst, name="Lab B Secret", created_by=secret_pi)
    membership_b = LabMembership.objects.create(lab=lab_b, user=secret_pi, role=LabRole.PI)
    Project.objects.create(lab=lab_b, name="P1 Secret", created_by=secret_pi)
    invite_b, _ = Invite.issue(
        lab=lab_b,
        email="invitee-b-secret@example.com",
        role=LabRole.MEMBER,
        invited_by=secret_pi,
    )
    return SimpleNamespace(
        user_ids={n: u.pk for n, u in users.items()},
        a={
            "lab_id": lab_a.pk,
            "membership_id": memberships["contrib"].pk,
            "invite_id": invite_a.pk,
        },
        b={"lab_id": lab_b.pk, "membership_id": membership_b.pk, "invite_id": invite_b.pk},
        b_names=["Lab B Secret", "P1 Secret", "invitee-b-secret@example.com"],
    )


@pytest.fixture(scope="session")
def world(django_db_setup, django_db_blocker):
    """Built once per session; each test runs in a rolled-back transaction on top of it."""
    with django_db_blocker.unblock():
        yield build_world()


def client_for(persona, w):
    client = APIClient()
    if persona != "anon":
        client.force_login(User.objects.get(pk=w.user_ids[persona]))
    return client


# ---------------------------------------------------------------- payloads


def _fresh_invite_for(email, w):
    """An invite in a brand-new lab, so accepting it is always valid for its addressee."""
    pi = User.objects.get(pk=w.user_ids["pi"])
    inst = Institution.objects.get(name="Matrix Institution")
    lab = Lab.objects.create(institution=inst, name=f"Fresh {next(_n)}", created_by=pi)
    _, token = Invite.issue(lab=lab, email=email, role=LabRole.MEMBER, invited_by=pi)
    return {"token": token}


# (persona user or None, world) -> a valid request body, so an allowed call returns 2xx.
PAYLOADS = {
    ("PATCH", "core:me"): lambda user, w: {"display_name": "New Name"},
    ("POST", "labs:lab-list"): lambda user, w: {"name": "Brand New Lab"},
    ("PATCH", "labs:lab-detail"): lambda user, w: {"name": "Renamed Lab"},
    ("PATCH", "labs:member-detail"): lambda user, w: {"role": "viewer"},
    ("POST", "labs:invite-list"): lambda user, w: {
        "email": f"new{next(_n)}@example.com",
        "role": "member",
    },
    ("POST", "labs:invite-preview"): lambda user, w: _fresh_invite_for("someone@example.com", w),
    ("POST", "labs:invite-accept"): lambda user, w: _fresh_invite_for(
        user.email if user else "nobody@example.com", w
    ),
}


# ---------------------------------------------------------------- enumeration


def discover():
    """Walk the URL resolver: {(METHOD, url_name): (url kwarg names)}."""
    found = {}

    def walk(patterns, prefix, ns, kwargs):
        for p in patterns:
            route = prefix + str(p.pattern)
            if any(("/" + route).startswith(x) for x in EXEMPT_PREFIXES):
                continue
            if isinstance(p, URLResolver):
                sub_ns = ns + (p.namespace + ":" if p.namespace else "")
                walk(p.url_patterns, route, sub_ns, kwargs + tuple(p.pattern.converters))
                continue
            assert isinstance(p, URLPattern)
            cb = p.callback
            if hasattr(cb, "actions"):  # ViewSet
                methods = [m.upper() for m in cb.actions]
            else:
                cls = getattr(cb, "cls", None)
                assert cls is not None, f"{route}: not a DRF view; exempt it or convert it"
                methods = [
                    m.upper()
                    for m in cls.http_method_names
                    if m not in ("head", "options") and hasattr(cls, m)
                ]
            assert p.name, f"{route}: URL has no name"
            for m in methods:
                found[(m, ns + p.name)] = kwargs + tuple(p.pattern.converters)

    walk(get_resolver().url_patterns, "", "", ())
    return found


def test_every_endpoint_has_a_matrix_row():
    missing = sorted(discover().keys() - MATRIX.keys())
    assert not missing, f"endpoints with no MATRIX row: {missing}"


def test_no_stale_matrix_rows():
    stale = sorted(MATRIX.keys() - discover().keys())
    assert not stale, f"MATRIX rows with no endpoint: {stale}"


def test_matrix_rows_are_well_formed():
    for key, row in MATRIX.items():
        tokens = row.split()
        assert len(tokens) == len(PERSONAS), key
        assert set(tokens) <= {"2", "401", "403", "404"}, key
        assert tokens[0] in {"2", "401"}, f"anon can only succeed or get 401: {key}"
        method, name = key
        if method in {"POST", "PATCH", "PUT"} and name != "core:health":
            assert key in PAYLOADS, f"no payload for {key}"


# ---------------------------------------------------------------- the matrix

CASES = [
    (method, name, persona, expected)
    for (method, name), row in MATRIX.items()
    for persona, expected in zip(PERSONAS, row.split(), strict=True)
]


def _request(client, method, url, payload):
    if method in {"POST", "PATCH", "PUT"}:
        return getattr(client, method.lower())(url, payload or {}, format="json")
    return getattr(client, method.lower())(url)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "name", "persona", "expected"),
    CASES,
    ids=[f"{m} {n} {p}" for m, n, p, _ in CASES],
)
def test_matrix(world, method, name, persona, expected):
    user = None if persona == "anon" else User.objects.get(pk=world.user_ids[persona])
    kwargs = {k: world.a[k] for k in discover()[(method, name)]}
    payload = PAYLOADS[(method, name)](user, world) if (method, name) in PAYLOADS else None
    response = _request(client_for(persona, world), method, reverse(name, kwargs=kwargs), payload)
    if expected == "2":
        assert 200 <= response.status_code < 300, (response.status_code, response.content)
    else:
        assert response.status_code == int(expected), (response.status_code, response.content)


# ---------------------------------------------------------------- cross-lab ID swap


# Not resolved at import: urls must load after pytest-django turns DEBUG off (no schema URL).
@pytest.mark.django_db
@pytest.mark.parametrize(("method", "name"), list(MATRIX), ids=[f"{m} {n}" for m, n in MATRIX])
def test_cross_lab_id_swap_is_404(world, method, name):
    """Acting as Lab A's PI: A's lab_id with B's object ID, and B's lab_id with A's object ID,
    both 404, and neither response leaks anything from Lab B."""
    if len(discover()[(method, name)]) < 2:
        pytest.skip("no object ID in the URL")
    pi = User.objects.get(pk=world.user_ids["pi"])
    client = client_for("pi", world)
    payload = PAYLOADS[(method, name)](pi, world) if (method, name) in PAYLOADS else None
    for lab_side, obj_side in [(world.a, world.b), (world.b, world.a)]:
        kwargs = {k: obj_side[k] for k in discover()[(method, name)]}
        kwargs["lab_id"] = lab_side["lab_id"]
        response = _request(client, method, reverse(name, kwargs=kwargs), payload)
        assert response.status_code == 404, (kwargs, response.status_code, response.content)
        body = response.content.decode()
        assert not any(secret in body for secret in world.b_names)


@pytest.mark.django_db
def test_options_on_lab_url_is_404_for_outsiders(world):
    url = reverse("labs:lab-detail", kwargs={"lab_id": world.a["lab_id"]})
    assert client_for("outsider", world).options(url).status_code == 404
    assert client_for("anon", world).options(url).status_code == 401
