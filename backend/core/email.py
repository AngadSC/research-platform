"""Outbound email (D9, D14, D61). One entry point, `send_email`; the Celery task renders and
sends one message per recipient. The log line carries recipient, template, status and attempt,
never the body or context values. Context must be JSON-serializable (it crosses Celery)."""

import logging
import smtplib

from anymail.exceptions import AnymailAPIError
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string

log = logging.getLogger("core.email")

MAX_RETRIES = 5
BACKOFF_SECONDS = 30  # 30s, 1m, 2m, 4m, 8m, capped at an hour


# Reserved names (RFC 2606, 6761) can never receive mail. Seed and QA accounts use them, so a
# test pass on the live server never hands the mail provider an address that will bounce.
RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")


def send_email(template: str, to, context: dict | None = None) -> None:
    """Queue `template` for each address in `to`, after the surrounding transaction commits.
    One task per recipient, so a retry never re-sends to someone already served."""
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [a for a in recipients if not a.lower().rstrip(".").endswith(RESERVED_TLDS)]
    context = dict(context or {})

    def enqueue():
        for address in recipients:
            send_email_task.delay(template, address, context)

    transaction.on_commit(enqueue, robust=True)


def is_temporary(exc: Exception) -> bool:
    if isinstance(exc, AnymailAPIError):  # no status means the request never got an answer
        status = getattr(exc, "status_code", None)
        return status is None or status == 429 or status >= 500
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, smtplib.SMTPException):
        return isinstance(exc, smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError)
    return isinstance(exc, OSError)  # connection reset, timeout, DNS


def _render_and_send(template: str, to: str, context: dict) -> None:
    ctx = {"frontend_url": settings.FRONTEND_URL, "product_name": settings.PRODUCT_NAME, **context}
    subject = " ".join(render_to_string(f"email/{template}_subject.txt", ctx).split())
    text = render_to_string(f"email/{template}.txt", ctx)
    html = render_to_string(f"email/{template}.html", ctx)
    msg = EmailMultiAlternatives(subject, text, None, [to])
    msg.attach_alternative(html, "text/html")
    msg.send()


@shared_task(bind=True, max_retries=MAX_RETRIES)
def send_email_task(self, template: str, to: str, context: dict) -> bool:
    attempt = self.request.retries + 1

    def line(status):
        log.info("email to=%s template=%s status=%s attempt=%d", to, template, status, attempt)

    try:
        _render_and_send(template, to, context)
    except Exception as exc:
        if is_temporary(exc) and self.request.retries < self.max_retries:
            line("retry")
            raise self.retry(
                exc=exc, countdown=min(BACKOFF_SECONDS * 2**self.request.retries, 3600)
            ) from exc
        line("failed")  # permanent, or out of retries
        return False
    line("sent")
    return True
