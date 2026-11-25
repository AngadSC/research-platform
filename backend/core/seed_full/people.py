"""The lab, its people and its projects. Everything else hangs off the ctx this returns."""

import datetime
from types import SimpleNamespace

from allauth.account.models import EmailAddress
from django.utils import timezone

from core.models import User
from labs.models import LabMembership, LabRole
from labs.services import create_lab
from projects import services as project_services
from projects.models import ProjectRole

LAB_NAME = "Northfield Neuroscience Lab (FAKE)"
DOMAIN = "example.test"

# key: (display name, lab role, title used in the bio)
PEOPLE = {
    "pi": ("Dr. Morgan Rivera (FAKE)", LabRole.PI, "Principal investigator"),
    "manager": ("Jordan Okafor (FAKE)", LabRole.LAB_ADMIN, "Lab manager"),
    "coordinator": ("Casey Lindqvist (FAKE)", LabRole.LAB_ADMIN, "Research coordinator"),
    "priya": ("Dr. Priya Natarajan (FAKE)", LabRole.MEMBER, "Postdoctoral fellow"),
    "tomas": ("Dr. Tomas Ferreira (FAKE)", LabRole.MEMBER, "Postdoctoral fellow"),
    "hana": ("Dr. Hana Sato (FAKE)", LabRole.MEMBER, "Postdoctoral fellow"),
    "eli": ("Eli Brooks (FAKE)", LabRole.MEMBER, "PhD student, year 5, leaving soon"),
    "aisha": ("Aisha Mensah (FAKE)", LabRole.MEMBER, "PhD student, year 3"),
    "noah": ("Noah Kim (FAKE)", LabRole.MEMBER, "PhD student, year 2"),
    "sofia": ("Sofia Petrov (FAKE)", LabRole.MEMBER, "PhD student, year 4"),
    "liam": ("Liam Byrne (FAKE)", LabRole.MEMBER, "PhD student, year 1"),
    "grace": ("Grace Chen (FAKE)", LabRole.MEMBER, "MSc student"),
    "mateo": ("Mateo Alvarez (FAKE)", LabRole.MEMBER, "MSc student"),
    "zoe": ("Zoe Martin (FAKE)", LabRole.MEMBER, "Research assistant"),
    "ravi": ("Ravi Patel (FAKE)", LabRole.MEMBER, "Research assistant"),
    "ella": ("Ella Novak (FAKE)", LabRole.MEMBER, "Undergraduate thesis student"),
    "ben": ("Ben Carter (FAKE)", LabRole.MEMBER, "Undergraduate volunteer"),
    "ingrid": ("Dr. Ingrid Hale (FAKE)", LabRole.VIEWER, "External collaborator"),
    "owen": ("Owen Price (FAKE)", LabRole.VIEWER, "Department research officer"),
    "kai": ("Kai Rotation (FAKE)", LabRole.VIEWER, "Rotation student"),
}


def email(key):
    return f"full-{key}@{DOMAIN}"


# key: (name, final status, lead, contributors, viewers, description)
PROJECTS = {
    "sleep": (
        "Sleep and Memory Consolidation (FAKE)",
        "active",
        "priya",
        ["aisha", "grace", "zoe", "ella"],
        ["ingrid"],
        "Overnight EEG and next-day recall in healthy adults. Fake study.",
    ),
    "fmri": (
        "fMRI Attention Networks (FAKE)",
        "active",
        "tomas",
        ["noah", "mateo", "ravi"],
        ["owen"],
        "Task fMRI of sustained attention. Fake study.",
    ),
    "mouse": (
        "Hippocampal Recording in Mice (FAKE)",
        "active",
        "hana",
        ["liam", "ben", "zoe"],
        [],
        "Silicon probe recordings during spatial navigation. Fake animal study.",
    ),
    "ageing": (
        "Ageing Cohort, Wave 3 (FAKE)",
        "active",
        "aisha",
        ["priya", "coordinator", "ravi", "grace"],
        ["ingrid", "owen"],
        "Longitudinal cognition and sleep in older adults. Fake participants only.",
    ),
    "eeg": (
        "EEG Biomarkers Pilot (FAKE)",
        "planning",
        "noah",
        ["tomas", "ella"],
        ["kai"],
        "Planning a resting-state EEG pilot. Fake study.",
    ),
    "reading": (
        "Reading Intervention Trial (FAKE)",
        "paused",
        "sofia",
        ["mateo", "zoe"],
        [],
        "School-based reading trial, paused for the school break. Fake study.",
    ),
    "grant": (
        "Program Grant Renewal 2027 (FAKE)",
        "planning",
        "pi",
        ["priya", "tomas", "hana", "manager"],
        [],
        "Writing the renewal of the program grant. Fake grant.",
    ),
    "crowding": (
        "Visual Crowding Study (FAKE)",
        "completed",
        "eli",
        ["sofia", "ben"],
        ["owen"],
        "Psychophysics of visual crowding. Data collected and published. Fake study.",
    ),
    "pupil": (
        "Pupillometry Pilot, 2022 (FAKE)",
        "archived",
        "eli",
        ["hana"],
        [],
        "An old pilot kept for the record. Fake study.",
    ),
}


def make_user(key, password):
    name, _, title = PEOPLE[key]
    user = User.objects.create_user(
        email=email(key), password=password, display_name=name, bio=f"{title}. Fake person."
    )
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def build(password) -> SimpleNamespace:
    """Make the lab, its 20 people and 9 projects. Returns the ctx every module gets:
    lab, people (key -> User), projects (key -> Project), roles (key -> lab role),
    today, now and day (one day as a timedelta)."""
    people = {key: make_user(key, password) for key in PEOPLE}
    lab = create_lab(user=people["pi"], name=LAB_NAME, website="https://northfield.example.invalid")
    for key, (_, role, _) in PEOPLE.items():
        if key != "pi":
            LabMembership.objects.create(lab=lab, user=people[key], role=role)
    projects = {}
    for key, (name, status, lead, contributors, viewers, description) in PROJECTS.items():
        project = project_services.create_project(
            lab=lab,
            user=people[lead],
            data={
                "name": name,
                "description": description,
                # archived last (archive() below), so the modules can still add to it
                "status": "completed" if status == "archived" else status,
                "members": [people[k].pk for k in contributors],
            },
        )
        for k in viewers:
            project_services.add_member(
                project=project, by=people[lead], user_id=people[k].pk, role=ProjectRole.VIEWER
            )
        projects[key] = project
    return SimpleNamespace(
        lab=lab,
        people=people,
        projects=projects,
        roles={key: role for key, (_, role, _) in PEOPLE.items()},
        today=timezone.localdate(),
        now=timezone.now(),
        day=datetime.timedelta(days=1),
    )


def archive(ctx):
    for key, (_, status, *_rest) in PROJECTS.items():
        if status == "archived":
            project_services.update_project(
                project=ctx.projects[key], user=ctx.people["pi"], data={"status": "archived"}
            )
