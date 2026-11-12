import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.tenancy import CrossLabError
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole
from provenance.models import Analysis, DatasetRecord

pytestmark = pytest.mark.django_db

CODE = {"code_repo_url": "https://example.com/r.git", "code_commit": "abc1234"}


class World:
    def __init__(self, make_lab, make_user, make_project, join):
        self.lab = make_lab("Lab A")
        self.pi = make_user()
        join(self.pi, self.lab, LabRole.PI)
        self.project = make_project(self.lab, "P1")
        self.other = make_project(self.lab, "P2")  # same lab, different project
        self.lab_b = make_lab("Lab B")
        self.pi_b = make_user()
        join(self.pi_b, self.lab_b, LabRole.PI)
        self.project_b = make_project(self.lab_b, "PB")
        self.make_user, self.join = make_user, join

    def client(self, user=None):
        client = APIClient()
        client.force_login(user or self.pi)
        return client

    def member(self, role):
        user = self.make_user()
        self.join(user, self.lab, LabRole.MEMBER)
        ProjectMembership.objects.create(lab=self.lab, project=self.project, user=user, role=role)
        return user

    def url(self, name, project=None, **kw):
        kwargs = {"lab_id": self.lab.pk, **kw}
        if name.rsplit("-", 1)[-1] == "list" or name in ("lineage", "export"):
            kwargs["project_id"] = (project or self.project).pk
        return reverse(f"provenance:{name}", kwargs=kwargs)

    def post(self, name, body, project=None, user=None):
        return self.client(user).post(self.url(name, project), body, format="json")

    def make(self, name, body, project=None):
        resp = self.post(name, body, project)
        assert resp.status_code == 201, resp.content
        return resp.json()["id"]


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    return World(make_lab, make_user, make_project, join)


def chain(w, project=None):
    """dataset v1 -> v2, analysis, result, manuscript, decision, all linked."""
    ds1 = w.make("dataset-list", {"name": "D", "version_label": "v1"}, project)
    ds2 = w.make(
        "dataset-list",
        {
            "name": "D",
            "version_label": "v2",
            "previous_version": ds1,
            "checksum": "sha256:" + "a" * 64,
        },
        project,
    )
    an = w.make("analysis-list", {"title": "A", "datasets": [ds2], **CODE}, project)
    res = w.make("result-list", {"title": "R", "analysis": an}, project)
    ms = w.make(
        "manuscript-list", {"title": "M", "url": "https://x.org/m", "results": [res]}, project
    )
    dec = w.make(
        "decision-list",
        {"title": "Dec", "analyses": [an], "datasets": [ds2], "results": [res]},
        project,
    )
    return {"ds1": ds1, "ds2": ds2, "an": an, "res": res, "ms": ms, "dec": dec}


# ---------------------------------------------------------------- links stay in one project / lab


def test_cross_project_link_is_rejected(w):
    foreign = chain(w, w.other)
    cases = [
        ("analysis-list", {"title": "A", "datasets": [foreign["ds1"]], **CODE}),
        ("result-list", {"title": "R", "analysis": foreign["an"]}),
        ("manuscript-list", {"title": "M", "url": "https://x.org", "results": [foreign["res"]]}),
        ("decision-list", {"title": "D", "analyses": [foreign["an"]]}),
        ("dataset-list", {"name": "N", "version_label": "1", "previous_version": foreign["ds1"]}),
    ]
    for name, body in cases:
        resp = w.post(name, body)
        assert resp.status_code == 400, (name, resp.content)
    # and on update
    mine = chain(w)
    resp = w.client().patch(
        w.url("analysis-detail", analysis_id=mine["an"]),
        {"datasets": [foreign["ds1"]]},
        format="json",
    )
    assert resp.status_code == 400
    assert Analysis.objects.for_lab(w.lab).get(pk=mine["an"]).datasets.count() == 1


def test_cross_lab_link_is_rejected(w):
    # Lab B's pi builds a dataset; Lab A references its ID.
    client_b = APIClient()
    client_b.force_login(w.pi_b)
    url = reverse(
        "provenance:dataset-list", kwargs={"lab_id": w.lab_b.pk, "project_id": w.project_b.pk}
    )
    foreign = client_b.post(url, {"name": "Secret", "version_label": "1"}, format="json").json()[
        "id"
    ]
    resp = w.post("analysis-list", {"title": "A", "datasets": [foreign], **CODE})
    assert resp.status_code == 400 and "Secret" not in resp.content.decode()
    resp = w.post("dataset-list", {"name": "N", "version_label": "1", "previous_version": foreign})
    assert resp.status_code == 400


