"""Outgoing webhooks (D241): secrets stay hidden, addresses are checked, only chosen events go out
and a message is signed and holds no research details. Every HTTP call is faked."""

import hashlib
import hmac
import json
import logging

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from audit.services import record
from integrations import http, webhooks
from integrations.models import Webhook
from integrations.tests.fake import response

pytestmark = pytest.mark.django_db

SECRET_PATH = "/hooks/catch/123/SECRETPATH/"
URL = f"https://hooks.example.org{SECRET_PATH}"
SLACK = "https://hooks.slack.com/services/T0/B0/SECRETPATH"


@pytest.fixture
def lab(lab_users):
    return lab_users[0]


@pytest.fixture
def admin(lab_users):
    client = APIClient()
    client.force_authenticate(lab_users[1]["lab_admin"])
    return client


def url_for(lab):
    return f"/api/labs/{lab.pk}/webhooks/"


def make(lab, user, *, kind="webhook", url=URL, events=("project.created",)):
    return webhooks.create(lab=lab, user=user, name="Hook", kind=kind, url=url, events=list(events))


def test_the_address_and_secret_are_encrypted_and_never_shown_again(lab, admin, transport):
    body = {"name": "Zap", "kind": "webhook", "url": URL, "events": ["project.created"]}
    made = admin.post(url_for(lab), body, format="json")
    assert made.status_code == 201
    secret = made.json()["secret"]
    assert "url" not in made.json() and made.json()["host"] == "hooks.example.org"

    hook = Webhook.objects.for_lab(lab).get()
    assert "SECRETPATH" not in hook.url_ct and secret not in hook.secret_ct
    assert hook.url() == URL and hook.secret() == secret

    listed = admin.get(url_for(lab))
    assert "SECRETPATH" not in listed.content.decode() and secret not in listed.content.decode()
    events = [e["value"] for e in listed.json()["events"]]
    assert "project.created" in events
    audit = AuditEvent.objects.get(action=AuditAction.WEBHOOK_CREATED)
    assert "SECRETPATH" not in json.dumps(audit.metadata) and audit.metadata["host"]


@pytest.mark.parametrize(
    ("kind", "bad"),
    [
        ("webhook", "http://hooks.example.org/x"),
        ("webhook", "https://hooks.example.org:8443/x"),
        ("webhook", "https://10.0.0.1/x"),
        ("webhook", "https://user:pw@hooks.example.org/x"),
        ("webhook", "https://hooks.example.org/x?token=abc"),
        ("slack", "https://hooks.slack.com.evil.example/services/x"),
        ("slack", "https://hooks.example.org/services/x"),
    ],
)
def test_bad_addresses_are_refused(lab, admin, transport, kind, bad):
    resp = admin.post(
        url_for(lab),
        {"name": "x", "kind": kind, "url": bad, "events": ["project.created"]},
        format="json",
    )
    assert resp.status_code == 400 and "url" in resp.json()
    assert not Webhook.objects.for_lab(lab).exists()


def test_an_address_resolving_to_a_private_ip_is_refused(lab, admin, transport, monkeypatch):
    monkeypatch.setattr(http, "_resolve", lambda host: ["169.254.169.254"])
    resp = admin.post(
        url_for(lab),
        {"name": "x", "kind": "webhook", "url": URL, "events": ["project.created"]},
        format="json",
    )
    assert resp.status_code == 400


def test_a_message_is_signed_and_holds_no_titles(lab, lab_users, transport, make_project):
    hook, secret = make(lab, lab_users[1]["pi"])
    transport.on("POST", URL, response(200, {}))
    project = make_project(lab, name="Confidential trial XYZ")
    event = record(AuditAction.PROJECT_CREATED, actor=lab_users[1]["pi"], lab=lab, target=project)
    webhooks.deliver.apply(
        args=[
            str(hook.pk),
            str(lab.pk),
            webhooks._message(event.action, lab.pk, lab.name, project.pk, event.pk),
        ]
    )

    sent = transport.sent("POST", URL)[0]
    body = sent["data"]
    timestamp, digest = (
        p.split("=")[1] for p in sent["headers"]["X-LabBench-Signature"].split(",")
    )
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    assert digest == expected.hexdigest()
    assert b"Confidential" not in body and json.loads(body)["event"] == "project.created"
    assert Webhook.objects.for_lab(lab).get().last_status == 200


