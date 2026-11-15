from rest_framework.test import APIClient

from labs.models import LabRole
from projects.models import ProjectMembership


class World:
    def __init__(self, make_lab, make_user, make_project, join):
        self.lab = make_lab("Lab A")
        self.pi = make_user()
        join(self.pi, self.lab, LabRole.PI)
        self.project = make_project(self.lab, "P1")
        self.other = make_project(self.lab, "P2")
        self.lab_b = make_lab("Lab B")
        self.pi_b = make_user()
        join(self.pi_b, self.lab_b, LabRole.PI)
        self.make_user, self.join = make_user, join
        self.base = f"/api/labs/{self.lab.pk}/projects/{self.project.pk}"

    def client(self, user=None):
        c = APIClient()
        c.force_login(user or self.pi)
        return c

    def member(self, role):
        user = self.make_user()
        self.join(user, self.lab, LabRole.MEMBER)
        ProjectMembership.objects.create(lab=self.lab, project=self.project, user=user, role=role)
        return user

    def add(self, *codes, client=None, **extra):
        r = (client or self.client()).post(
            f"{self.base}/participants/", {"codes": list(codes), **extra}, "json"
        )
        assert r.status_code == 201, r.content
        return r.json()

    def column(self, name="Transcript", **extra):
        r = self.client().post(
            f"{self.base}/participant-components/", {"name": name, **extra}, "json"
        )
        assert r.status_code == 201, r.content
        return r.json()

    def reason(self, kind="missing", label="Did not attend"):
        r = self.client().get(f"/api/labs/{self.lab.pk}/participant-reasons/")
        return next(x["id"] for x in r.json() if x["kind"] == kind and x["label"] == label)
