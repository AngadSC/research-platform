"""Meetings on Google Meet or Zoom, and Google Calendar both ways (D253 to D256).

Every call goes through `integrations.http.send` with the person's own connected account, so the
host allow-list, token refresh, retries and the account's status rules all apply. Only the two
writer providers (`integrations.providers.WRITERS`) are used here.

What leaves the app follows the `.ics` feed (D231): title, times, the project name and the join
link. Notes never do. Meet events also carry the attendees' email addresses, because that is what
puts the meeting on their own calendars (D254).
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from integrations.http import AccountUnavailable, IntegrationError, send
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_calendar, zoom
from labs.models import GoogleCalendarSync, Meeting, SyncedEvent, VideoProvider

log = logging.getLogger(__name__)

GCAL = google_calendar.API
ZOOM = zoom.API
PROVIDER_OF = {
    VideoProvider.GOOGLE_MEET: google_calendar.PROVIDER,
    VideoProvider.ZOOM: zoom.PROVIDER,
}
LABEL = {VideoProvider.GOOGLE_MEET: "Google Calendar", VideoProvider.ZOOM: "Zoom"}
PUSH_PAST = timedelta(days=7)
PUSH_FUTURE = timedelta(days=90)
MAX_CHANGES = 300  # per sync run; the rest wait for the next run
MAX_PULLED = 250  # events shown from Google per request


class RemoteError(ValidationError):
    """Google or Zoom refused or failed. Shown on the form; nothing local was changed."""


def active_account(lab, user, provider_name):
    return (
        ConnectedAccount.objects.for_lab(lab)
        .filter(user=user, provider=provider_name, status=AccountStatus.ACTIVE)
        .first()
    )


def _call(account, method, url, *, ok=(200, 201, 204), **kwargs):
    """One API call; a RemoteError (shown on the form) when it fails."""
    provider = google_calendar.PROVIDER if account.provider == "google_calendar" else zoom.PROVIDER
    try:
        resp = send(method, url, provider=provider, account=account, **kwargs)
    except AccountUnavailable as exc:
        raise RemoteError(
            {"video": [f"Reconnect {provider.label} in Settings, then try again."]}
        ) from exc
    except IntegrationError as exc:
        raise RemoteError({"video": [f"{provider.label} did not answer. Try again."]}) from exc
    if resp.status_code not in ok:
        log.warning("%s %s answered %s", provider.name, method, resp.status_code)
        raise RemoteError({"video": [f"{provider.label} refused the change. Try again."]})
    return resp


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- calls on a meeting (D254)


def _meet_body(meeting, emails):
    return {
        "summary": meeting.title,
        "start": {"dateTime": _iso(meeting.starts_at)},
        "end": {"dateTime": _iso(meeting.ends_at)},
        "attendees": [{"email": e} for e in sorted(emails)],
        "source": {"title": settings.PRODUCT_NAME, "url": settings.FRONTEND_URL},
    }


def _zoom_body(meeting):
    minutes = max(1, round((meeting.ends_at - meeting.starts_at).total_seconds() / 60))
    return {
        "topic": meeting.title[:200],
        "type": 2,  # scheduled
        "start_time": _iso(meeting.starts_at),
        "duration": minutes,
        "timezone": "UTC",
        "settings": {"waiting_room": True, "join_before_host": False},
    }


def _meet_link(data) -> str:
    link = str(data.get("hangoutLink") or "")
    return link if urlsplit(link).hostname == "meet.google.com" else ""


def _zoom_link(data) -> str:
    link = str(data.get("join_url") or "")
    host = urlsplit(link).hostname or ""
    return link if host == "zoom.us" or host.endswith(".zoom.us") else ""


def create_call(meeting, provider, account, emails) -> None:
    """Make the call on `account` and fill in the meeting's link (not saved here)."""
    if provider == VideoProvider.GOOGLE_MEET:
        body = _meet_body(meeting, emails)
        body["conferenceData"] = {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        data = _call(
            account,
            "POST",
            f"{GCAL}/calendars/primary/events",
            params={"conferenceDataVersion": 1, "sendUpdates": "none"},
            json=body,
        ).json()
        meeting.external_id, meeting.join_url = str(data.get("id", "")), _meet_link(data)
    else:
        data = _call(account, "POST", f"{ZOOM}/users/me/meetings", json=_zoom_body(meeting)).json()
        meeting.external_id, meeting.join_url = str(data.get("id", "")), _zoom_link(data)
    if not meeting.external_id or not meeting.join_url:
        delete_call(meeting, quiet=True)
        raise RemoteError({"video": [f"{LABEL[provider]} did not return a join link. Try again."]})
    meeting.video_provider, meeting.video_account = provider, account


def update_call(meeting, emails) -> None:
    account = meeting.video_account
    if not meeting.video_provider or account is None or account.status != AccountStatus.ACTIVE:
        return  # the account was disconnected: the link stays, changes stay here (D254)
    if meeting.video_provider == VideoProvider.GOOGLE_MEET:
        _call(
            account,
            "PATCH",
            f"{GCAL}/calendars/primary/events/{quote(meeting.external_id, safe='')}",
            params={"sendUpdates": "none"},
            json=_meet_body(meeting, emails),
        )
    else:
        body = _zoom_body(meeting)
        body.pop("type")
        _call(account, "PATCH", f"{ZOOM}/meetings/{quote(meeting.external_id, safe='')}", json=body)


def delete_call(meeting, *, quiet=False) -> None:
    """Remove the call. Already gone (404 or 410) is fine. `quiet` swallows every failure."""
    account = meeting.video_account
    if not meeting.external_id or account is None or account.status != AccountStatus.ACTIVE:
        return
    if meeting.video_provider == VideoProvider.GOOGLE_MEET:
        url = f"{GCAL}/calendars/primary/events/{quote(meeting.external_id, safe='')}"
        kwargs = {"params": {"sendUpdates": "none"}}
    else:
        url, kwargs = f"{ZOOM}/meetings/{quote(meeting.external_id, safe='')}", {}
    try:
        _call(account, "DELETE", url, ok=(200, 204, 404, 410), **kwargs)
    except RemoteError:
        if not quiet:
            raise


def check_can_change(meeting, user) -> None:
    """D254: a call made on someone's account changes only through that person."""
    account = meeting.video_account
    if (
        meeting.video_provider
        and account is not None
        and account.status == AccountStatus.ACTIVE
        and account.user_id != user.pk
    ):
        who = meeting.created_by.display_name or meeting.created_by.email
        raise PermissionDenied(
            f"This meeting's {LABEL[meeting.video_provider]} call is on {who}'s account, "
            "so only they can change or delete it."
        )


def account_for_new_call(lab, user, provider) -> ConnectedAccount:
    account = active_account(lab, user, PROVIDER_OF[provider].name)
    if account is None:
        raise ValidationError(
            {"video": [f"Connect {LABEL[provider]} in Settings > Integrations first."]}
        )
    return account


# ---------------------------------------------------------------- Google into the app (D256)


def sync_for(lab, user):
    account = active_account(lab, user, google_calendar.PROVIDER.name)
    if account is None:
        return None
    sync, _ = GoogleCalendarSync.objects.for_lab(lab).get_or_create(
        lab=lab, account=account, defaults={"user": user}
    )
    return sync


def google_events(lab, user, start: date, end: date) -> list[dict]:
    """The person's own primary-calendar events in the window, read live and never stored.
    Meetings the app made on that calendar are left out: they are on the calendar already."""
    sync = sync_for(lab, user)
    if sync is None or not sync.show_google_events:
        return []
    resp = _call(
        sync.account,
        "GET",
        f"{GCAL}/calendars/primary/events",
        params={
            "timeMin": f"{start.isoformat()}T00:00:00Z",
            "timeMax": f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z",
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": MAX_PULLED,
        },
    )
    ours = set(
        Meeting.objects.for_lab(lab)
        .filter(video_account=sync.account, video_provider=VideoProvider.GOOGLE_MEET)
        .values_list("external_id", flat=True)
    )
    out = []
    for e in resp.json().get("items", []):
        if not isinstance(e, dict) or e.get("status") == "cancelled" or e.get("id") in ours:
            continue
        start_, end_ = e.get("start") or {}, e.get("end") or {}
        starts_at = parse_datetime(str(start_.get("dateTime") or ""))
        ends_at = parse_datetime(str(end_.get("dateTime") or ""))
        day = parse_date(str(start_.get("date") or "")) or (starts_at.date() if starts_at else None)
        if day is None:
            continue
        last = parse_date(str(end_.get("date") or ""))  # all-day end is exclusive
        link = str(e.get("htmlLink") or "")
        out.append(
            {
                "id": str(e.get("id", ""))[:1024],
                "title": str(e.get("summary") or "(No title)")[:300],
                "date": day,
                "end_date": (
                    last - timedelta(days=1) if last and last - day > timedelta(days=1) else None
                ),
                "starts_at": starts_at,
                "ends_at": ends_at,
                "join_url": _meet_link(e),
                "url": link if (urlsplit(link).hostname or "") == "www.google.com" else "",
            }
        )
    return out


# ---------------------------------------------------------------- the app into Google (D255)


def _wanted(sync) -> dict[str, dict]:
    """The events the app calendar should hold: the person's own calendar items, as Google
    event bodies, by key."""
    from labs.lab_calendar import build_calendar

    today = timezone.localdate()
    out = {}
    lab = sync.lab
    for item in build_calendar(sync.user, lab, today - PUSH_PAST, today + PUSH_FUTURE, mine=True):
        kind = item["kind"]
        if item["done"] or not getattr(sync, f"push_{kind}s", False):
            continue
        if kind == "meeting":
            meeting = Meeting.objects.for_lab(lab).filter(pk=item["id"]).first()
            if (
                meeting
                and meeting.video_provider == VideoProvider.GOOGLE_MEET
                and meeting.video_account_id == sync.account_id
            ):
                continue  # already on their own calendar, made with Meet
        title = item["title"] + (f" ({item['project_name']})" if item["project_name"] else "")
        lines = [f"Join: {item['join_url']}"] if item["join_url"] else []
        lines.append(
            f"From {settings.PRODUCT_NAME}: {settings.FRONTEND_URL}/labs/{lab.pk}/calendar"
        )
        body = {"summary": title[:300], "description": "\n".join(lines)}
        if item["starts_at"]:
            body["start"] = {"dateTime": _iso(item["starts_at"])}
            body["end"] = {"dateTime": _iso(item["ends_at"])}
        else:
            body["start"] = {"date": item["date"].isoformat()}
            body["end"] = {"date": (item["date"] + timedelta(days=1)).isoformat()}
        out[f"{kind}:{item['id']}"] = body
    return out


def _fingerprint(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _app_calendar(sync) -> str:
    if not sync.app_calendar_id:
        data = _call(
            sync.account,
            "POST",
            f"{GCAL}/calendars",
            json={"summary": f"{settings.PRODUCT_NAME}: {sync.lab.name}"[:200]},
        ).json()
        sync.app_calendar_id = str(data.get("id", ""))[:1024]
        if not sync.app_calendar_id:
            raise RemoteError({"video": ["Google did not make the calendar."]})
        sync.save(update_fields=["app_calendar_id", "updated_at"])
        SyncedEvent.objects.for_lab(sync.lab).filter(sync=sync).delete()
    return sync.app_calendar_id


def push(sync) -> dict:
    """Bring the person's app calendar in Google up to date. Returns counts. A calendar the
    person deleted in Google is made again on the next run."""
    counts = {"added": 0, "changed": 0, "removed": 0}
    if sync.account.status != AccountStatus.ACTIVE:
        return counts
    have = {s.key: s for s in SyncedEvent.objects.for_lab(sync.lab).filter(sync=sync)}
    if not sync.pushes and not have:
        return counts
    try:
        cal = quote(_app_calendar(sync) if sync.pushes else sync.app_calendar_id, safe="")
        wanted = _wanted(sync) if sync.pushes else {}
        budget = MAX_CHANGES
        for key, body in wanted.items():
            if budget <= 0:
                break
            fp, row = _fingerprint(body), have.get(key)
            if row is not None and row.fingerprint == fp:
                continue
            budget -= 1
            if row is not None:
                resp = send(
                    "PATCH",
                    f"{GCAL}/calendars/{cal}/events/{quote(row.event_id, safe='')}",
                    provider=google_calendar.PROVIDER,
                    account=sync.account,
                    json=body,
                )
                if resp.status_code == 200:
                    row.fingerprint = fp
                    row.save(update_fields=["fingerprint", "updated_at"])
                    counts["changed"] += 1
                    continue
                if resp.status_code not in (404, 410):
                    raise RemoteError({"video": ["Google refused a change."]})
                row.delete()  # removed in Google: add it again
            data = _call(sync.account, "POST", f"{GCAL}/calendars/{cal}/events", json=body).json()
            SyncedEvent.objects.create(
                lab=sync.lab, sync=sync, key=key, event_id=str(data["id"])[:1024], fingerprint=fp
            )
            counts["added"] += 1
        for key in set(have) - set(wanted):
            if budget <= 0:
                break
            budget -= 1
            _call(
                sync.account,
                "DELETE",
                f"{GCAL}/calendars/{cal}/events/{quote(have[key].event_id, safe='')}",
                ok=(200, 204, 404, 410),
            )
            have[key].delete()
            counts["removed"] += 1
        sync.last_error = ""
    except RemoteError:
        if _calendar_gone(sync):
            sync.app_calendar_id = ""  # deleted in Google: made again next time
        sync.last_error = "Google did not accept every change. It will try again shortly."
    except (KeyError, ValueError, TypeError):
        sync.last_error = "Google sent an answer the app did not understand."
    sync.last_synced_at = timezone.now()
    sync.save(update_fields=["app_calendar_id", "last_error", "last_synced_at", "updated_at"])
    return counts


def _calendar_gone(sync) -> bool:
    if not sync.app_calendar_id:
        return False
    try:
        resp = send(
            "GET",
            f"{GCAL}/calendars/{quote(sync.app_calendar_id, safe='')}/events",
            provider=google_calendar.PROVIDER,
            account=sync.account,
            params={"maxResults": 1},
        )
    except (AccountUnavailable, IntegrationError):
        return False
    return resp.status_code in (404, 410)


def push_all() -> int:
    """The scheduled run: every active Google Calendar connection that pushes anything. Lab by
    lab, as jobs do (D49); each person's calendar is built as that person (`build_calendar`)."""
    from labs.models import Lab

    done = 0
    for lab in Lab.objects.all():
        accounts = ConnectedAccount.objects.for_lab(lab).filter(
            provider=google_calendar.PROVIDER.name, status=AccountStatus.ACTIVE
        )
        for account in accounts.select_related("user"):
            if not account.user.is_active:
                continue
            sync = sync_for(lab, account.user)
            if sync is None or not sync.pushes:
                continue
            push(sync)
            done += 1
    return done