def test_model_layer_rejects_cross_project_and_cross_lab(w):
    """Defence in depth under the services: `save()` and the m2m_changed receiver (D31)."""
    mine = DatasetRecord.objects.create(
        lab=w.lab, project=w.project, name="a", version_label="1", created_by=w.pi
    )
    other_project = DatasetRecord.objects.create(
        lab=w.lab, project=w.other, name="a", version_label="1", created_by=w.pi
    )
    other_lab = DatasetRecord.objects.create(
        lab=w.lab_b, project=w.project_b, name="a", version_label="1", created_by=w.pi_b
    )
    analysis = Analysis.objects.create(
        lab=w.lab, project=w.project, title="t", ran_by=w.pi, ran_at="2030-01-01T00:00:00Z", **CODE
    )
    analysis.datasets.add(mine)
    for bad in (other_project, other_lab):
        with pytest.raises(CrossLabError), transaction.atomic():
            analysis.datasets.add(bad)
        with pytest.raises(CrossLabError), transaction.atomic():
            bad.analyses.add(analysis)
        with pytest.raises(CrossLabError), transaction.atomic():
            DatasetRecord(
                lab=w.lab,
                project=w.project,
                name="b",
                version_label="1",
                created_by=w.pi,
                previous_version=bad,
            ).save()


@pytest.mark.parametrize(
    ("name", "body"),
    [
        (
            "dataset-list",
            {"name": "N", "version_label": "1", "location_url": "javascript:alert(1)"},
        ),
        (
            "analysis-list",
            {"title": "A", "code_commit": "abc1234", "code_repo_url": "javascript:alert(1)"},
        ),
        ("manuscript-list", {"title": "M", "url": "javascript:alert(1)"}),
        ("manuscript-list", {"title": "M", "url": "ftp://example.com/x"}),
        (
            "decision-list",
            {"title": "D", "references": [{"title": "t", "url": "javascript:alert(1)"}]},
        ),
    ],
)
def test_non_web_url_is_rejected(w, name, body):
    assert w.post(name, body).status_code == 400


def test_model_validator_rejects_javascript_url():
    from django.core.exceptions import ValidationError

    from provenance.models import validate_web_url

    with pytest.raises(ValidationError):
        validate_web_url("javascript:alert(1)")
    validate_web_url("https://example.com")


# ---------------------------------------------------------------- behaviour


def test_analysis_needs_a_code_reference(w):
    assert w.post("analysis-list", {"title": "A"}).status_code == 400
    assert (
        w.post("analysis-list", {"title": "A", "code_repo_url": CODE["code_repo_url"]}).status_code
        == 400
    )


def test_new_dataset_version_is_a_new_row_and_names_are_unique(w):
    ids = chain(w)
    assert DatasetRecord.objects.for_lab(w.lab).filter(project=w.project).count() == 2
    assert w.post("dataset-list", {"name": "D", "version_label": "v1"}).status_code == 400
    body = w.client().get(w.url("dataset-detail", datasetrecord_id=ids["ds2"])).json()
    assert body["previous_version"] == {"id": ids["ds1"], "name": "D", "version_label": "v1"}
    assert [a["title"] for a in body["analyses"]] == ["A"]


def test_delete_conflicts(w):
    ids = chain(w)
    c = w.client()
    assert c.delete(w.url("dataset-detail", datasetrecord_id=ids["ds2"])).status_code == 409
    assert c.delete(w.url("analysis-detail", analysis_id=ids["an"])).status_code == 409
    assert c.delete(w.url("manuscript-detail", manuscriptlink_id=ids["ms"])).status_code == 204
    assert c.delete(w.url("decision-detail", decision_id=ids["dec"])).status_code == 204
    assert c.delete(w.url("result-detail", result_id=ids["res"])).status_code == 204
    assert c.delete(w.url("analysis-detail", analysis_id=ids["an"])).status_code == 204
    assert c.delete(w.url("dataset-detail", datasetrecord_id=ids["ds2"])).status_code == 204


