# ruff: noqa: E501  (seed tables are data, kept compact)
"""Project-level research data for the full fake lab: tasks, chat, deadlines, documents,
provenance, papers, notebooks, comments and the Ageing cohort participant registry. Everything
goes through the services, acting as someone allowed to do it. Deterministic (Random(7))."""

import datetime
import random

from django.core.files.uploadedfile import SimpleUploadedFile

from core import reactions
from core.management.commands.seed_pilot import PNG_BYTES, block, make_pdf
from core.models import PageComment
from core.seed_full.people import PROJECTS
from documents import services as docs
from documents.models import DocumentComment, Folder, PinnedDocument
from labs import notebook
from labs import services as lab_services
from labs.models import LabChatMessage
from papers import services as papers
from participants import rules as prule
from participants import services as part
from participants.models import Component, StatusReason
from projects import services as proj
from projects.models import ChatMessage, Task, TaskPost
from provenance import dmp
from provenance import services as prov

rng = random.Random(7)
FAKE_COMMIT = "9d8c7b6a5f4e3d2c1b0a9d8c7b6a5f4e3d2c1b0a"

# ---------------------------------------------------------------- tables

TOPIC = {
    "sleep": "Sleep", "fmri": "fMRI", "mouse": "Mouse", "ageing": "Ageing", "eeg": "EEG",
    "reading": "Reading", "grant": "Grant", "crowding": "Crowding", "pupil": "Pupil",
}  # fmt: skip

TASKS = {
    "sleep": ["Order replacement EEG caps", "Write the recall scoring guide", "Screen 8 new volunteers",
              "Fix the overnight trigger timing", "Score recall for batch 3", "Clean spindle detection output",
              "Pre-register the main analysis", "Book the sleep room for January", "Check electrode impedance logs",
              "Draft methods section", "Update consent for the follow-up call", "Back up night-1 recordings",
              "Re-run slow-wave detection with new threshold", "Prepare lab meeting slides"],
    "fmri": ["Run motion QC on all subjects", "Write the preprocessing pipeline note", "Book scanner time for March",
             "Fix the stimulus onset logging", "Draft the ROI definition", "Model the vigilance decrement",
             "Rerun group model with covariates", "Collect the practice-block data", "Check eye-tracker calibration",
             "Write the ethics amendment for new task", "Archive raw DICOMs", "Prepare conference abstract",
             "Compare surface and volume results", "Update the analysis README"],
    "mouse": ["Order probe replacements", "Surgery schedule for cohort 4", "Spike-sort session 12 to 18",
              "Calibrate the maze rewards", "Histology for animal M07", "Write the place-cell metrics code",
              "Check cable noise on rig 2", "Update the animal care log", "Train two animals on the new track",
              "Backup recordings to cold storage", "Draft figure 2 panels", "Review the approved protocol changes"],
    "ageing": ["Call back participants for wave 3 visits", "Check consent forms are all signed", "Score the memory battery",
               "Reconcile the visit calendar", "Ship actigraphy watches", "Fix questionnaire export columns",
               "Write the wave 3 data cleaning plan", "Review missing-data report", "Order parking vouchers",
               "Train new assistant on the battery", "Update the retention plan", "Prepare DSMB summary",
               "Merge wave 2 and wave 3 files", "Spot-check double entry", "Draft the interim report"],
    "eeg": ["Pick the headset vendor", "Write the pilot protocol", "Draft the power calculation",
            "Request ethics amendment", "Test the resting-state script", "Make the recruitment flyer",
            "Book the EEG room", "Choose preprocessing defaults"],
    "reading": ["Confirm school start dates", "Print the testing booklets", "Hire two test administrators",
                "Update the teacher training slides", "Chase the missing parental consents", "Plan the resume visit",
                "Check the paused budget", "Write the pause notice for schools"],
    "grant": ["Outline the specific aims", "Collect biosketches", "Draft the budget justification",
              "Write the preliminary data section", "Get letters of support", "Review the previous reviews",
              "Create the timeline figure", "Internal review round 1", "Check page limits", "Draft the data sharing plan",
              "Request institutional sign-off", "Final proofread"],
    "crowding": ["Submit the camera-ready paper", "Post the data to the repository", "Answer reviewer 2",
                 "Archive the stimulus code", "Write the lay summary", "Close the ethics file",
                 "Hand over the project folder", "Update the lab website"],
    "pupil": ["Archive the raw pupil recordings", "Write the handover note", "Close the equipment loan"],
}  # fmt: skip

