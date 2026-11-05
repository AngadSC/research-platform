"""D31 upgrade: composite (fk, lab_id) FKs and M2M triggers (Postgres only, D15).
Fails loudly, naming table, rows and both lab ids, if existing data is inconsistent."""

from django.db import migrations

from core.lab_db import LabForeignKey as FK
from core.lab_db import LabM2MTrigger as M2M

P, D, DR = "projects_project", "documents_document", "documents_documentrevision"
A, E = "documents_attachment", "ethics_ethicsapproval"
DS, AN, R = "provenance_datasetrecord", "provenance_analysis", "provenance_result"

# (child table, column, parent table, on_delete)
FKS = [
    ("projects_projectmembership", "project_id", P, "CASCADE"),
    ("projects_projectdeadline", "project_id", P, "CASCADE"),
    ("projects_task", "project_id", P, "CASCADE"),
    ("documents_document", "project_id", P, "CASCADE"),
    ("documents_documentrevision", "document_id", D, "CASCADE"),
    ("documents_documentrevision", "restored_from_id", DR, "SET_NULL"),
    ("documents_attachment", "project_id", P, "CASCADE"),
    ("documents_attachment", "ethics_approval_id", E, "PROTECT"),
    ("provenance_datasetrecord", "project_id", P, "CASCADE"),
    ("provenance_datasetrecord", "previous_version_id", DS, "SET_NULL"),
    ("provenance_analysis", "project_id", P, "CASCADE"),
    ("provenance_analysis", "code_attachment_id", A, "PROTECT"),
    ("provenance_result", "project_id", P, "CASCADE"),
    ("provenance_result", "analysis_id", AN, "PROTECT"),
    ("provenance_decision", "project_id", P, "CASCADE"),
    ("provenance_manuscriptlink", "project_id", P, "CASCADE"),
]

# (through table, (left table, column), (right table, column)); provenance links also need the
# same project, ethics approvals are lab-level.
M2MS = [
    ("provenance_analysis_datasets", (AN, "analysis_id"), (DS, "datasetrecord_id")),
    ("provenance_result_attachments", (R, "result_id"), (A, "attachment_id")),
    (
        "provenance_decision_supporting_documents",
        ("provenance_decision", "decision_id"),
        (D, "document_id"),
    ),
    (
        "provenance_decision_supporting_attachments",
        ("provenance_decision", "decision_id"),
        (A, "attachment_id"),
    ),
    ("provenance_decision_analyses", ("provenance_decision", "decision_id"), (AN, "analysis_id")),
    ("provenance_decision_results", ("provenance_decision", "decision_id"), (R, "result_id")),
    (
        "provenance_decision_datasets",
        ("provenance_decision", "decision_id"),
        (DS, "datasetrecord_id"),
    ),
    (
        "provenance_manuscriptlink_results",
        ("provenance_manuscriptlink", "manuscriptlink_id"),
        (R, "result_id"),
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("labs", "0001_initial"),
        ("projects", "0002_projectdeadline_task"),
        ("documents", "0004_alter_attachment_ethics_approval"),
        ("provenance", "0001_initial"),
        ("ethics", "0003_restricted"),
    ]

    operations = (
        [FK(*fk) for fk in FKS]
        + [M2M(t, l, r, "project_id", "project_id") for t, l, r in M2MS]
        + [M2M("ethics_ethicsapproval_projects", (E, "ethicsapproval_id"), (P, "project_id"))]
    )
