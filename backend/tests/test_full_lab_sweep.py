"""Whole app at full-lab scale: 20 people, 9 projects, a year of data (seed_full_lab).

Every GET endpoint the permission matrix knows is called as eight kinds of person. We check:
no 5xx, nobody sees more than the matrix allows, a query budget (N+1 shapes) and speed.
The slowest and most-queried endpoints are printed (run with -s). A few write smokes at the end.
"""

import time
import traceback
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

# the matrix test module is importable by bare name (no tests/__init__.py)
from test_permission_matrix import MATRIX, PERSONAS, discover, matrix_lab_files  # noqa: F401

from core.models import Institution, User
from core.seed_full import people
from labs.models import Lab, LabMembership, LabRole
from labs.services import create_lab
from projects import services as project_services
from projects.models import ProjectRole

QUERY_BUDGET = 60
# Known heavy: the list re-checks every notification's target one row at a time (D54), about two
# queries a row, up to its 100-row limit. Batch the target lookups to bring this under budget.
KNOWN_HEAVY = {"core:notification-list": 220}
SECONDS_BUDGET = 5.0
PW = "sweep-pw-not-secret"

# Calls that leave the box (Google, DOI lookups, link previews, OAuth): not a lab-size question.
EXTERNAL = {
    "labs:link-preview",
    "papers:doi-lookup",
    "papers:zotero-import",
    "integrations:oauth-callback",
    "integrations:picker-token",
    "integrations:item-search",
    "labs:calendar-google",
    "labs:calendar-google-events",
    "labs:calendar-video-options",
    "labs:google-chat",
    "labs:google-chat-people",
    "labs:google-chat-spaces",
    "labs:google-chat-threads",
    "projects:project-google-chat",
    "projects:project-google-chat-people",
    "projects:project-google-chat-spaces",
    "projects:project-google-chat-threads",
    "core:weather",
    "assistant:file-link",
    "labs:calendar-ics",  # needs a feed token, not a login
}
# kwarg stem -> model name where the two differ
ALIASES = {"comment": "documentcomment", "ethics_attachment": "ethicsattachment"}

# label -> (people key or fresh user, project key, matrix persona column)
WHO = {
    "outsider": ("outsider", "sleep", "outsider"),
    "pi": ("pi", "sleep", "pi"),
    "manager": ("manager", "sleep", "admin"),
    "lead": ("priya", "sleep", "lead"),
    "contrib": ("grace", "sleep", "contrib"),
    "pviewer": ("pviewer", "sleep", "pviewer"),
    "nonproj": ("nonproj", "sleep", "nonproj"),
    "lviewer": ("owen", "fmri", "lviewer"),  # lab viewer who is on this project
    "lviewer_off": ("owen", "sleep", "lviewer"),  # same person, a project they are not on
}


def _model(stem):
    want = ALIASES.get(stem, stem).replace("_", "")
    for m in apps.get_models():
        if m._meta.model_name == want:
            return m
    return None


def _base(model, lab):
    mgr = model._default_manager
    return mgr.for_lab(lab) if hasattr(mgr, "for_lab") else mgr.all()


def _resolve(kwarg, lab, project, got, ctx):
    """A real value for one URL kwarg, from the seeded data. None if it can't be filled."""
    if kwarg == "lab_id":
        return lab.pk
    if kwarg == "project_id":
        return project.pk
    if kwarg == "version":
        return 1
    if kwarg == "ai_provider":
        return "anthropic"
    if kwarg == "provider":
        from integrations.models import ConnectedAccount

        acct = ConnectedAccount.objects.for_lab(lab).first()
        return acct.provider if acct else "google_drive"
    if kwarg == "user_id":
        return ctx.people["priya"].pk
    if not kwarg.endswith("_id"):
        return None
    model = _model(kwarg[:-3])
    if model is None:
        return None
    qs = _base(model, lab)
    names = {f.name for f in model._meta.fields}
    if "project" in names:
        qs = qs.filter(project=project)
    if model._meta.label_lower == "training.trainingrecord":  # someone else's, as in the matrix
        qs = qs.filter(user=ctx.people["ben"])
    for obj in got.values():
        for f in model._meta.fields:
            if f.is_relation and f.related_model is type(obj):
                qs = qs.filter(**{f.name: obj})
                break
    row = qs.order_by("pk").first()
    if row is None:  # nothing in this project: any in the lab (still fine for 5xx/budget checks)
        row = _base(model, lab).order_by("pk").first()
    return row.pk if row else None