POSTS = [
    "Started on this today, nothing blocking yet",
    "Blocked until the room booking is confirmed",
    "Done on my side, can you have a look",
    "Pushed a first version, notes are in the project documents",
    "I need two more days, the export keeps failing",
    "Checked it again and the numbers match",
    "Moved the deadline after talking to the lead",
    "Can you review before Friday",
]
CHAT = [
    "Uploaded the latest export to the project documents",
    "Reminder: meeting tomorrow, agenda is in the notes",
    "Does anyone have the updated consent wording",
    "The room is booked for the whole week",
    "I fixed the script, please pull before running",
    "Running the pipeline overnight, results in the morning",
    "Can someone cover the Thursday session",
    "Thanks, that worked",
    "Found the bug, it was the time zone again",
    "Please log your hours before the end of the month",
    "New version of the analysis plan is in documents",
    "Sorry, I missed that, will do today",
    "Great progress this week",
    "Who is taking the notes at the meeting",
    "The equipment arrived, I left it in the cupboard",
    "Quick question about the exclusion rule",
    "I will be out Monday",
    "Draft figures are up for comments",
    "Can we move the check-in to the afternoon",
    "Backups finished without errors",
]
LAB_CHAT = [
    "Welcome to the lab chat, use it for lab-wide notices",
    "Fire drill on Thursday at 10:00",
    "The shared printer is out of toner again",
    "Journal club this week is on sleep and memory",
    "Please sign out of the shared computers when you leave",
    "Congratulations on the accepted paper",
    "Pizza in the kitchen after the seminar",
    "Reminder to update your project tasks before the Friday meeting",
    "The freezer alarm went off, it was a false alarm",
    "New student starts Monday, please say hello",
    "Seminar room is free this afternoon",
    "Annual safety training links are in the training page",
    "Lab meeting moved to 14:00",
    "Does anyone have a spare HDMI cable",
    "Holiday schedule is posted on the door",
    "The supplier is delayed by a week",
    "Thanks to everyone who helped with the open house",
    "Reminder: no food near the EEG cabinet",
    "Grant renewal deadline is closing in, check the grant project",
    "Great talk today",
]
DEADLINES = [
    ("Ethics renewal", 40, "high"), ("Interim report", 25, "medium"), ("Conference abstract", -6, "high"),
    ("Data freeze", 14, "high"), ("Draft of methods", -20, "low"), ("Equipment order cut-off", 8, "medium"),
    ("Pre-registration", -35, "medium"), ("Final report", 90, "low"), ("Lab meeting presentation", 3, "low"),
]  # fmt: skip
DOCS = [
    ("{t} protocol", "Protocol"), ("{t} analysis plan", "Analysis"), ("Meeting notes, week 12", "Meetings"),
    ("{t} data dictionary", "Analysis"), ("Onboarding guide for {t}", "Protocol"), ("Open questions", "Meetings"),
]  # fmt: skip
SENTENCES = [
    "This is invented text for a demo lab.", "Nothing here describes a real study.",
    "Measurements were taken on a fake schedule.", "The team agreed to revisit this next month.",
    "Numbers in this document are made up.", "Open items are listed below.",
]  # fmt: skip
COMMENTS = ["Can we clarify this step?", "I added the missing numbers.", "Looks good to me.",
            "Should this go in the protocol instead?", "Updated after the meeting."]  # fmt: skip
HUMAN = ("sleep", "ageing", "eeg", "reading", "crowding")
STUDY = {"sleep": "in_review", "fmri": "submitted", "mouse": "drafting", "ageing": "drafting",
         "crowding": "published", "reading": "drafting", "pupil": "accepted"}  # fmt: skip
