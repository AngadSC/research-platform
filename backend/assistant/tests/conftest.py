import datetime
from types import SimpleNamespace

import pytest

from assistant import tools
from documents import services as document_services
from ethics.models import EthicsApproval
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole, Task, TaskPost
from provenance.models import Analysis, DatasetRecord, FundingRecord, ManuscriptLink, Result


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    """Lab A: pi; contrib (member, contributor on P1); nonproj (member, on no project);
    viewer (lab viewer, contributor on P1, capped to viewer). P2 has nobody but the pi.
    Lab B mirrors P1 with a "SECRET" project. Names carry SECRET where nobody but its own people
    may see them."""
    lab_a, lab_b = make_lab("Lab A"), make_lab("Lab B SECRET")
    u = SimpleNamespace(
        pi=make_user(display_name="Pi"),
        contrib=make_user(display_name="Contrib"),
        nonproj=make_user(display_name="Nonproj"),
        viewer=make_user(display_name="Viewer"),
        other=make_user(display_name="Other"),
    )
    join(u.pi, lab_a, LabRole.PI)
    join(u.contrib, lab_a, LabRole.MEMBER)
    join(u.nonproj, lab_a, LabRole.MEMBER)
    join(u.viewer, lab_a, LabRole.VIEWER)
    join(u.other, lab_b, LabRole.PI)
    p1 = make_project(lab_a, "P1 open")
    p2 = make_project(lab_a, "P2 SECRET hidden")
    pb = make_project(lab_b, "PB SECRET other lab")
    for user, role in ((u.contrib, ProjectRole.CONTRIBUTOR), (u.viewer, ProjectRole.CONTRIBUTOR)):
        ProjectMembership.objects.create(lab=lab_a, project=p1, user=user, role=role)

    def stuff(lab, project, owner, tag):
        task = Task.objects.create(lab=lab, project=project, title=f"Task {tag}", created_by=owner)
        TaskPost.objects.create(lab=lab, task=task, author=owner, body=f"Post {tag}")
        doc = document_services.create_document(
            project=project,
            user=owner,
            title=f"Doc {tag}",
            content=[{"type": "paragraph", "content": [{"type": "text", "text": f"Text {tag}"}]}],
        )
        kw = {"lab": lab, "project": project}
        ds = DatasetRecord.objects.create(
            name=f"Data {tag}",
            version_label="v1",
            checksum="sha256:" + "a" * 64,
            created_by=owner,
            **kw,
        )
        an = Analysis.objects.create(
            title=f"Analysis {tag}",
            code_repo_url="https://example.com/r.git",
            code_commit="abc1234",
            ran_by=owner,
            ran_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
            **kw,
        )
        an.datasets.add(ds)
        res = Result.objects.create(title=f"Result {tag}", analysis=an, created_by=owner, **kw)
        ms = ManuscriptLink.objects.create(
            title=f"Manuscript {tag}", url="https://example.com/ms", created_by=owner, **kw
        )
        ms.results.add(res)
        fund = FundingRecord.objects.create(
            funder=f"Funder {tag}", amount="5000.00", created_by=owner, **kw
        )
        return SimpleNamespace(task=task, doc=doc, ds=ds, an=an, res=res, ms=ms, fund=fund)

    a1 = stuff(lab_a, p1, u.pi, "open")
    a2 = stuff(lab_a, p2, u.pi, "SECRET-p2")
    b = stuff(lab_b, pb, u.other, "SECRET-labb")

    def approval(lab, project, owner, tag, restricted=False):
        ap = EthicsApproval.objects.create(
            lab=lab,
            approval_number=f"N-{tag}",
            board="REB",
            title=f"Ethics {tag}",
            approval_date="2030-01-01",
            expiry_date="2030-06-01",
            restricted=restricted,
            created_by=owner,
        )
        ap.projects.add(project)
        return ap

    eth_open = approval(lab_a, p1, u.pi, "open")
    eth_restricted = approval(lab_a, p2, u.pi, "SECRET-restricted", restricted=True)
    eth_b = approval(lab_b, pb, u.other, "SECRET-labb")
    return SimpleNamespace(
        lab_a=lab_a,
        lab_b=lab_b,
        u=u,
        p1=p1,
        p2=p2,
        pb=pb,
        a1=a1,
        a2=a2,
        b=b,
        eth_open=eth_open,
        eth_restricted=eth_restricted,
        eth_b=eth_b,
    )


@pytest.fixture
def ctx():
    def make(user, *labs, write=False):
        return tools.Context(
            user=user,
            lab_ids=frozenset(str(lab.pk) for lab in labs),
            can_write=write,
            client="Test client",
            grant_id="g1",
        )

    return make
