"""Project templates (D235): a starting plan that is copied once into a new project. The numbers
are days after the project's start date. Plain data, so adding a template is one more entry."""

from datetime import timedelta

from django.utils import timezone

from documents.models import Folder
from projects.models import DeadlinePriority, ProjectDeadline, Task
from provenance.models import ReviewItem

HIGH, MEDIUM = DeadlinePriority.HIGH, DeadlinePriority.MEDIUM

TEMPLATES = {
    "honours_thesis": {
        "tasks": [
            ("Agree on a research question with your supervisor", 14),
            ("Finish the training your lab requires", 21),
            ("Write your research proposal", 42),
            ("Submit your ethics application", 60),
            ("Collect your data", 150),
            ("Analyse your data", 185),
            ("Write the first full draft", 215),
            ("Revise the draft using your supervisor's feedback", 240),
            ("Prepare your presentation or poster", 255),
        ],
        "deadlines": [
            ("Research proposal due", 42, HIGH),
            ("Ethics application submitted", 60, HIGH),
            ("Full draft to supervisor", 215, HIGH),
            ("Final thesis due", 250, HIGH),
            ("Thesis presentation", 265, MEDIUM),
        ],
        "reviews": ["Supervisor signs off on the final thesis"],
        "not_needed": [],
    },
    "survey_study": {
        "tasks": [
            ("Write your research questions", 7),
            ("Draft the survey questions", 21),
            ("Submit your ethics application", 35),
            ("Try the survey on a few people and fix problems", 60),
            ("Start recruiting participants", 70),
            ("Close the survey and download the responses", 120),
            ("Clean the data and remove anything that identifies people", 130),
            ("Run the analysis", 150),
            ("Write up the findings", 180),
        ],
        "deadlines": [
            ("Ethics application submitted", 35, HIGH),
            ("Survey opens", 70, MEDIUM),
            ("Survey closes", 120, HIGH),
            ("First draft of the paper", 180, MEDIUM),
        ],
        "reviews": ["Check the survey data contains nothing that identifies people"],
        "not_needed": [],
    },
    "secondary_data_analysis": {
        "tasks": [
            ("Write your question and analysis plan", 14),
            ("Find the dataset and ask for access", 30),
            ("Ask your ethics board if you need an approval or an exemption", 30),
            ("Download the dataset and record where it came from", 45),
            ("Clean and prepare the data", 60),
            ("Run the analysis", 90),
            ("Check that the results can be reproduced", 100),
            ("Write up the findings", 125),
        ],
        "deadlines": [
            ("Data access request sent", 30, MEDIUM),
            ("Analysis finished", 100, HIGH),
            ("First draft of the paper", 125, MEDIUM),
        ],
        "reviews": ["Check the work follows the dataset's terms of use"],
        "not_needed": ["participants"],  # nobody new is recruited
    },
    "thesis_chapter": {
        "tasks": [
            ("Outline the chapter and agree it with your supervisor", 5),
            ("Collect and read the sources you need", 14),
            ("Write the rough first draft", 35),
            ("Add figures, tables and references", 45),
            ("Send the draft to your supervisor", 50),
            ("Revise using the feedback", 70),
            ("Proofread and format the chapter", 80),
        ],
        "deadlines": [
            ("Draft to supervisor", 50, HIGH),
            ("Revised chapter due", 80, HIGH),
        ],
        "reviews": ["Supervisor signs off on the chapter"],
        "not_needed": ["participants"],
        "folders": ["Drafts", "Sources", "Figures and tables", "Feedback"],
    },
    "ra_onboarding": {
        "tasks": [
            ("Meet your supervisor and agree what you will work on", 3),
            ("Finish the training your lab requires", 7),
            ("Get access to the lab's shared files and tools", 7),
            ("Read the lab's guidelines and the project's protocol", 10),
            ("Shadow someone doing the work once", 14),
            ("Do a small task on your own and ask for feedback", 21),
            ("Set up a regular check-in with your supervisor", 21),
            ("Write down your goals for the term", 28),
        ],
        "deadlines": [
            ("Required training finished", 7, HIGH),
            ("First check-in with your supervisor", 14, MEDIUM),
            ("Goals for the term agreed", 28, MEDIUM),
        ],
        "reviews": [],
        "not_needed": ["ethics", "participants", "analysis", "manuscript"],
        "folders": ["Training", "Lab guidelines", "Notes"],
    },
    "conference_poster": {
        "tasks": [
            ("Check the poster size and rules for the conference", 3),
            ("Decide your one main message", 7),
            ("Draft the text and pick the figures", 14),
            ("Make the first version of the poster", 21),
            ("Get feedback from your supervisor and lab", 28),
            ("Revise the poster", 35),
            ("Send the poster to be printed", 40),
            ("Practise your two-minute talk", 45),
        ],
        "deadlines": [
            ("Poster sent to print", 40, HIGH),
            ("Conference", 50, HIGH),
        ],
        "reviews": [],
        "not_needed": ["ethics", "participants"],
        "folders": ["Poster files", "Figures", "Abstract and notes"],
    },
}


def apply(name, project, user) -> None:
    """Fill a new project in. The caller's transaction and audit event cover it. Funding is never
    marked here: only a PI may say anything about a project's funding (D226)."""
    plan = TEMPLATES[name]
    start = project.start_date or timezone.localdate()

    def due(days):
        return start + timedelta(days=days)

    for position, (title, days) in enumerate(plan["tasks"]):
        Task.objects.create(
            project=project, title=title, due_date=due(days), position=position, created_by=user
        )
    for title, days, priority in plan["deadlines"]:
        ProjectDeadline.objects.create(
            project=project, title=title, due_date=due(days), priority=priority
        )
    for title in plan["reviews"]:
        ReviewItem.objects.create(project=project, title=title, created_by=user)
    for name in plan.get("folders", []):
        Folder.objects.create(project=project, name=name, created_by=user)
    if plan["not_needed"]:
        project.workflow_marked_done = plan["not_needed"]
        project.save(update_fields=["workflow_marked_done", "updated_at"])
