"""Quiet hours, from a person's own preferences. Hours are 0-23 in
the time zone the app saved for them (D291); a bad or missing value falls back to UTC."""

import datetime
from zoneinfo import ZoneInfo

DEFAULT_QUIET = (22, 7)


def _hour(value, default: int) -> int:
    try:
        h = int(value)
    except (TypeError, ValueError):
        return default
    return h if 0 <= h <= 23 else default


def zone_of(user) -> ZoneInfo:
    try:
        return ZoneInfo((user.preferences or {}).get("time_zone") or "UTC")
    except Exception:  # noqa: BLE001 (an unknown zone name is the same answer: UTC)
        return ZoneInfo("UTC")


def quiet_window(user) -> tuple[int, int] | None:
    prefs = user.preferences or {}
    if prefs.get("quiet") != "on":
        return None
    start = _hour(prefs.get("quiet_start"), DEFAULT_QUIET[0])
    end = _hour(prefs.get("quiet_end"), DEFAULT_QUIET[1])
    return None if start == end else (start, end)


def in_quiet_hours(user, now: datetime.datetime) -> bool:
    window = quiet_window(user)
    if window is None:
        return False
    start, end = window
    hour = now.astimezone(zone_of(user)).hour
    return start <= hour < end if start < end else hour >= start or hour < end


def quiet_release(user, now: datetime.datetime) -> datetime.datetime | None:
    """When quiet hours end, if `now` is inside them; else None."""
    if not in_quiet_hours(user, now):
        return None
    _, end = quiet_window(user)
    local = now.astimezone(zone_of(user))
    release = local.replace(hour=end, minute=0, second=0, microsecond=0)
    if release <= local:
        release += datetime.timedelta(days=1)
    return release