def _kwargs(names, lab, project, ctx):
    got, out = {}, {}
    for k in names:
        # in order, so later kwargs are narrowed by earlier ones (task, then its post)
        v = _resolve(k, lab, project, got, ctx)
        if v is None:
            return None, k
        out[k] = v
        model = _model(k[:-3]) if k.endswith("_id") else None
        if model is not None and k not in ("lab_id", "project_id"):
            got[k] = _base(model, lab).filter(pk=v).first() or object()
    return out, None


def _params(name, lab):
    return {
        "core:search": {"q": "sleep"},
        "core:page-comment-list": {"path": f"/labs/{lab.pk}/calendar"},
        "labs:calendar": {"from": "2026-11-01", "to": "2026-11-30"},
    }.get(name, {})


@pytest.fixture(scope="module")
def sweep(django_db_setup, django_db_blocker, matrix_lab_files):  # noqa: F811
    with (
        django_db_blocker.unblock(),
        override_settings(
            DEBUG=True,
            ALLOWED_HOSTS=["*"],
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
            CELERY_TASK_ALWAYS_EAGER=True,
        ),
        transaction.atomic(),
    ):
        # Rolled back at the end, so no other test module sees this lab.
        yield _build_and_sweep()
        transaction.set_rollback(True)


def _build_and_sweep():
    call_command("seed_full_lab", stdout=open("/dev/null", "w"))  # noqa: SIM115
    lab = Lab.objects.get(name=people.LAB_NAME)
    ctx = SimpleNamespace(
        lab=lab,
        people={k: User.objects.get(email=people.email(k)) for k in people.PEOPLE},
        projects={},
    )
    from projects.models import Project

    for key, spec in people.PROJECTS.items():
        ctx.projects[key] = Project.objects.for_lab(lab).get(name=spec[0])

    def fresh(name):
        u = User.objects.create_user(email=f"sweep-{name}@example.test", password=PW)
        return u

    nonproj, pviewer, outsider = fresh("nonproj"), fresh("pviewer"), fresh("outsider")
    for u in (nonproj, pviewer):
        LabMembership.objects.create(lab=lab, user=u, role=LabRole.MEMBER)
    project_services.add_member(
        project=ctx.projects["sleep"],
        by=ctx.people["priya"],
        user_id=pviewer.pk,
        role=ProjectRole.VIEWER,
    )
    Institution.objects.get_or_create(name="Sweep Institution")
    create_lab(user=outsider, name="Small Other Lab (FAKE)")
    ctx.people.update(nonproj=nonproj, pviewer=pviewer, outsider=outsider)

    endpoints = sorted(
        (m, n, ks) for (m, n), ks in discover().items() if m == "GET" and (m, n) in MATRIX
    )  # DEBUG adds the schema URL
    records, skipped = [], {}
    for label, (who, pkey, col) in WHO.items():
        client = APIClient()
        client.force_login(ctx.people[who])
        _run(client, label, col, ctx.projects[pkey], lab, endpoints, ctx, records, skipped)
    # the PI against every project (statuses: planning, paused, completed, archived too)
    client = APIClient()
    client.force_login(ctx.people["pi"])
    for pkey, project in ctx.projects.items():
        _run(client, f"pi@{pkey}", "pi", project, lab, endpoints, ctx, records, skipped)
    return SimpleNamespace(records=records, skipped=skipped, ctx=ctx, n_endpoints=len(endpoints))


def _run(client, label, col, project, lab, endpoints, ctx, records, skipped):
    for _m, name, names in endpoints:
        if name in EXTERNAL:
            skipped[name] = "external call"
            continue
        kwargs, missing = _kwargs(names, lab, project, ctx)
        if kwargs is None:
            skipped[name] = f"cannot fill {missing}"
            continue
        url = reverse(name, kwargs=kwargs)
        err = None
        t0 = time.perf_counter()
        connection.queries_log.clear()  # it keeps only the last 9000
        with CaptureQueriesContext(connection) as q:
            try:
                status = client.get(url, _params(name, lab)).status_code
            except Exception:  # noqa: BLE001 (the point is to catch any crash)
                status = 500
                err = "".join(traceback.format_exc().splitlines(True)[-6:])
        records.append(
            SimpleNamespace(
                label=label,
                col=col,
                name=name,
                status=status,
                queries=len(q),
                ms=(time.perf_counter() - t0) * 1000,
                err=err,
                has_project="project_id" in names,
                url=url,
            )
        )


def _expected(rec):
    """The matrix's word for this endpoint and person: '2' or a status code."""
    col = "nonproj" if rec.label == "lviewer_off" and rec.has_project else rec.col
    return MATRIX[("GET", rec.name)].split()[PERSONAS.index(col)]


def _ok(status):
    return 200 <= status < 300


def test_no_server_errors(sweep):
    bad = [r for r in sweep.records if r.status >= 500]
    assert not bad, "\n".join(f"{r.label} GET {r.name} {r.url} -> {r.status}\n{r.err}" for r in bad)