def test_only_chosen_events_of_this_lab_are_queued(
    lab, lab_users, make_lab, monkeypatch, make_project, django_capture_on_commit_callbacks
):
    hook, _ = make(lab, lab_users[1]["pi"], events=["project.created"])
    make(lab, lab_users[1]["pi"], events=["meeting.created"])  # another event: not sent
    other = make_lab(name="Other lab")  # another lab: never sent
    make(other, lab_users[1]["pi"], events=["project.created"])
    queued = []
    monkeypatch.setattr(webhooks.deliver, "delay", lambda *a: queued.append(a))

    project = make_project(lab)
    with django_capture_on_commit_callbacks(execute=True):
        record(AuditAction.PROJECT_CREATED, actor=lab_users[1]["pi"], lab=lab, target=project)
        record(AuditAction.DATASET_CREATED, actor=lab_users[1]["pi"], lab=lab)  # not chosen

    assert [q[0] for q in queued] == [str(hook.pk)]
    assert queued[0][2]["url"].endswith(f"/projects/{project.pk}")


def test_inactive_webhook_is_not_sent(lab, lab_users, transport):
    hook, _ = make(lab, lab_users[1]["pi"])
    Webhook.objects.for_lab(lab).update(is_active=False)
    webhooks.deliver.apply(args=[str(hook.pk), str(lab.pk), {"event": "x", "id": "1"}])
    assert transport.calls == []


def test_slack_text_escapes_markup(lab, lab_users, transport):
    hook, _ = make(lab, lab_users[1]["pi"], kind="slack", url=SLACK)
    lab.name = "<!channel> & co"
    transport.on("POST", SLACK, response(200, {}))
    webhooks._post(hook, webhooks._message("project.created", lab.pk, lab.name, None, hook.pk))
    text = json.loads(transport.calls[-1][2]["data"])["text"]
    assert "<!channel>" not in text and "&lt;!channel&gt; &amp; co" in text
    assert "X-LabBench-Signature" not in transport.calls[-1][2]["headers"]


@pytest.mark.parametrize(
    ("status", "retried"), [(500, True), (429, True), (400, False), (302, False)]
)
def test_only_temporary_failures_retry(lab, lab_users, transport, monkeypatch, status, retried):
    hook, _ = make(lab, lab_users[1]["pi"])
    transport.on(
        "POST", URL, response(status, {}, headers={"Location": "https://169.254.169.254/"})
    )
    calls = []

    def retry(*a, **kw):
        calls.append(kw)
        raise webhooks.deliver.MaxRetriesExceededError

    monkeypatch.setattr(webhooks.deliver, "retry", retry)
    result = webhooks.deliver.apply(
        args=[
            str(hook.pk),
            str(lab.pk),
            webhooks._message("project.created", lab.pk, lab.name, None, hook.pk),
        ]
    )
    assert bool(calls) is retried and result.failed() is retried
    assert len(transport.sent("POST", URL)) == 1  # a redirect is not followed
    assert Webhook.objects.for_lab(lab).get().last_status == status


def test_a_network_failure_is_recorded_as_no_answer(lab, lab_users, transport, monkeypatch):
    hook, _ = make(lab, lab_users[1]["pi"])
    monkeypatch.setattr(http, "_resolve", lambda host: ["10.0.0.1"])  # DNS changed since saving
    assert (
        webhooks._post(hook, webhooks._message("project.created", lab.pk, lab.name, None, hook.pk))
        is None
    )
    assert transport.calls == []  # refused before any request


def test_logs_never_contain_the_secret_path(lab, lab_users, transport, caplog):
    hook, _ = make(lab, lab_users[1]["pi"])
    transport.on("POST", URL, response(200, {}))
    with caplog.at_level(logging.INFO, logger="integrations.http"):
        webhooks._post(hook, webhooks._message("project.created", lab.pk, lab.name, None, hook.pk))
    assert "hooks.example.org" in caplog.text and "SECRETPATH" not in caplog.text


def test_rotation_reencrypts_addresses_and_secrets(lab, lab_users, settings):
    _, secret = make(lab, lab_users[1]["pi"])
    before = Webhook.objects.for_lab(lab).get().url_ct
    assert webhooks.rotate_keys() == 1
    row = Webhook.objects.for_lab(lab).get()
    assert row.url_ct != before and row.url() == URL and row.secret() == secret


def test_events_cannot_be_anything_outside_the_catalogue(lab, admin, transport):
    resp = admin.post(
        url_for(lab),
        {"name": "x", "kind": "webhook", "url": URL, "events": ["audit_log.viewed"]},
        format="json",
    )
    assert resp.status_code == 400 and "events" in resp.json()