FUNDERS = {
    "sleep": ("Example Health Council (FAKE)", 420000, "active"),
    "fmri": ("Example Science Fund (FAKE)", 650000, "active"),
    "mouse": ("Example Brain Foundation (FAKE)", 310000, "awarded"),
    "ageing": ("Example Ageing Institute (FAKE)", 880000, "active"),
    "grant": ("Example Science Fund (FAKE)", 1500000, "applied"),
    "eeg": ("Example Seed Grant (FAKE)", 40000, "declined"),
}  # fmt: skip
PAPERS = [
    ("Slow oscillations and overnight recall", 2019, "Journal of Fake Sleep Research"),
    ("Spindle density predicts memory gains", 2021, "Fake Neuroscience Letters"),
    ("Sustained attention networks in the scanner", 2020, "Journal of Invented Cognition"),
    ("Vigilance decrement revisited", 2018, "Fake Brain Mapping"),
    ("Place cells remap in new rooms", 2017, "Hippocampus Reports (FAKE)"),
    ("Silicon probes for freely moving mice", 2022, "Methods in Fake Neuroscience"),
    ("Cognitive ageing across ten years", 2016, "Fake Gerontology"),
    ("Sleep fragmentation in older adults", 2023, "Journal of Invented Ageing"),
    ("Retention in longitudinal cohorts", 2015, "Fake Epidemiology Review"),
    ("Resting-state EEG as a biomarker", 2021, "Fake Clinical Neurophysiology"),
    ("Alpha power and attention lapses", 2019, "Journal of Invented Cognition"),
    ("A trial of phonics teaching", 2018, "Fake Education Research"),
    ("Reading gains after school breaks", 2020, "Fake Education Research"),
    ("Crowding in peripheral vision", 2014, "Journal of Fake Vision"),
    ("Psychophysics with staircases", 2013, "Fake Vision Methods"),
    ("Pupil size tracks effort", 2012, "Fake Psychophysiology"),
    ("Open data in neuroscience labs", 2022, "Fake Open Science"),
    ("Pre-registration in practice", 2021, "Fake Open Science"),
    ("Mixed models for repeated measures", 2017, "Fake Statistics Today"),
    ("Handling missing data", 2016, "Fake Statistics Today"),
    ("Reproducible pipelines for EEG", 2020, "Fake Neuroinformatics"),
    ("Writing a data management plan", 2019, "Fake Research Practice"),
    ("Memory consolidation theories compared", 2015, "Fake Memory Reviews"),
    ("Lab handover and lost knowledge", 2023, "Fake Research Practice"),
    ("Power analysis for small pilots", 2018, "Fake Statistics Today"),
]  # fmt: skip
NOTES = [
    "Good methods section, borrow the exclusion wording", "Effect size is small, check the power",
    "Relevant for our wave 3 design", "Figure 3 is the one to show at journal club",
    "Their code is not shared, ask the authors", "Contradicts the 2019 paper above",
]  # fmt: skip
PEOPLE_CELLS = ["complete"] * 11 + ["in_progress", "needs_review", "needs_review", "not_started",
                                     "missing", "missing", "excluded", "not_applicable"]  # fmt: skip


# ---------------------------------------------------------------- helpers


class Ctx:
    """Small bag so the helpers read the same `ctx` without passing it everywhere."""

    def __init__(self, ctx):
        self.__dict__.update(ctx.__dict__)
        self.ctx = ctx

    def user(self, key):
        return self.people[key]

    def actors(self, pkey):
        """Who may edit this project's content (lead and contributors), as users."""
        _, _, lead, contributors, _, _ = PROJECTS[pkey]
        return [self.people[k] for k in [lead, *contributors]]

    def lead(self, pkey):
        return self.people[PROJECTS[pkey][2]]

    def name(self, user):
        return f"@[{user.display_name}](user:{user.pk})"

    def when(self, minutes_ago):
        return self.now - datetime.timedelta(minutes=minutes_ago)


def fake(text):
    return text if "(FAKE)" in text else f"{text} (FAKE)"


def backdate(model, obj, when):
    model.objects.for_lab(obj.lab_id).filter(pk=obj.pk).update(created_at=when)


def paras(n=3):
    return [block("paragraph", " ".join(rng.sample(SENTENCES, 3)) + " (FAKE)") for _ in range(n)]


def upload(project, user, name, data, kind, folder=None, flagged=False):
    return docs.upload_attachment(
        project=project, user=user, folder=folder, contains_participant_data=flagged,
        file=SimpleUploadedFile(name, data, content_type=kind),
    )  # fmt: skip


def csv_bytes(rows=6):
    return (
        "id,score\n" + "\n".join(f"FAKE-{i:03d},{rng.randint(10, 99)}" for i in range(rows))
    ).encode()


# ---------------------------------------------------------------- seed


