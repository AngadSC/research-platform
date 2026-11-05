"""Outbound email (D61): templates, recipients, retries and the log line."""

import logging
from unittest import mock

import pytest
from allauth.core import context as allauth_context
from anymail.exceptions import AnymailAPIError
from celery.exceptions import Retry
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.test import APIClient

from core.auth import AccountAdapter
from core.email import send_email, send_email_task
from core.models import Notification, NotificationKind
from core.notifications import notify
from labs.models import LabRole
from labs.services import create_invite

pytestmark = pytest.mark.django_db

SECRET = "s3cret-context-value"


def assert_multipart(msg, subject_part):
    assert subject_part in msg.subject and "\n" not in msg.subject
    assert msg.body.strip()
    assert [a[1] for a in msg.alternatives] == ["text/html"]


def test_sends_one_message_per_recipient_with_html(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        send_email("notification", ["a@x.org", "b@x.org"], {"title": "T", "body": "B"})
    assert [m.to for m in mail.outbox] == [["a@x.org"], ["b@x.org"]]
    assert_multipart(mail.outbox[0], "T")


def test_not_sent_before_commit(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        send_email("notification", "a@x.org", {"title": "T", "body": "B"})
    assert mail.outbox == [] and len(callbacks) == 1


def test_invite_email(make_lab, make_user, join, django_capture_on_commit_callbacks):
    lab, pi = make_lab("Lab X"), make_user()
    join(pi, lab, LabRole.PI)
    with django_capture_on_commit_callbacks(execute=True):
        create_invite(lab=lab, by=pi, email="new@x.org", role="member")
    (msg,) = mail.outbox
    assert msg.to == ["new@x.org"]
    assert_multipart(msg, "invited to Lab X")
    assert "/invite/" in msg.body and "/invite/" in msg.alternatives[0][0]


def test_allauth_verification_and_reset_use_service(django_capture_on_commit_callbacks):
    adapter = AccountAdapter()
    with django_capture_on_commit_callbacks(execute=True):
        adapter.send_mail(
            "account/email/email_confirmation", "v@x.org", {"activate_url": "http://f/k"}
        )
        adapter.send_mail(
            "account/email/password_reset_key", "v@x.org", {"password_reset_url": "http://f/r"}
        )
    verify, reset = mail.outbox
    assert_multipart(verify, "Confirm your email")
    assert "http://f/k" in verify.body
    assert_multipart(reset, "Reset your password")
    assert "http://f/r" in reset.body


def test_other_allauth_email_uses_account_notice(make_user, django_capture_on_commit_callbacks):
    user = make_user()
    request = RequestFactory().get("/")
    with django_capture_on_commit_callbacks(execute=True), allauth_context.request_context(request):
        AccountAdapter().send_mail("account/email/password_changed", user.email, {"user": user})
    (msg,) = mail.outbox
    assert msg.to == [user.email]
    assert msg.alternatives and msg.body.strip()


def test_ethics_and_retention_emails(make_lab, make_user, join, django_capture_on_commit_callbacks):
    lab, user = make_lab("L"), make_user()
    join(user, lab, LabRole.MEMBER)
    kw = {"lab": lab, "recipient": user, "title": "Hello", "body": "Body text", "dedupe_key": "k"}
    ethics = {"kind": NotificationKind.ETHICS_EXPIRY, "email_template": "ethics_reminder"}
    with django_capture_on_commit_callbacks(execute=True):
        assert notify(**kw, **ethics)
        assert not notify(**kw, **ethics)  # same dedupe key: no second email
        assert notify(
            **{**kw, "dedupe_key": "k2"},
            kind=NotificationKind.RETENTION_DUE,
            email_template="retention_notice",
        )
    assert [m.to for m in mail.outbox] == [[user.email]] * 2
    for m in mail.outbox:
        assert_multipart(m, "Hello")


# ---------------------------------------------------------------- retries and log


@pytest.mark.parametrize(
    "exc", [AnymailAPIError("x", status_code=s) for s in (429, 503)] + [ConnectionError("down")]
)
def test_temporary_failure_retries_with_backoff(exc):
    with (
        mock.patch("core.email._render_and_send", side_effect=exc),
        mock.patch.object(send_email_task, "retry", side_effect=Retry()) as retry,
    ):
        send_email_task.apply(args=["notification", "a@x.org", {}])
    assert retry.call_args.kwargs["countdown"] == 30


@pytest.mark.parametrize(
    "exc",
    [AnymailAPIError("x", status_code=400), AnymailAPIError("x", status_code=401), ValueError("t")],
)
def test_permanent_failure_does_not_retry(exc):
    with (
        mock.patch("core.email._render_and_send", side_effect=exc),
        mock.patch.object(send_email_task, "retry") as retry,
    ):
        assert send_email_task.apply(args=["notification", "a@x.org", {}]).get() is False
    retry.assert_not_called()


def test_log_line_has_recipient_template_status_attempt_but_no_body(caplog):
    ctx = {"title": SECRET, "body": SECRET}
    with caplog.at_level(logging.INFO, logger="core.email"):
        send_email_task.apply(args=["notification", "a@x.org", ctx]).get()
    (record,) = [r for r in caplog.records if r.name == "core.email"]
    text = record.getMessage()
    assert "to=a@x.org" in text and "template=notification" in text
    assert "status=sent" in text and "attempt=1" in text
    assert SECRET not in text and SECRET in mail.outbox[0].body


# ---------------------------------------------------------------- export notice


@pytest.fixture
def export_world(make_lab, make_user, make_project, join):
    lab = make_lab("Lab E")
    pi, pi2, admin = make_user(), make_user(), make_user()
    join(pi, lab, LabRole.PI)
    join(pi2, lab, LabRole.PI)
    join(admin, lab, LabRole.LAB_ADMIN)
    return lab, make_project(lab, "Proj E"), pi, pi2, admin


def export(project, user):
    client = APIClient()
    client.force_login(user)
    url = reverse("provenance:export", kwargs={"lab_id": project.lab_id, "project_id": project.pk})
    return client.post(url, {}, format="json")


def test_non_pi_export_notifies_every_pi(export_world, django_capture_on_commit_callbacks):
    lab, project, pi, pi2, admin = export_world
    with django_capture_on_commit_callbacks(execute=True):
        assert export(project, admin).status_code == 200
    notes = Notification.objects.for_lab(lab).filter(kind=NotificationKind.PROJECT_EXPORTED)
    assert {n.recipient for n in notes} == {pi, pi2}
    assert sorted(m.to[0] for m in mail.outbox) == sorted([pi.email, pi2.email])
    assert_multipart(mail.outbox[0], "Project exported: Proj E")


def test_pi_export_notifies_nobody(export_world, django_capture_on_commit_callbacks):
    lab, project, pi, pi2, admin = export_world
    with django_capture_on_commit_callbacks(execute=True):
        assert export(project, pi).status_code == 200
    assert not Notification.objects.for_lab(lab).filter(kind=NotificationKind.PROJECT_EXPORTED)
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind,emailed",
    [
        ("ethics_expiry", True),
        ("retention_due", True),
        ("project_exported", True),
        ("integration_issue", True),
        ("task_assigned", False),
        ("task_unassigned", False),
        ("invite_accepted", False),
    ],
)
def test_only_actionable_kinds_are_emailed(
    kind, emailed, make_lab, make_user, mailoutbox, django_capture_on_commit_callbacks
):
    """D71: every kind gets an in-app notification; only EMAIL_KINDS also get an email."""
    from core.notifications import notify

    lab, user = make_lab(), make_user()
    with django_capture_on_commit_callbacks(execute=True):
        assert notify(lab=lab, recipient=user, kind=kind, title="t", dedupe_key=f"k:{kind}")
    assert (len(mailoutbox) == 1) is emailed
