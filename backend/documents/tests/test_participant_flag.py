"""VISION A3: "Contains participant data" on folders, documents, files and datasets. It is copied
down from folders, changing it needs the right to edit the item, and every change is audited."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents.models import Attachment, Document, Folder
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db
FLAG = "contains_participant_data"


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    lab = make_lab()
    pi, viewer = make_user(), make_user()
    join(pi, lab, LabRole.PI)
    join(viewer, lab, LabRole.MEMBER)
    project = make_project(lab)
    ProjectMembership.objects.create(lab=lab, project=project, user=viewer, role=ProjectRole.VIEWER)

    def client(user):
        c = APIClient()
        c.force_login(user)
        return c

    return lab, project, pi, client(pi), client(viewer)


def u(name, lab, **kw):
    app = "provenance" if name.startswith("dataset") else "documents"
    return reverse(f"{app}:{name}", kwargs={"lab_id": lab.pk, **kw})


def folder(c, lab, project, name, parent=None):
    body = {"name": name, "parent": parent}
    resp = c.post(u("folder-list", lab, project_id=project.pk), body, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def doc(c, lab, project, folder_id=None, **extra):
    body = {"title": "Doc", "content": [], "folder": folder_id, **extra}
    resp = c.post(u("document-list", lab, project_id=project.pk), body, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def upload(c, lab, project, folder_id=None, **extra):
    body = {
        "file": SimpleUploadedFile("a.csv", b"a,b\n1,2\n", content_type="text/csv"),
        "acknowledged_notice": "true",
        **extra,
    }
    if folder_id:
        body["folder"] = folder_id
    resp = c.post(u("attachment-list", lab, project_id=project.pk), body, format="multipart")
    assert resp.status_code == 201, resp.content
    return resp.json()


def flag_folder(c, lab, folder_id, value):
    return c.patch(u("folder-detail", lab, folder_id=folder_id), {FLAG: value}, format="json")


def test_new_items_in_a_flagged_folder_are_flagged(w):
    lab, project, _, pi, _ = w
    top = folder(pi, lab, project, "Raw")
    assert top[FLAG] is False
    assert flag_folder(pi, lab, top["id"], True).json()[FLAG] is True
    assert folder(pi, lab, project, "Sub", parent=top["id"])[FLAG] is True
    assert doc(pi, lab, project, top["id"])[FLAG] is True
    assert upload(pi, lab, project, top["id"])[FLAG] is True
    # outside the folder the box is off unless ticked on upload
    assert doc(pi, lab, project)[FLAG] is False
    assert upload(pi, lab, project)[FLAG] is False
    assert upload(pi, lab, project, **{FLAG: "true"})[FLAG] is True
    assert doc(pi, lab, project, **{FLAG: True})[FLAG] is True


def test_flagging_a_folder_flags_everything_inside_and_clearing_leaves_it(w):
    lab, project, user, pi, _ = w
    top = folder(pi, lab, project, "Top")
    mid = folder(pi, lab, project, "Mid", parent=top["id"])
    deep = folder(pi, lab, project, "Deep", parent=mid["id"])
    d = doc(pi, lab, project, deep["id"])
    a = upload(pi, lab, project, mid["id"])
    outside = doc(pi, lab, project)
    assert flag_folder(pi, lab, top["id"], True).status_code == 200
    assert all(f.contains_participant_data for f in Folder.objects.for_lab(lab))
    assert Document.objects.for_lab(lab).get(pk=d["id"]).contains_participant_data
    assert Attachment.objects.for_lab(lab).get(pk=a["id"]).contains_participant_data
    assert not Document.objects.for_lab(lab).get(pk=outside["id"]).contains_participant_data
    event = AuditEvent.objects.get(action=AuditAction.FOLDER_PARTICIPANT_FLAG_CHANGED)
    assert event.actor == user and str(event.target_id) == top["id"]
    assert event.metadata == {"old": False, "new": True, "items_flagged": 4}

    assert flag_folder(pi, lab, top["id"], False).json()[FLAG] is False
    assert Folder.objects.for_lab(lab).get(pk=mid["id"]).contains_participant_data
    assert Document.objects.for_lab(lab).get(pk=d["id"]).contains_participant_data
    cleared = AuditEvent.objects.filter(action=AuditAction.FOLDER_PARTICIPANT_FLAG_CHANGED)
    assert cleared.count() == 2
    assert cleared.order_by("occurred_at").last().metadata == {"old": True, "new": False}


def test_rename_still_works_and_an_unchanged_flag_writes_nothing(w):
    lab, project, _, pi, _ = w
    f = folder(pi, lab, project, "Old")
    resp = pi.patch(u("folder-detail", lab, folder_id=f["id"]), {"name": "New"}, format="json")
    assert resp.status_code == 200 and resp.json()["name"] == "New"
    assert flag_folder(pi, lab, f["id"], False).status_code == 200
    assert not AuditEvent.objects.filter(action=AuditAction.FOLDER_PARTICIPANT_FLAG_CHANGED)


@pytest.mark.parametrize("kind", ["document", "attachment", "dataset"])
def test_changing_the_flag_needs_edit_rights_and_is_audited(w, kind):
    lab, project, user, pi, viewer = w
    if kind == "document":
        item_id = doc(pi, lab, project)["id"]
        detail = u("document-detail", lab, document_id=item_id)
        action = AuditAction.DOCUMENT_PARTICIPANT_FLAG_CHANGED
    elif kind == "attachment":
        item_id = upload(pi, lab, project)["id"]
        detail = u("attachment-detail", lab, attachment_id=item_id)
        action = AuditAction.ATTACHMENT_PARTICIPANT_FLAG_CHANGED
    else:
        item_id = str(
            DatasetRecord.objects.create(
                lab=lab, project=project, name="D", version_label="v1", created_by=user
            ).pk
        )
        detail = u("dataset-detail", lab, datasetrecord_id=item_id)
        action = AuditAction.DATASET_PARTICIPANT_FLAG_CHANGED
    assert viewer.patch(detail, {FLAG: True}, format="json").status_code == 403
    assert not AuditEvent.objects.filter(action=action).exists()
    resp = pi.patch(detail, {FLAG: True}, format="json")
    assert resp.status_code == 200 and resp.json()[FLAG] is True
    event = AuditEvent.objects.get(action=action)
    assert event.actor == user and str(event.target_id) == item_id
    assert event.metadata == {"old": False, "new": True}
    assert viewer.get(detail).json()[FLAG] is True  # readable by anyone who can see it


def test_dataset_flag_alone_writes_only_the_flag_event(w):
    lab, project, user, pi, _ = w
    ds = DatasetRecord.objects.create(
        lab=lab, project=project, name="D", version_label="v1", created_by=user
    )
    detail = u("dataset-detail", lab, datasetrecord_id=ds.pk)
    assert pi.patch(detail, {FLAG: True}, format="json").status_code == 200
    assert not AuditEvent.objects.filter(action=AuditAction.DATASET_UPDATED).exists()
    resp = pi.patch(detail, {"access_notes": "x", FLAG: False}, format="json")
    assert resp.status_code == 200 and resp.json()[FLAG] is False
    assert AuditEvent.objects.filter(action=AuditAction.DATASET_UPDATED).count() == 1
    assert (
        AuditEvent.objects.filter(action=AuditAction.DATASET_PARTICIPANT_FLAG_CHANGED).count() == 2
    )


def test_flag_sticks_to_items_when_their_folder_goes_away(w):
    from documents import services
    from documents.models import Attachment, Document

    lab, project, _, pi, _ = w
    box = folder(pi, lab, project, "Raw")
    sub = folder(pi, lab, project, "Sub", parent=box["id"])
    moved_doc, moved_file = doc(pi, lab, project), upload(pi, lab, project)
    d = Document.objects.for_lab(lab).get(pk=moved_doc["id"])
    f = Attachment.objects.for_lab(lab).get(pk=moved_file["id"])
    services.move_to_folder(d, Folder.objects.for_lab(lab).get(pk=box["id"]))
    services.move_to_folder(f, Folder.objects.for_lab(lab).get(pk=box["id"]))
    flag_folder(pi, lab, box["id"], True)  # the new items sit in it, the moved ones too
    # one more moved in after the box was flagged (a plain move, no flag of its own yet)
    late = Attachment.objects.for_lab(lab).get(pk=upload(pi, lab, project)["id"])
    services.move_to_folder(late, Folder.objects.for_lab(lab).get(pk=box["id"]))
    assert late.contains_participant_data
    Attachment.objects.for_lab(lab).filter(pk=f.pk).update(contains_participant_data=False)
    services.delete_folder(Folder.objects.for_lab(lab).get(pk=box["id"]))
    for model, pk in ((Document, d.pk), (Attachment, f.pk), (Attachment, late.pk)):
        item = model.objects.for_lab(lab).get(pk=pk)
        assert item.folder is None and item.contains_participant_data
    assert Folder.objects.for_lab(lab).get(pk=sub["id"]).contains_participant_data