def seed(ctx):
    c = Ctx(ctx)
    live = [k for k, v in PROJECTS.items() if v[1] != "planning" or k == "grant"]
    docs_by_project = {}
    for key in PROJECTS:
        docs_by_project[key] = seed_documents(c, key)
    for key in PROJECTS:
        seed_tasks(c, key, docs_by_project[key])
        seed_chat(c, key)
        seed_deadlines(c, key)
    seed_lab_chat(c)
    for key in live:
        seed_provenance(c, key, docs_by_project[key])
    seed_papers(c)
    seed_notebooks(c)
    seed_participants(c)
    seed_comments(c)


def seed_tasks(c, key, doc_list):
    project = c.projects[key]
    actors = c.actors(key)
    lead = c.lead(key)
    for i, title in enumerate(TASKS[key]):
        roll = rng.random()
        status = "done" if roll < 0.35 else "in_progress" if roll < 0.6 else "todo"
        days = rng.randint(-25, -2) if status == "done" else rng.randint(-14, 45)
        who = rng.choice(actors) if rng.random() < 0.8 else None
        task = proj.create_task(
            project=project, by=lead,
            data={"title": fake(title), "status": status, "assignee": who.pk if who else None,
                  "description": f"{rng.choice(SENTENCES)} (FAKE)",
                  "due_date": c.today + datetime.timedelta(days=days)},
        )  # fmt: skip
        backdate(Task, task, c.when(rng.randint(60 * 24 * 10, 60 * 24 * 300)))
        if i % 3 == 0:
            for _ in range(rng.randint(1, 3)):
                a, b = rng.sample(actors, 2)
                post = proj.create_post(
                    task=task, author=a, body=fake(f"{rng.choice(POSTS)}, {c.name(b)}")
                )
                backdate(TaskPost, post, c.when(rng.randint(60, 60 * 24 * 30)))
        if i % 4 == 0 and doc_list:
            proj.link_to_task(task=task, kind="documents", obj=doc_list[i % len(doc_list)])


def seed_chat(c, key):
    project = c.projects[key]
    actors = c.actors(key)
    busy = PROJECTS[key][1] == "active"
    n = rng.randint(15, 40) if busy else rng.randint(4, 9)
    minutes = sorted(rng.sample(range(30, 60 * 24 * 45), n), reverse=True)
    made = []
    for m in minutes:
        a, b = rng.sample(actors, 2)
        text = rng.choice(CHAT) + (f", {c.name(b)}" if rng.random() < 0.2 else "")
        msg = proj.post_message(project=project, by=a, body=fake(text))
        backdate(ChatMessage, msg, c.when(m))
        made.append(msg)
    for msg in rng.sample(made, min(6, len(made))):
        for u in rng.sample(actors, 2):
            reactions.toggle(
                ChatMessage.objects.for_lab(c.lab),
                msg.pk,
                u,
                rng.choice(["\U0001f44d", "\U0001f389", "\U0001f440"]),
            )
    for u in actors:  # some read everything, some half, some never opened it
        pick = rng.choice(["all", "half", "none"])
        if pick != "none":
            read_to = c.now if pick == "all" else c.when(60 * 24 * rng.randint(5, 25))
            proj.mark_chat_read(project=project, user=u, read_to=read_to)


def seed_lab_chat(c):
    staff = [c.people[k] for k, r in c.roles.items() if r != "viewer"]
    for i, m in enumerate(sorted(rng.sample(range(30, 60 * 24 * 60), 30), reverse=True)):
        a, b = rng.sample(staff, 2)
        text = LAB_CHAT[i % len(LAB_CHAT)] + (f", {c.name(b)}" if i % 5 == 0 else "")
        msg = lab_services.post_lab_message(lab=c.lab, by=a, body=fake(text))
        backdate(LabChatMessage, msg, c.when(m))
        if i % 6 == 0:
            reactions.toggle(LabChatMessage.objects.for_lab(c.lab), msg.pk, b, "\U0001f44d")
    for k in ("priya", "tomas", "aisha", "zoe"):
        lab_services.mark_lab_chat_read(
            lab=c.lab, user=c.people[k], read_to=c.when(60 * 24 * rng.randint(0, 12))
        )


def seed_deadlines(c, key):
    project = c.projects[key]
    for title, days, priority in rng.sample(DEADLINES, rng.randint(3, 5)):
        d = proj.create_deadline(
            project=project,
            data={
                "title": fake(title),
                "due_date": c.today + datetime.timedelta(days=days),
                "priority": priority,
            },
        )
        if days < 0 and rng.random() < 0.6:
            proj.update_deadline(deadline=d, data={"done": True})


