import datetime

import pytest

from audit.models import AuditAction, AuditEvent
from participants.models import CellTask
from projects.models import ProjectRole, Task

pytestmark = pytest.mark.django_db


def setup_cells(w):
    ps = w.add("P-001", "P-002", "P-003", group="Punjabi")
    t = w.column("Translation", category="translation")
    s = w.column("Session", category="session")
    return ps, t, s


def make(w, tasks_mode="cell", **extra):
    ps, t, s = setup_cells(w)
    cells = [{"participant": p["id"], "component": t["id"]} for p in ps]
    r = w.client().post(
        f"{w.base}/participant-tasks/", {"cells": cells, "mode": tasks_mode, **extra}, "json"
    )
    return r, ps, t, s


def test_one_task_per_cell_with_a_useful_title_and_link_back(w):
    r, ps, t, _ = make(w)
    assert r.status_code == 201 and r.json()["created"] == 3
    titles = set(Task.objects.for_lab(w.lab).values_list("title", flat=True))
    assert "Translate P-001, Translation" in titles
    task = Task.objects.for_lab(w.lab).get(title="Translate P-001, Translation")
    assert f"/participants/{ps[0]['id']}" in task.description
    cells = w.client().get(f"{w.base}/participant-cells/").json()
    assert all(len(c["tasks"]) == 1 and c["tasks"][0]["status"] == "todo" for c in cells)


def test_one_task_per_participant_or_per_column(w):
    r, *_ = make(w, "component")
    assert r.json()["created"] == 1
    task = Task.objects.for_lab(w.lab).get()
    assert "3 participants" in task.title and "- P-002" in task.description


def test_asking_twice_never_doubles_the_work(w):
    r, ps, t, _ = make(w)
    again = w.client().post(
        f"{w.base}/participant-tasks/",
        {"cells": [{"participant": ps[0]["id"], "component": t["id"]}]},
        "json",
    )
    assert again.json() == {"created": 0, "skipped": 1, "tasks": []}
    assert Task.objects.for_lab(w.lab).count() == 3


def test_completed_cells_are_not_given_tasks_and_assignee_must_see_the_project(w):
    ps, t, _ = setup_cells(w)
    url = f"{w.base}/participants/{ps[0]['id']}/cells/{t['id']}/"
    w.client().patch(url, {"status": "complete"}, "json")
    cells = [{"participant": ps[0]["id"], "component": t["id"]}]
    r = w.client().post(f"{w.base}/participant-tasks/", {"cells": cells}, "json")
    assert r.json()["created"] == 0 and r.json()["skipped"] == 1
    outsider = w.make_user()
    bad = w.client().post(
        f"{w.base}/participant-tasks/",
        {
            "cells": [{"participant": ps[1]["id"], "component": t["id"]}],
            "assignee": str(outsider.pk),
        },
        "json",
    )
    assert bad.status_code == 400


def test_a_finished_task_does_not_change_the_cell(w):
    r, ps, t, _ = make(w)
    Task.objects.for_lab(w.lab).update(status="done")
    cells = w.client().get(f"{w.base}/participant-cells/").json()
    assert {c["status"] for c in cells} == {"not_started"}  # the person is asked, never synced
    assert CellTask.objects.for_lab(w.lab).count() == 3
    # and a cell with only finished tasks can have a new one
    again = w.client().post(
        f"{w.base}/participant-tasks/",
        {"cells": [{"participant": ps[0]["id"], "component": t["id"]}]},
        "json",
    )
    assert again.json()["created"] == 1
    assert AuditEvent.objects.filter(action=AuditAction.PARTICIPANT_TASKS_CREATED).count() == 2


def test_viewers_cannot_create_tasks(w):
    ps, t, _ = setup_cells(w)
    viewer = w.client(w.member(ProjectRole.VIEWER))
    r = viewer.post(
        f"{w.base}/participant-tasks/",
        {"cells": [{"participant": ps[0]["id"], "component": t["id"]}]},
        "json",
    )
    assert r.status_code == 403


def test_the_lab_overview_rolls_up_what_the_person_can_see(w):
    ps, t, s = setup_cells(w)
    miss = w.reason()
    a, b, c = ps
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    w.client().patch(
        f"{w.base}/participants/{a['id']}/cells/{s['id']}/", {"status": "complete"}, "json"
    )
    w.client().patch(
        f"{w.base}/participants/{b['id']}/cells/{t['id']}/",
        {"status": "missing", "reason": miss, "owner": str(w.pi.pk), "due_date": yesterday},
        "json",
    )
    o = w.client().get(f"/api/labs/{w.lab.pk}/participant-overview/").json()
    (project,) = o["projects"]
    assert project["participants"] == 3 and project["missing"] == 1 and project["overdue"] == 1
    assert o["missing_by_reason"] == [{"reason": "Did not attend", "count": 1}]
    assert o["translation_pending"] == [{"group": "Punjabi", "count": 1}]
    assert o["waiting_on_me"][0]["participant"] == "P-002"
    assert "url" not in str(o)  # no links in the roll-up
    # a member with no access to the project sees nothing of it
    stranger = w.make_user()
    from labs.models import LabRole

    w.join(stranger, w.lab, LabRole.MEMBER)
    empty = w.client(stranger).get(f"/api/labs/{w.lab.pk}/participant-overview/").json()
    assert empty["projects"] == [] and empty["waiting_on_me"] == []
