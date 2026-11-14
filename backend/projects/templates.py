"""Project templates (D235): a starting plan that is copied once into a new project. The numbers
are days after the project's start date. Plain data, so adding a template is one more entry."""

from datetime import timedelta

from django.utils import timezone

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
    "experiment": {
        "tasks": [
            ("Write your research question and hypothesis", 7),
            ("Design the experiment and the materials", 21),
            ("Submit your ethics application", 35),
            ("Run a small pilot and fix problems", 60),
            ("Recruit participants", 75),
            ("Run the sessions", 120),
            ("Clean the data and remove anything that identifies people", 135),
            ("Run the analysis", 155),
            ("Write up the findings", 185),
        ],
        "deadlines": [
            ("Ethics application submitted", 35, HIGH),
            ("Pilot finished", 60, MEDIUM),
            ("Last session run", 120, HIGH),
            ("First draft of the paper", 185, MEDIUM),
        ],
        "reviews": ["Check the data contains nothing that identifies people"],
        "not_needed": [],
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
    for title, days, priority in sorted(plan["deadlines"], key=lambda d: d[1]):
        ProjectDeadline.objects.create(
            project=project, title=title, due_date=due(days), priority=priority
        )
    for title in plan["reviews"]:
        ReviewItem.objects.create(project=project, title=title, created_by=user)
    if plan["not_needed"]:
        project.workflow_marked_done = plan["not_needed"]
        project.save(update_fields=["workflow_marked_done", "updated_at"])