def seed_documents(c, key):
    """Folders, documents with revisions, a pin, comments and files. Returns the documents."""
    project = c.projects[key]
    actors = c.actors(key)
    lead = c.lead(key)
    t = TOPIC[key]
    folders = {
        n: docs.create_folder(project=project, user=lead, name=n)
        for n in ("Protocol", "Analysis", "Meetings")
    }
    raw = None
    if key == "ageing":  # VISION A3: items in a flagged folder are flagged too
        raw = docs.create_folder(project=project, user=lead, name="Raw data (participant data)")
        Folder.objects.for_lab(c.lab).filter(pk=raw.pk).update(contains_participant_data=True)
        raw.refresh_from_db()
    made = []
    for title, folder in DOCS if key not in ("pupil", "eeg") else DOCS[:3]:
        author = rng.choice(actors)
        doc = docs.create_document(
            project=project, user=author, title=fake(title.format(t=t)), folder=folders[folder],
            content=[block("heading", fake(title.format(t=t)), level=1), *paras()],
        )  # fmt: skip
        for _ in range(rng.randint(0, 4)):  # revisions, by different people
            doc = docs.save_document(
                doc, title=doc.title, base_version=doc.version, user=rng.choice(actors),
                content=[block("heading", doc.title, level=1), *paras()],
            )  # fmt: skip
        made.append(doc)
    PinnedDocument.objects.create(lab=c.lab, document=made[0], pinned_by=lead)
    for doc in made[:2]:
        first = docs.add_comment(
            doc, user=rng.choice(actors), body=fake(rng.choice(COMMENTS)), quote="Fake text"
        )
        docs.add_comment(doc, user=doc.created_by, body=fake(rng.choice(COMMENTS)), parent=first)
    docs.resolve_comment(
        DocumentComment.objects.for_lab(c.lab)
        .filter(document=made[0], parent__isnull=True)
        .first(),
        user=lead,
        resolved=True,
    )
    for name, data, kind, folder in [
        (f"{t.lower()}-consent-sheet.pdf", make_pdf(), "application/pdf", folders["Protocol"]),
        (f"{t.lower()}-figure-1.png", PNG_BYTES, "image/png", folders["Analysis"]),
        (f"{t.lower()}-summary.csv", csv_bytes(), "text/csv", folders["Analysis"]),
    ]:
        upload(project, rng.choice(actors), name, data, kind, folder)
    if raw:
        for name in ("raw-sessions-wave3.csv", "raw-questionnaires-wave3.csv"):
            upload(project, lead, name, csv_bytes(12), "text/csv", raw)
        made.append(
            docs.create_document(project=project, user=lead, title=fake("Participant key notes"), folder=raw,
                                 content=[block("paragraph", "Codes only, no names (FAKE).")])
        )  # fmt: skip
    return made


