import pytest
from django.db.models import Count

from core.tenancy import CrossLabError, LabScopedModel, UnscopedQueryError, check_m2m_same_lab
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_labs(make_lab, make_project):
    a, b = make_lab("A"), make_lab("B")
    return a, b, make_project(a, "pa"), make_project(b, "pb")


@pytest.mark.parametrize(
    "call",
    [
        lambda m: list(m.objects.all()),
        lambda m: m.objects.count(),
        lambda m: m.objects.exists(),
        lambda m: m.objects.first(),
        lambda m: m.objects.get(),
        lambda m: m.objects.filter(name="x").values("name").first(),
        lambda m: m.objects.update(name="x"),
        lambda m: m.objects.all().delete(),
        lambda m: m.objects.aggregate(n=Count("pk")),
        lambda m: list(m.objects.all().iterator()),
        lambda m: m.objects.in_bulk([]),
    ],
)
def test_unscoped_query_raises(two_labs, call):
    with pytest.raises(UnscopedQueryError):
        call(Project)


def test_user_reverse_manager_raises(two_labs, make_user):
    with pytest.raises(UnscopedQueryError):
        list(make_user().projectmembership_set.all())


def test_related_manager_is_scoped(two_labs):
    _, _, pa, _ = two_labs
    assert list(pa.memberships.all()) == []


def test_for_lab_and_visible_to(two_labs, make_user, join):
    a, b, pa, pb = two_labs
    other = Project.objects.create(lab=a, name="pa2", created_by=pa.created_by)
    assert set(Project.objects.for_lab(a)) == {pa, other}
    assert list(Project.objects.for_lab(b)) == [pb]

    pi, member, viewer, outsider = (make_user() for _ in range(4))
    join(pi, a, LabRole.PI)
    join(member, a, LabRole.MEMBER)
    join(viewer, a, LabRole.VIEWER)
    join(pi, b, LabRole.MEMBER)  # pi of A is only a plain member of B
    ProjectMembership.objects.create(project=pa, user=member, role=ProjectRole.LEAD)
    ProjectMembership.objects.create(project=pb, user=member, role=ProjectRole.LEAD)

    assert set(Project.objects.visible_to(pi, a)) == {pa, other}
    assert set(Project.objects.visible_to(member, a)) == {pa}
    assert list(Project.objects.visible_to(viewer, a)) == []
    assert list(Project.objects.visible_to(outsider, a)) == []
    assert list(Project.objects.visible_to(pi, b)) == []  # member of B without a project role
    assert list(ProjectMembership.objects.visible_to(member, a)) == [
        ProjectMembership.objects.for_lab(a).get()
    ]


def test_lab_consistency_rejects_cross_lab_child(two_labs, make_user):
    a, b, pa, _ = two_labs
    u = make_user()
    with pytest.raises(CrossLabError):
        ProjectMembership.objects.create(lab=b, project=pa, user=u, role=ProjectRole.VIEWER)
    child = ProjectMembership.objects.create(project=pa, user=u, role=ProjectRole.VIEWER)
    assert child.lab_id == a.pk  # copied from the parent


def test_update_cannot_move_lab(two_labs):
    a, b, _, _ = two_labs
    with pytest.raises(CrossLabError):
        Project.objects.for_lab(a).update(lab=b)
    with pytest.raises(CrossLabError):
        ProjectMembership.objects.for_lab(a).update(project_id=None)


def test_m2m_receiver_rejects_other_lab(two_labs):
    _, _, pa, pb = two_labs
    with pytest.raises(CrossLabError):
        check_m2m_same_lab(None, pa, "pre_add", Project, {pb.pk})
    check_m2m_same_lab(None, pa, "pre_add", Project, {pa.pk})


def test_all_lab_models_declare_unscoped_as_base():
    from django.apps import apps

    found = [m for m in apps.get_models() if issubclass(m, LabScopedModel)]
    assert found
    assert all(m._meta.base_manager_name == "unscoped" for m in found)