def test_audit_events_for_create_update_delete(w):
    ds = w.make("dataset-list", {"name": "N", "version_label": "1"})
    url = w.url("dataset-detail", datasetrecord_id=ds)
    assert w.client().patch(url, {"access_notes": "x"}, format="json").status_code == 200
    assert w.client().delete(url).status_code == 204
    actions = list(
        AuditEvent.objects.filter(target_id=ds)
        .order_by("occurred_at")
        .values_list("action", flat=True)
    )
    assert actions == [
        AuditAction.DATASET_CREATED,
        AuditAction.DATASET_UPDATED,
        AuditAction.DATASET_DELETED,
    ]


# ---------------------------------------------------------------- lineage


def test_lineage_shape(w):
    ids = chain(w)
    data = w.client().get(w.url("lineage")).json()
    nodes = {n["href_id"]: n for n in data["nodes"]}
    assert set(nodes) == set(ids.values())
    assert {n["kind"] for n in data["nodes"]} == {
        "dataset",
        "analysis",
        "result",
        "manuscript",
        "decision",
    }
    for n in data["nodes"]:
        assert set(n) == {"id", "kind", "label", "subtitle", "href_id", "meta"}
    assert nodes[ids["ds2"]]["meta"]["version_label"] == "v2"
    assert nodes[ids["ds2"]]["meta"]["checksum"] == "sha256:" + "a" * 64
    assert nodes[ids["an"]]["meta"]["code_commit"] == "abc1234"
    assert nodes[ids["an"]]["meta"]["code_repo_url"] == CODE["code_repo_url"]
    assert nodes[ids["ms"]]["meta"]["status"] == "drafting"
    pairs = {(e["source"], e["target"], e["kind"]) for e in data["edges"]}
    ref = lambda k: nodes[ids[k]]["id"]  # noqa: E731
    assert pairs == {
        (ref("ds1"), ref("ds2"), "dataset"),
        (ref("ds2"), ref("an"), "dataset"),
        (ref("an"), ref("res"), "analysis"),
        (ref("res"), ref("ms"), "result"),
        (ref("dec"), ref("an"), "decision"),
        (ref("dec"), ref("ds2"), "decision"),
        (ref("dec"), ref("res"), "decision"),
    }
    assert all(e["id"] for e in data["edges"])


def test_lineage_query_count_is_constant(w, django_assert_max_num_queries):
    url = w.url("lineage")
    client = w.client()

    def count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx)

    chain(w)
    small = count()
    for i in range(5):
        ds = w.make("dataset-list", {"name": f"X{i}", "version_label": "1"})
        an = w.make("analysis-list", {"title": f"A{i}", "datasets": [ds], **CODE})
        res = w.make("result-list", {"title": f"R{i}", "analysis": an})
        w.make("manuscript-list", {"title": f"M{i}", "url": "https://x.org", "results": [res]})
        w.make("decision-list", {"title": f"D{i}", "analyses": [an], "results": [res]})
    assert count() == small
    with django_assert_max_num_queries(20):
        client.get(url)


def test_list_query_count_is_constant(w):
    client = w.client()

    def count(name):
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(w.url(name)).status_code == 200
        return len(ctx)

    chain(w)
    before = {
        n: count(n)
        for n in (
            "dataset-list",
            "analysis-list",
            "result-list",
            "decision-list",
            "manuscript-list",
        )
    }
    for i in range(4):
        ds = w.make("dataset-list", {"name": f"X{i}", "version_label": "1"})
        an = w.make("analysis-list", {"title": f"A{i}", "datasets": [ds], **CODE})
        res = w.make("result-list", {"title": f"R{i}", "analysis": an})
        w.make("manuscript-list", {"title": f"M{i}", "url": "https://x.org", "results": [res]})
        w.make("decision-list", {"title": f"D{i}", "analyses": [an], "results": [res]})
    assert {n: count(n) for n in before} == before


def test_lineage_of_invisible_project_is_404(w):
    chain(w)
    outsider = w.make_user()
    w.join(outsider, w.lab, LabRole.MEMBER)  # in the lab, not on the project
    assert w.client(outsider).get(w.url("lineage")).status_code == 404
    assert w.client(w.pi_b).get(w.url("lineage")).status_code == 404  # another lab
    assert w.client(w.member(ProjectRole.VIEWER)).get(w.url("lineage")).status_code == 200


# ---------------------------------------------------------------- export