def seed_provenance(c, key, doc_list):
    project = c.projects[key]
    actors = c.actors(key)
    lead, pi = c.lead(key), c.people["pi"]
    t = TOPIC[key]
    flagged = key == "ageing"
    base = {"location_text": "Lab secure drive (FAKE)", "location_url": f"https://data.example.invalid/{key}",
            "controlled_by": lead.pk, "access_notes": "The lead approves requests (FAKE).",
            "contains_participant_data": flagged}  # fmt: skip
    prev, sets = None, []
    for n in range(rng.randint(2, 3)):
        prev = prov.create("dataset", project=project, user=lead, data={
            **base, "name": fake(f"{t} raw recordings"), "version_label": f"v{n + 1}",
            "checksum": "sha256:" + f"{n + 1}a" * 32, "previous_version": prev.pk if prev else None})  # fmt: skip
        sets.append(prev)
    analyses, results = [], []
    for n, name in enumerate(("Primary model", "Sensitivity check")):
        ran_by = rng.choice(actors)
        a = prov.create("analysis", project=project, user=ran_by, data={
            "title": fake(f"{t} {name.lower()}"), "description": "Invented analysis (FAKE).",
            "code_repo_url": f"https://git.example.invalid/{key}-analysis", "code_commit": FAKE_COMMIT,
            "datasets": [sets[-1].pk] if n else [s.pk for s in sets], "ran_by": ran_by.pk})  # fmt: skip
        analyses.append(a)
        fig = upload(project, ran_by, f"{key}-result-{n + 1}.png", PNG_BYTES, "image/png")
        results.append(prov.create("result", project=project, user=ran_by, data={
            "title": fake(f"{t} result {n + 1}"), "summary": "An invented effect (FAKE).",
            "analysis": a.pk, "attachments": [fig.pk]}))  # fmt: skip
    if key in STUDY:
        prov.create("manuscript", project=project, user=lead, data={
            "title": fake(f"{t} paper"), "url": f"https://overleaf.example.invalid/{key}",
            "status": STUDY[key], "results": [r.pk for r in results]})  # fmt: skip
    for title, why in (
        ("Exclude noisy sessions", "Signal quality was poor"),
        ("Use the stricter threshold", "Fewer false alarms"),
    ):
        prov.create("decision", project=project, user=lead, data={
            "title": fake(title), "rationale": f"{why} (FAKE).", "decided_on": c.today - datetime.timedelta(days=rng.randint(5, 200)),
            "analyses": [analyses[0].pk], "datasets": [sets[0].pk],
            "supporting_documents": [doc_list[1].pk]})  # fmt: skip
    for title, status in (
        ("Methods check", "approved"),
        ("Stats review", rng.choice(["requested", "in_review", "changes_requested"])),
    ):
        prov.create("review", project=project, user=lead, data={
            "title": fake(title), "status": status, "reviewer": pi.pk, "notes": "Invented review (FAKE).",
            "due_date": c.today + datetime.timedelta(days=rng.randint(-10, 30))})  # fmt: skip
    prov.create("external", project=project, user=lead, data={
        "title": fake(f"{t} poster"), "type": "poster", "date": c.today - datetime.timedelta(days=90),
        "place": "Example Conference Centre (FAKE)", "url": f"https://posters.example.invalid/{key}"})  # fmt: skip
    if key in HUMAN:
        prov.update_recruitment_plan(
            project=project,
            user=lead,
            data={"target_enrolment": 60, "notes": "Fake target (FAKE)."},
        )
        for n, (st, count) in enumerate(
            (("screened", 30), ("enrolled", 22), ("completed", 12), ("withdrawn", 3))
        ):
            prov.create("recruitment", project=project, user=lead, data={
                "entry_date": c.today - datetime.timedelta(days=100 - n * 20), "status": st, "count": count})  # fmt: skip
    if key in FUNDERS:
        funder, amount, status = FUNDERS[key]
        prov.create("funding", project=project, user=pi, data={
            "funder": funder, "program": "Operating grant (FAKE)", "award_number": f"FAKE-{key.upper()}-01",
            "amount": amount, "spent": amount * 0.4 if status == "active" else 0, "status": status,
            "start_date": c.today - datetime.timedelta(days=300), "end_date": c.today + datetime.timedelta(days=800),
            "report_due": c.today + datetime.timedelta(days=45), "holder": pi.pk})  # fmt: skip
    if key in ("sleep", "ageing", "fmri"):
        dmp.save_plan(project=project, user=lead, data={
            "data_description": f"{t} recordings and scores (FAKE).", "collection": "Collected in the lab (FAKE).",
            "storage": "Lab secure drive, members only (FAKE).", "preservation": "Kept 7 years (FAKE).",
            "sharing": "Coded data on request (FAKE).", "last_reviewed": c.today - datetime.timedelta(days=60)})  # fmt: skip
        if key == "sleep":
            dmp.approve_plan(project=project, user=pi)


def seed_papers(c):
    staff = [c.people[k] for k, r in c.roles.items() if r != "viewer"]
    made = []
    for i, (title, year, venue) in enumerate(PAPERS):
        by = staff[i % len(staff)]
        made.append(papers.create_paper(c.lab, user=by, data={
            "title": fake(title), "authors": ["Example, Alex", "Sample, Sam", "Invented, Ida"], "year": year,
            "venue": venue, "doi": f"10.0000/fake.{i + 1:03d}", "url": f"https://papers.example.invalid/{i + 1}",
            "abstract": "An invented abstract for a demo lab (FAKE)."}))  # fmt: skip
    for i in range(45):
        papers.add_note(made[i % len(made)], author=rng.choice(staff), body=fake(rng.choice(NOTES)))


