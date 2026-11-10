"""Outgoing webhooks for chosen lab events (ARCHITECTURE section 9, D241).

An event is an audit event whose action is in EVENTS. The message says what happened and links
to it; it never holds a title, a person's name or a participant detail, so a lab's admin can't
send research details to an outside service by ticking a box. Delivery goes through
`integrations.http`: https on 443 to public addresses only, the address pinned per request, and
a redirect is never followed for a POST.
"""

import dataclasses
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import urlsplit

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from audit.models import AuditAction, AuditEvent
from integrations import crypto, http
from integrations.models import Webhook, WebhookKind
from integrations.providers import AuthType, Provider
from labs.models import Lab

log = logging.getLogger("integrations.webhooks")

EVENTS = {
    AuditAction.PROJECT_CREATED.value: "A project was created",
    AuditAction.MEMBERSHIP_INVITE_ACCEPTED.value: "A new member joined the lab",
    AuditAction.DATASET_CREATED.value: "A dataset was added",
    AuditAction.ANALYSIS_CREATED.value: "An analysis was added",
    AuditAction.RESULT_CREATED.value: "A result was added",
    AuditAction.DECISION_CREATED.value: "A decision was recorded",
    AuditAction.MANUSCRIPT_CREATED.value: "A manuscript was added",
    AuditAction.ETHICS_APPROVAL_CREATED.value: "An ethics approval was added",
    AuditAction.ETHICS_APPROVAL_UPDATED.value: "An ethics approval was changed",
    AuditAction.INVENTORY_ORDER_CREATED.value: "An inventory order was placed",
    AuditAction.MEETING_CREATED.value: "A meeting was scheduled",
    AuditAction.LAB_EVENT_CREATED.value: "A calendar event was added",
}
TEST_EVENT = "webhook.test"
MAX_PER_LAB = 20
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds, doubled per attempt
_TEMPORARY = frozenset({429, 500, 502, 503, 504})

_BASE = {
    WebhookKind.WEBHOOK: Provider(
        name="webhook", label="Webhook", auth_type=AuthType.PUBLIC, secret_url=True
    ),
    WebhookKind.SLACK: Provider(
        name="slack",
        label="Slack",
        auth_type=AuthType.PUBLIC,
        secret_url=True,
        instance_host_pattern=r"hooks\.slack\.com",
    ),
}


@sensitive_variables("url", "checked")
def clean_url(url: str, kind: str) -> str:
    """The checked address (`http.validate_instance_url`), keeping a trailing slash, which some
    services treat as part of the address. Raises InstanceURLError."""
    url = str(url).strip()
    checked = http.validate_instance_url(url, _BASE[kind])
    return f"{checked}/" if url.endswith("/") else checked


@sensitive_variables("secret")
def create(*, lab, user, name, kind, url, events) -> tuple[Webhook, str]:
    """A new webhook and its signing secret, which is shown only this once."""
    secret = secrets.token_urlsafe(32)
    hook = Webhook.objects.create(
        lab=lab,
        created_by=user,
        name=name,
        kind=kind,
        url_ct=crypto.encrypt(url),
        secret_ct=crypto.encrypt(secret),
        host=urlsplit(url).hostname,
        events=events,
    )
    return hook, secret


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Hex HMAC-SHA256 of `<timestamp>.<body>`: a receiver recomputes this to trust a message."""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def _message(event, lab_id, lab_name, project_id, delivery_id) -> dict:
    url = f"{settings.FRONTEND_URL}/labs/{lab_id}"
    if project_id:
        url += f"/projects/{project_id}"
    return {
        "id": str(delivery_id),
        "event": event,
        "label": EVENTS.get(event, "Test message"),
        "occurred_at": timezone.now().isoformat(),
        "lab": {"id": str(lab_id), "name": lab_name},
        "project_id": str(project_id) if project_id else None,
        "url": url,
    }


def _slack_text(message: dict) -> str:
    """Slack reads `<`, `>` and `&` as markup: a lab named `<!channel>` must not ping anyone."""
    name = message["lab"]["name"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"{message['label']} in {name}. {message['url']}"


@sensitive_variables("url", "body", "headers")
def _post(hook: Webhook, message: dict) -> int | None:
    """Send once and record the outcome. Returns the status, or None if nothing answered."""
    url = hook.url()
    provider = dataclasses.replace(_BASE[hook.kind], api_hosts=frozenset({hook.host}))
    headers = {"Content-Type": "application/json"}
    if hook.kind == WebhookKind.SLACK:
        body = json.dumps({"text": _slack_text(message)}).encode()
    else:
        body = json.dumps(message, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers |= {
            "X-LabBench-Event": message["event"],
            "X-LabBench-Delivery": message["id"],
            "X-LabBench-Signature": f"t={timestamp},v1={sign(hook.secret(), timestamp, body)}",
        }
    try:
        # Checked again at send time: DNS, the allowlist and the host rule may have changed.
        http.validate_instance_url(url, provider)
        status = http.send("POST", url, provider=provider, data=body, headers=headers).status_code
    except http.IntegrationError:
        status = None
    Webhook.objects.for_lab(hook.lab_id).filter(pk=hook.pk).update(
        last_attempt_at=timezone.now(), last_status=status
    )
    return status


@shared_task(bind=True, max_retries=MAX_RETRIES, soft_time_limit=120, time_limit=150)
def deliver(self, webhook_id: str, lab_id: str, message: dict) -> None:
    hook = Webhook.objects.for_lab(lab_id).filter(pk=webhook_id, is_active=True).first()
    if hook is None:  # turned off or removed since the event
        return
    status = _post(hook, message)
    if (status is None or status in _TEMPORARY) and self.request.retries < MAX_RETRIES:
        raise self.retry(countdown=RETRY_DELAY * 2**self.request.retries)


@http.interactive
def send_test(hook: Webhook) -> int | None:
    return _post(hook, _message(TEST_EVENT, hook.lab_id, hook.lab.name, None, hook.pk))


def _queue(event: AuditEvent) -> None:
    hooks = list(
        Webhook.objects.for_lab(event.lab_id).filter(
            is_active=True, events__contains=[event.action]
        )
    )
    if not hooks:
        return
    lab_name = Lab.objects.values_list("name", flat=True).get(pk=event.lab_id)
    message = _message(event.action, event.lab_id, lab_name, event.project_id, event.pk)
    for hook in hooks:
        deliver.delay(str(hook.pk), str(event.lab_id), message)


@receiver(post_save, sender=AuditEvent, dispatch_uid="integrations.webhooks.on_audit_event")
def on_audit_event(sender, instance, created, raw=False, **kwargs):
    if created and not raw and instance.lab_id and instance.action in EVENTS:
        # robust: a broker outage must not fail a request whose work is already committed
        transaction.on_commit(lambda: _queue(instance), robust=True)


def rotate_keys() -> int:
    """Re-encrypt webhook addresses and secrets under the newest key (D63)."""
    count = 0
    for lab in Lab.objects.all():
        for hook in Webhook.objects.for_lab(lab):
            hook.url_ct, hook.secret_ct = crypto.rotate(hook.url_ct), crypto.rotate(hook.secret_ct)
            hook.save(update_fields=["url_ct", "secret_ct"])
            count += 1
    return count