def test_nobody_sees_more_than_the_matrix_allows(sweep):
    leaks = [r for r in sweep.records if _expected(r) != "2" and _ok(r.status)]
    assert not leaks, "\n".join(
        f"{r.label} GET {r.name} -> {r.status}, matrix says {_expected(r)}" for r in leaks
    )


def test_outsider_gets_nothing_of_this_lab(sweep):
    # only endpoints about the person themselves (matrix says 2 for the outsider) may answer
    own = {n for (_m, n), row in MATRIX.items() if row.split()[1] == "2"}
    leaks = [
        r for r in sweep.records if r.label == "outsider" and _ok(r.status) and r.name not in own
    ]
    assert not leaks, [(r.name, r.status) for r in leaks]


def test_wrongly_refused_is_reported(sweep, capsys):
    """Not a failure: matrix says allowed, got 4xx. Usually a data pick, sometimes a real bug."""
    odd = sorted(
        {
            (r.label, r.name, r.status)
            for r in sweep.records
            if _expected(r) == "2"
            and not _ok(r.status)
            and not r.label.startswith("pi@")
            and r.label != "lviewer_off"
        }
    )
    with capsys.disabled():
        print(f"\nREFUSED BUT MATRIX SAYS ALLOWED ({len(odd)}):")
        for row in odd:
            print("  ", *row)


def test_query_budget_and_speed(sweep, capsys):
    recs = [r for r in sweep.records if _ok(r.status)]
    with capsys.disabled():
        print(
            f"\nCOVERED {len({r.name for r in sweep.records})} of {sweep.n_endpoints} GET endpoints"
        )
        print("SKIPPED:", dict(sorted(sweep.skipped.items())))
        print(f"\nTOP 25 BY QUERIES (of {len(recs)} OK calls)")
        for r in sorted(recs, key=lambda r: -r.queries)[:25]:
            print(f"  {r.queries:4d} q {r.ms:7.0f} ms  {r.label:12} {r.name}")
        print("\nTOP 25 BY TIME")
        for r in sorted(recs, key=lambda r: -r.ms)[:25]:
            print(f"  {r.ms:7.0f} ms {r.queries:4d} q  {r.label:12} {r.name}")
    over = [
        r
        for r in recs
        if r.queries > KNOWN_HEAVY.get(r.name, QUERY_BUDGET) or r.ms > SECONDS_BUDGET * 1000
    ]
    assert not over, "\n".join(f"{r.label} {r.name}: {r.queries} q, {r.ms:.0f} ms" for r in over)


def test_dashboard_and_search_per_role(sweep):
    by = {(r.label, r.name): r.status for r in sweep.records}
    for who in ("pi", "manager"):
        assert by[(who, "labs:dashboard")] == 200
    for who in ("lead", "contrib", "pviewer", "nonproj", "lviewer"):
        assert by[(who, "labs:dashboard")] == 403
    for who in ("pi", "manager", "lead", "contrib", "pviewer", "nonproj", "lviewer"):
        assert by[(who, "core:search")] == 200


# ------------------------------------------------------------------ writes


def _client(sweep, key):
    c = APIClient()
    c.force_login(sweep.ctx.people[key])
    return c


def _urls(sweep, project):
    kw = {"lab_id": sweep.ctx.lab.pk, "project_id": sweep.ctx.projects[project].pk}
    return {
        "task": reverse("projects:task-list", kwargs=kw),
        "chat": reverse("projects:chatmessage-list", kwargs=kw),
        "doc": reverse("documents:document-list", kwargs=kw),
    }


BODIES = {
    "task": {"title": "Sweep task"},
    "chat": {"body": "Sweep hello"},
    "doc": {"title": "Sweep doc", "content": [{"type": "paragraph"}]},
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("who", "project", "task", "chat", "doc"),
    [
        ("grace", "sleep", True, True, True),  # contributor
        ("priya", "sleep", True, True, True),  # lead
        ("pviewer", "sleep", False, True, False),  # project viewer: chat only (matrix)
        ("owen", "fmri", False, True, False),  # lab viewer: chat only (matrix)
        ("nonproj", "sleep", False, False, False),  # not on the project at all
    ],
)
def test_write_smoke(sweep, who, project, task, chat, doc):
    c, urls = _client(sweep, who), _urls(sweep, project)
    for kind, allowed in (("task", task), ("chat", chat), ("doc", doc)):
        res = c.post(urls[kind], BODIES[kind], format="json")
        if allowed:
            assert res.status_code == 201, (who, kind, res.status_code, res.content[:200])
        else:
            assert res.status_code in (403, 404), (who, kind, res.status_code)