def seed_notebooks(c):
    for key in ("priya", "tomas", "hana", "aisha", "noah", "liam"):  # personal notebooks
        for n in range(2):
            notebook.create_entry(lab=c.lab, user=c.people[key], data={
                "title": fake(f"Bench notes {n + 1}"), "entry_date": c.today - datetime.timedelta(days=rng.randint(1, 80)),
                "body": "Invented notes for the demo (FAKE)."})  # fmt: skip
    for key in ("sleep", "fmri", "mouse", "ageing"):  # shared project notebooks
        for n in range(3):
            who = rng.choice(c.actors(key))
            entry = notebook.create_entry(lab=c.lab, user=who, project=c.projects[key], data={
                "title": fake(f"{TOPIC[key]} session log {n + 1}"),
                "entry_date": c.today - datetime.timedelta(days=rng.randint(1, 120)),
                "body": "Session went as planned. Invented text (FAKE)."})  # fmt: skip
            if n == 0:
                notebook.lock_entry(entry, user=who)


def seed_comments(c):
    base = f"/labs/{c.lab.pk}/projects"
    for key in ("sleep", "fmri", "mouse", "ageing", "grant", "crowding"):
        project = c.projects[key]
        a, b = rng.sample(c.actors(key), 2)
        PageComment.objects.create(
            lab=c.lab, project=project, author=a, path=f"{base}/{project.pk}/tasks",
            page_label="Tasks", quote="", body=fake(f"{rng.choice(COMMENTS)} {c.name(b)}"),
        )  # fmt: skip


def seed_participants(c):
    project = c.projects["ageing"]
    lead, helper, coord = c.people["aisha"], c.people["ravi"], c.people["coordinator"]
    part.seed_reasons(c.lab)
    reason = {
        k: StatusReason.objects.for_lab(c.lab).filter(kind=k, active=True).order_by("label").first()
        for k in ("missing", "excluded", "not_applicable")
    }  # fmt: skip
    for name, cat in (("Baseline session", "session"), ("Sleep diary", "questionnaire"),
                      ("Cognitive scoring", "scoring"), ("Interview transcript", "transcript")):  # fmt: skip
        part.create_component(project, user=lead, data={"name": name, "category": cat})
    comps = list(
        Component.objects.for_lab(c.lab).filter(project=project).order_by("order", "created_at")
    )
    statuses = (
        ["active"] * 26
        + ["completed"] * 6
        + ["enrolled"] * 3
        + ["screened"] * 2
        + ["withdrawn"] * 2
        + ["ineligible"]
    )
    rows = [
        {"code": f"FAKE-P{i + 1:03d}", "group": ("Control", "Poor sleep", "Typical")[i % 3], "cohort": "Wave 3",
         "enrolment_status": s, "enrolled_on": c.today - datetime.timedelta(days=200 - i * 4)}
        for i, s in enumerate(statuses)
    ]  # fmt: skip
    people = part.create_participants(project, user=coord, rows=rows)
    for p in people:
        if p.enrolment_status in ("withdrawn", "ineligible"):
            continue
        for comp in comps:
            st = rng.choice(PEOPLE_CELLS)
            data = {"status": st, "owner": rng.choice([lead, helper, coord]).pk}
            if st in reason:
                data["reason"] = reason[st].pk
            if st == "complete":
                data["collected_on"] = c.today - datetime.timedelta(days=rng.randint(2, 150))
            cell = part.set_cell(p, comp, user=helper, data=data)
            if st == "complete" and rng.random() < 0.3:
                part.add_file(
                    cell,
                    user=helper,
                    data={
                        "url": f"https://files.example.test/ageing/{p.code}/{comp.key}.csv",
                        "title": f"{p.code} {comp.name} (FAKE)",
                        "role": "raw",
                    },
                )
    part.update_participant(
        people[-4],
        user=coord,
        data={"enrolment_status": "withdrawn", "notes": "Withdrew after visit two (FAKE)"},
    )
    part.set_archived(people[-1], True, user=coord)
    rule = prule.save_rule(
        project,
        lead,
        data={
            "name": "Complete baseline (FAKE)",
            "description": "Fake rule",
            "spec": {"requires": ["baseline-session"]},
        },
    )
    prule.lock_set(project, lead, rule=rule, name="Wave 3 baseline set (FAKE)")
