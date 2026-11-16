"""Scheduled lab jobs (Celery beat, config/settings.py)."""

from celery import shared_task

from labs import google_chat, video_calendar


@shared_task(soft_time_limit=600, time_limit=660)
def push_google_calendars() -> int:
    """D255: keep each person's app calendar in Google up to date (every 15 minutes)."""
    return video_calendar.push_all()


@shared_task(soft_time_limit=50, time_limit=60)
def poll_google_chat() -> int:
    """D316: bring new messages from each linked Google Chat space into the lab chat."""
    return google_chat.poll_all()


@shared_task(
    soft_time_limit=50,
    time_limit=60,
    autoretry_for=(google_chat.IntegrationError,),
    retry_backoff=5,
    max_retries=5,
)
def relay_lab_chat_message(lab_id: str, message_id: str, project_id: str = "") -> bool:
    """D317, D325: post one lab or project chat message to its linked Google Chat."""
    model = google_chat._model(project_id or None)
    related = ("author", "lab", "project") if project_id else ("author", "lab")
    message = model.objects.for_lab(lab_id).select_related(*related).filter(pk=message_id).first()
    return google_chat.relay(message) if message is not None else False


@shared_task(soft_time_limit=50, time_limit=60)
def delete_google_chat_message(
    lab_id: str, external_id: str, author_id: str, project_id: str = ""
) -> None:
    """D319: remove a deleted chat message from Google Chat too (best effort)."""
    from labs.models import Lab
    from projects.models import Project

    lab = Lab.objects.filter(pk=lab_id).first()
    if lab is None:
        return
    project = Project.objects.for_lab(lab).filter(pk=project_id).first() if project_id else None
    if project_id and project is None:
        return
    google_chat.delete_remote(lab, external_id, author_id or None, project)
