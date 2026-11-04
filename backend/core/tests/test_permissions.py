import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404

from core.permissions import Perm, can, get_lab_or_404, require, users_with, visible_projects
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db
Y, N = True, False

# Hand-written copy of ARCHITECTURE section 3 (lab roles), order: pi admin member viewer.
LAB_TABLE = {
    Perm.VIEW_LAB: (Y, Y, Y, Y),
    Perm.MANAGE_LAB: (Y, Y, N, N),
    Perm.MANAGE_MEMBERS: (Y, Y, N, N),
    Perm.MANAGE_BILLING: (Y, N, N, N),
    Perm.VIEW_AUDIT_LOG: (Y, Y, N, N),
    Perm.CREATE_PROJECT: (Y, Y, Y, N),
    Perm.VIEW_ETHICS: (Y, Y, Y, Y),
    Perm.EDIT_ETHICS: (Y, Y, Y, N),
    Perm.VIEW_RETENTION: (Y, Y, N, N),
}
LAB_ROLES = [LabRole.PI, LabRole.LAB_ADMIN, LabRole.MEMBER, LabRole.VIEWER]
# Project roles, order: lead contributor viewer.
PROJECT_TABLE = {
    Perm.VIEW_PROJECT: (Y, Y, Y),
    Perm.EDIT_CONTENT: (Y, Y, N),
    Perm.EDIT_PROJECT: (Y, N, N),
    Perm.MANAGE_PROJECT_MEMBERS: (Y, N, N),
    Perm.EXPORT: (Y, N, N),
}
PROJECT_ROLES = [ProjectRole.LEAD, ProjectRole.CONTRIBUTOR, ProjectRole.VIEWER]


@pytest.fixture
def setup(make_lab, make_project):
    lab = make_lab()
    return lab, make_project(lab)


@pytest.mark.parametrize("perm", list(LAB_TABLE))
@pytest.mark.parametrize("i", range(4))
def test_lab_role_table(setup, make_user, join, perm, i):
    lab, _ = setup
    user = make_user()
    join(user, lab, LAB_ROLES[i])
    assert can(user, perm, lab) is LAB_TABLE[perm][i]


@pytest.mark.parametrize("i", range(4))
def test_delete_project_table(setup, make_user, join, i):
    lab, project = setup
    user = make_user()
    join(user, lab, LAB_ROLES[i])
    assert can(user, Perm.DELETE_PROJECT, project) is (i < 2)


@pytest.mark.parametrize("perm", list(PROJECT_TABLE))
@pytest.mark.parametrize("i", range(3))
def test_project_role_table(setup, make_user, join, perm, i):
    lab, project = setup
    user = make_user()
    join(user, lab, LabRole.MEMBER)
    ProjectMembership.objects.create(project=project, user=user, role=PROJECT_ROLES[i])
    assert can(user, perm, project) is PROJECT_TABLE[perm][i]


@pytest.mark.parametrize("perm", list(PROJECT_TABLE))
@pytest.mark.parametrize("lab_role_", [LabRole.PI, LabRole.LAB_ADMIN])
def test_pi_and_admin_are_implicit_leads(setup, make_user, join, perm, lab_role_):
    lab, project = setup
    user = make_user()
    join(user, lab, lab_role_)
    assert can(user, perm, project) is True


def test_member_without_project_membership_has_nothing(setup, make_user, join):
    lab, project = setup
    user = make_user()
    join(user, lab, LabRole.MEMBER)
    assert not can(user, Perm.VIEW_PROJECT, project)
    assert list(visible_projects(user, lab)) == []
    with pytest.raises(Http404):
        require(user, Perm.VIEW_PROJECT, project)


def test_lab_viewer_capped_and_non_member_has_no_access(setup, make_user, join):
    lab, project = setup
    viewer, outsider = make_user(), make_user()
    join(viewer, lab, LabRole.VIEWER)
    for u in (viewer, outsider):
        ProjectMembership.objects.create(project=project, user=u, role=ProjectRole.LEAD)
    assert can(viewer, Perm.VIEW_PROJECT, project)
    assert not can(viewer, Perm.EDIT_CONTENT, project)
    assert not can(outsider, Perm.VIEW_PROJECT, project)
    with pytest.raises(PermissionDenied):
        require(viewer, Perm.EDIT_CONTENT, project)
    with pytest.raises(Http404):
        require(outsider, Perm.VIEW_PROJECT, project)


def test_pseudo_perms_and_get_lab_or_404(setup, make_user, join):
    lab, _ = setup
    user = make_user()
    assert can(None, Perm.PUBLIC)
    assert can(user, Perm.AUTHENTICATED)
    with pytest.raises(Http404):
        get_lab_or_404(user, lab.pk)
    with pytest.raises(Http404):
        get_lab_or_404(user, "not-a-uuid")
    join(user, lab, LabRole.VIEWER)
    user._perm_cache = {}
    assert get_lab_or_404(user, lab.pk) == lab


def test_users_with(setup, make_user, join):
    lab, project = setup
    pi, lead, contrib, viewer_pm = (make_user() for _ in range(4))
    join(pi, lab, LabRole.PI)
    for u, role in ((lead, ProjectRole.LEAD), (contrib, ProjectRole.CONTRIBUTOR)):
        join(u, lab, LabRole.MEMBER)
        ProjectMembership.objects.create(project=project, user=u, role=role)
    join(viewer_pm, lab, LabRole.VIEWER)
    ProjectMembership.objects.create(project=project, user=viewer_pm, role=ProjectRole.LEAD)
    assert set(users_with(Perm.EXPORT, project)) == {pi, lead}
    assert set(users_with(Perm.EDIT_CONTENT, project)) == {pi, lead, contrib}
    assert set(users_with(Perm.VIEW_PROJECT, project)) == {pi, lead, contrib, viewer_pm}
    assert set(users_with(Perm.VIEW_RETENTION, lab)) == {pi}
