"""D31 at the database level: composite lab FKs and M2M triggers (Postgres only, D15)."""

import uuid

import pytest
from django.apps import apps
from django.db import DatabaseError, IntegrityError, connection, transaction

from core import lab_db
from core.tenancy import LabScopedModel
from provenance.models import Analysis, DatasetRecord

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres-only constraints"),
]


def lab_models():
    return [m for m in apps.get_models() if issubclass(m, LabScopedModel)]


def sql(query, *params):
    """Run raw SQL that bypasses save(); constraints are made immediate so they fire here."""
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute(query, params)


@pytest.fixture
def world(make_lab, make_project, make_user):
    user = make_user()
    lab_a, lab_b = make_lab("A"), make_lab("B")
    pa, pa2, pb = make_project(lab_a), make_project(lab_a, "P2"), make_project(lab_b)
    ds = {"version_label": "v1", "created_by": user}
    ran = {
        "ran_by": user,
        "ran_at": "2030-01-01T00:00:00Z",
        "code_repo_url": "https://example.com/x.git",
        "code_commit": "abc1234",
    }
    return {
        "lab_a": lab_a,
        "lab_b": lab_b,
        "pa": pa,
        "pa2": pa2,
        "pb": pb,
        "dataset": DatasetRecord.objects.create(lab=lab_a, project=pa, name="d", **ds),
        "dataset_p2": DatasetRecord.objects.create(lab=lab_a, project=pa2, name="d", **ds),
        "analysis": Analysis.objects.create(lab=lab_a, project=pa, title="a", **ran),
    }


def test_raw_update_cannot_change_lab_of_a_linked_child(world, make_user):
    from projects.models import Task

    task = Task.objects.create(
        lab=world["lab_a"], project=world["pa"], title="t", created_by=make_user()
    )
    with pytest.raises(IntegrityError):
        sql("UPDATE projects_task SET lab_id = %s WHERE id = %s", world["lab_b"].pk, task.pk)


def test_raw_update_cannot_point_at_other_lab_parent(world):
    with pytest.raises(IntegrityError):  # nullable self-FK too
        sql(
            "UPDATE provenance_datasetrecord SET previous_version_id = %s WHERE id = %s",
            world["dataset"].pk,
            world["dataset"].pk,
        )
        sql("UPDATE provenance_datasetrecord SET lab_id = %s", world["lab_b"].pk)


def test_raw_insert_with_parent_in_other_lab_fails(world, make_user):
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO projects_task (id, lab_id, created_at, updated_at, project_id, title,"
            " description, status, created_by_id) VALUES (%s, %s, now(), now(), %s, 't', '',"
            " 'todo', %s)",
            uuid.uuid4(),
            world["lab_b"].pk,
            world["pa"].pk,
            make_user().pk,
        )


def test_m2m_row_across_labs_fails(world, make_user):
    other = DatasetRecord.objects.create(
        lab=world["lab_b"], project=world["pb"], name="o", version_label="v1",
        created_by=make_user(),
    )  # fmt: skip
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO provenance_analysis_datasets (analysis_id, datasetrecord_id)"
            " VALUES (%s, %s)",
            world["analysis"].pk,
            other.pk,
        )


def test_m2m_row_across_projects_fails(world):
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO provenance_analysis_datasets (analysis_id, datasetrecord_id)"
            " VALUES (%s, %s)",
            world["analysis"].pk,
            world["dataset_p2"].pk,
        )


def test_m2m_row_in_same_project_is_allowed(world):
    sql(
        "INSERT INTO provenance_analysis_datasets (analysis_id, datasetrecord_id) VALUES (%s, %s)",
        world["analysis"].pk,
        world["dataset"].pk,
    )


def _constraint_exists(table, column, parent):
    with connection.cursor() as cur:
        cur.execute(
            """SELECT 1 FROM pg_constraint c
               WHERE c.contype = 'f' AND c.conrelid = %s::regclass AND c.confrelid = %s::regclass
                 AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
                      FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
                     = ARRAY[%s, 'lab_id']
                 AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
                      FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
                      JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum)
                     = ARRAY['id', 'lab_id']""",
            [table, parent, column],
        )
        return cur.fetchone() is not None


def _trigger_exists(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass AND tgname = %s"
            " AND tgtype & 4 = 4 AND tgtype & 16 = 16",  # INSERT and UPDATE
            [table, lab_db.trigger_name(table)],
        )
        return cur.fetchone() is not None


def test_every_lab_to_lab_link_has_a_db_constraint():
    """Fails for a new LabScopedModel FK or M2M to another LabScopedModel that has no composite
    FK / trigger. Add `LabForeignKey` / `LabM2MTrigger` (core/lab_db.py) in a migration."""
    missing, seen = [], 0
    for model in lab_models():
        for f in model._meta.concrete_fields:
            if f.many_to_one and issubclass(f.related_model, LabScopedModel):
                seen += 1
                if not _constraint_exists(
                    model._meta.db_table, f.column, f.related_model._meta.db_table
                ):
                    missing.append(f"FK {model._meta.label}.{f.name}")
        for f in model._meta.many_to_many:
            if issubclass(f.related_model, LabScopedModel):
                seen += 1
                if not _trigger_exists(f.remote_field.through._meta.db_table):
                    missing.append(f"M2M {model._meta.label}.{f.name}")
    assert seen >= 20, "introspection found suspiciously few links"
    assert not missing, f"no lab DB constraint for: {missing}"


def test_migration_check_names_table_rows_and_labs(world, make_user):
    from projects.models import Task

    task = Task.objects.create(
        lab=world["lab_a"], project=world["pa"], title="t", created_by=make_user()
    )
    op = lab_db.LabForeignKey("projects_task", "project_id", "projects_project", "CASCADE")
    fk = lab_db.fk_name("projects_task", "project_id")
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # no pending trigger events before ALTER
        cur.execute(f'ALTER TABLE projects_task DROP CONSTRAINT "{fk}"')
        cur.execute(
            "UPDATE projects_task SET lab_id = %s WHERE id = %s", [world["lab_b"].pk, task.pk]
        )
        with pytest.raises(DatabaseError) as exc, transaction.atomic():
            cur.execute(op.forwards_sql()[0])
    msg = str(exc.value)
    assert "projects_task.project_id" in msg and str(task.pk) in msg
    assert str(world["lab_a"].pk) in msg and str(world["lab_b"].pk) in msg


@pytest.fixture
def folders(world, make_user):
    from documents.models import Document, Folder

    user = make_user()
    lab = world["lab_a"]
    return {
        "a": Folder.objects.create(lab=lab, project=world["pa"], name="a", created_by=user),
        "other_project": Folder.objects.create(
            lab=lab, project=world["pa2"], name="b", created_by=user
        ),
        "doc": Document.objects.create(
            lab=lab, project=world["pa"], title="d", created_by=user, updated_by=user
        ),
    }


def test_folder_links_cannot_cross_projects(folders):
    other = folders["other_project"].pk
    with pytest.raises(IntegrityError):
        sql("UPDATE documents_document SET folder_id = %s WHERE id = %s", other, folders["doc"].pk)
    with pytest.raises(IntegrityError):
        sql("UPDATE documents_folder SET parent_id = %s WHERE id = %s", other, folders["a"].pk)


def test_folder_link_inside_a_project_is_allowed(folders):
    sql(
        "UPDATE documents_document SET folder_id = %s WHERE id = %s",
        folders["a"].pk,
        folders["doc"].pk,
    )