def test_export_is_for_leads_not_contributors(w):
    chain(w)
    assert w.post("export", {}, user=w.member(ProjectRole.CONTRIBUTOR)).status_code == 403
    assert w.post("export", {}, user=w.member(ProjectRole.VIEWER)).status_code == 403
    resp = w.post("export", {}, user=w.member(ProjectRole.LEAD))
    assert resp.status_code == 200
    assert w.post("export", {}).status_code == 200  # pi: implicit lead


def test_export_contents_and_audit(w):
    ids = chain(w)
    w.client().post(
        reverse("documents:document-list", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk}),
        {"title": "Notes", "content": [{"type": "paragraph"}]},
        format="json",
    )
    resp = w.post("export", {})
    data = resp.json()
    assert data["project"]["name"] == "P1"
    assert {d["id"] for d in data["datasets"]} == {ids["ds1"], ids["ds2"]}
    assert [d["title"] for d in data["documents"]] == ["Notes"]
    assert data["documents"][0]["content"] == [{"type": "paragraph"}]
    assert {"tasks", "analyses", "results", "decisions", "manuscripts", "attachments"} <= set(data)
    event = AuditEvent.objects.get(action=AuditAction.PROJECT_EXPORTED)
    assert event.actor == w.pi and event.lab == w.lab and event.project_id == w.project.pk


def test_export_contains_no_other_project_data(w):
    chain(w)
    foreign = chain(w, w.other)
    secret_b = reverse(
        "provenance:dataset-list", kwargs={"lab_id": w.lab_b.pk, "project_id": w.project_b.pk}
    )
    b_client = APIClient()
    b_client.force_login(w.pi_b)
    b_client.post(secret_b, {"name": "LAB-B-SECRET", "version_label": "1"}, format="json")
    resp = w.post("export", {})
    body = resp.content.decode()
    for key in foreign.values():
        assert key not in body
    assert "LAB-B-SECRET" not in body
    assert "P2" not in body


# ---- D95: decision references


GOOD_REF = {"title": "Smith 2020", "url": "https://example.org/p", "doi": "10.1234/abc.5"}


@pytest.mark.parametrize(
    "refs",
    [
        [{"url": "https://example.org"}],  # title missing
        [{"title": "   "}],  # blank title
        [{"title": "t", "url": "ftp://example.org/x"}],
        [{"title": "t", "doi": "11.1234/abc"}],
        [{"title": "t", "doi": "10.12/abc"}],
        [{"title": "t", "doi": "10.1234/has space"}],
        [GOOD_REF] * 51,
    ],
)
def test_bad_references_are_rejected(w, refs):
    assert w.post("decision-list", {"title": "D", "references": refs}).status_code == 400


def test_references_are_saved_in_order_and_can_be_replaced(w):
    refs = [GOOD_REF, {"title": "No link"}]
    r = w.post("decision-list", {"title": "D", "references": refs})
    assert r.status_code == 201, r.content
    assert [x["title"] for x in r.json()["references"]] == ["Smith 2020", "No link"]
    url = w.url("decision-detail", decision_id=r.json()["id"])
    r = w.client().patch(url, {"references": refs[::-1]}, format="json")
    assert r.status_code == 200 and r.json()["references"][0]["title"] == "No link"
    r = w.client().patch(url, {"references": []}, format="json")
    assert r.json()["references"] == []
    assert w.post("decision-list", {"title": "D", "references": [GOOD_REF] * 50}).status_code == 201


def test_a_new_version_of_flagged_data_stays_flagged_unless_unticked(w):
    """VISION A3: a flagged dataset's next version must not slip past the AI tools by default."""
    v1 = w.make(
        "dataset-list", {"name": "D", "version_label": "v1", "contains_participant_data": True}
    )
    v2 = w.make("dataset-list", {"name": "D", "version_label": "v2", "previous_version": v1})
    v3 = w.make(
        "dataset-list",
        {
            "name": "D",
            "version_label": "v3",
            "previous_version": v2,
            "contains_participant_data": False,
        },
    )
    plain = w.make("dataset-list", {"name": "E", "version_label": "v1"})
    v2_of_plain = w.make(
        "dataset-list", {"name": "E", "version_label": "v2", "previous_version": plain}
    )
    flags = {
        pk: DatasetRecord.objects.for_lab(w.lab).get(pk=pk).contains_participant_data
        for pk in (v1, v2, v3, v2_of_plain)
    }
    assert flags == {v1: True, v2: True, v3: False, v2_of_plain: False}
