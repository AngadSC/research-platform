import pytest
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, override_settings

from audit.models import AuditAction, AuditEvent, AuditImmutableError
from audit.services import record

pytestmark = pytest.mark.django_db


@pytest.fixture
def event(make_lab, make_project, make_user):
    lab = make_lab()
    project = make_project(lab, "Proj")
    return record(AuditAction.PROJECT_CREATED, actor=make_user(), lab=lab, target=project)


def test_record_fills_target_fields(event):
    event.refresh_from_db()
    assert event.target_type == "projects.Project"
    assert event.target_repr == "Proj" and event.project_id == event.target_id
    assert event.occurred_at is not None


def test_record_rejects_bad_input(make_lab):
    with pytest.raises(ValueError):
        record("nope.nope", actor=None, lab=make_lab())
    with pytest.raises(ValueError):
        record(AuditAction.LAB_CREATED, actor=None, lab=None)
    assert record(AuditAction.AUTH_LOGIN, actor=None, lab=None).lab is None


def test_record_request_ip_and_trusted_proxy():
    req = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", HTTP_USER_AGENT="ua"
    )
    assert record(AuditAction.AUTH_LOGIN, actor=None, lab=None, request=req).ip == "10.0.0.1"
    with override_settings(TRUSTED_PROXY_COUNT=1):
        assert record(AuditAction.AUTH_LOGIN, actor=None, lab=None, request=req).ip == "5.6.7.8"


def test_model_level_update_and_delete_rejected(event):
    event.action = AuditAction.LAB_UPDATED
    with pytest.raises(AuditImmutableError):
        event.save()
    with pytest.raises(AuditImmutableError):
        event.delete()
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.all().update(actor_label="x")
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.all().delete()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="trigger is Postgres-only")
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_auditevent SET actor_label = 'x'",
        "DELETE FROM audit_auditevent",
        "TRUNCATE audit_auditevent",
    ],
)
def test_trigger_rejects_raw_sql(event, sql):
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute(sql)
