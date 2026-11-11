"""Scheduled lab jobs (Celery beat, config/settings.py)."""

from celery import shared_task

from labs import video_calendar


@shared_task(soft_time_limit=600, time_limit=660)
def push_google_calendars() -> int:
    """D255: keep each person's app calendar in Google up to date (every 15 minutes)."""
    return video_calendar.push_all()
