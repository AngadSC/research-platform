"""Lab notebooks (D330): a personal notebook for each member, which only they can read, and a
shared notebook for each project. Entries are Markdown, dated and can be locked as a signed
record. Both export to Markdown, HTML (to print or save as PDF) and JSON."""

import json
from datetime import date

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import escape
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import Perm, can
from core.serializers import UserSerializer, no_control_chars
from core.views import LabScopedViewMixin
from labs import notebook_hints
from labs.models import NotebookEntry, Protocol
from projects.views import ProjectScopedMixin

MAX_BODY = 100_000
FORMATS = ("md", "html", "json")


class NotebookEntrySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    locked_by = UserSerializer(read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = NotebookEntry
        fields = [
            "id",
            "project",
            "author",
            "title",
            "entry_date",
            "body",
            "locked_at",
            "locked_by",
            "can_edit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_can_edit(self, entry) -> bool:
        return entry.locked_at is None and _may_change(self.context["request"].user, entry)


class NotebookEntryInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    entry_date = serializers.DateField(required=False)
    body = serializers.CharField(max_length=MAX_BODY, allow_blank=True, required=False)


def _may_change(user, entry) -> bool:
    """The author, and for a project's notebook also a lead (pi and lab admin count as leads)."""
    if entry.author_id == user.pk:
        return True
    return entry.project_id is not None and can(user, Perm.EDIT_PROJECT, entry.project)


# ---------------------------------------------------------------- services


@transaction.atomic
def create_entry(*, lab, user, data, project=None, request=None) -> NotebookEntry:
    data = {**data, "title": data["title"].strip()}
    if not data["title"]:
        raise ValidationError({"title": "Give the entry a title."})
    data.setdefault("entry_date", timezone.localdate())
    entry = NotebookEntry.objects.create(lab=lab, project=project, author=user, **data)
    record(
        A.NOTEBOOK_CREATED,
        actor=user,
        lab=lab,
        target=entry,
        request=request,
        metadata={"project": str(project.pk)} if project else {"personal": True},
    )
    return entry


def _refuse_if_locked(entry):
    if entry.locked_at is not None:
        raise ValidationError(
            {"detail": "This entry is locked and cannot change. Add a new entry to correct it."}
        )


@transaction.atomic
def update_entry(entry, *, user, data, request=None) -> NotebookEntry:
    if not _may_change(user, entry):
        raise PermissionDenied("Only the author, or a project lead, can change this entry.")
    _refuse_if_locked(entry)
    if "title" in data:
        data["title"] = data["title"].strip()
        if not data["title"]:
            raise ValidationError({"title": "Give the entry a title."})
    for key, value in data.items():
        setattr(entry, key, value)
    entry.save()
    record(
        A.NOTEBOOK_UPDATED,
        actor=user,
        lab=entry.lab,
        target=entry,
        request=request,
        metadata={"fields": sorted(data)},
    )
    return entry


@transaction.atomic
def delete_entry(entry, *, user, request=None) -> None:
    if not _may_change(user, entry):
        raise PermissionDenied("Only the author, or a project lead, can delete this entry.")
    _refuse_if_locked(entry)
    record(A.NOTEBOOK_DELETED, actor=user, lab=entry.lab, target=entry, request=request)
    entry.delete()


@transaction.atomic
def lock_entry(entry, *, user, request=None) -> NotebookEntry:
    """Sign an entry: nothing can change it afterwards, not even the person who wrote it."""
    if not _may_change(user, entry):
        raise PermissionDenied("Only the author, or a project lead, can lock this entry.")
    _refuse_if_locked(entry)
    entry.locked_at, entry.locked_by = timezone.now(), user
    entry.save(update_fields=["locked_at", "locked_by", "updated_at"])
    record(A.NOTEBOOK_LOCKED, actor=user, lab=entry.lab, target=entry, request=request)
    return entry


# ---------------------------------------------------------------- export


def _name(user) -> str:
    return user.display_name or user.email


def render(entries, *, title: str, fmt: str) -> tuple[str, str]:
    """(content type, text) for `entries`, oldest first."""
    stamp = timezone.localdate().isoformat()
    if fmt == "json":
        data = {
            "notebook": title,
            "exported": stamp,
            "entries": [
                {
                    "title": e.title,
                    "date": e.entry_date.isoformat(),
                    "author": _name(e.author),
                    "locked_at": e.locked_at.isoformat() if e.locked_at else None,
                    "locked_by": _name(e.locked_by) if e.locked_by_id else None,
                    "body": e.body,
                }
                for e in entries
            ],
        }
        return "application/json", json.dumps(data, indent=2, ensure_ascii=False)
    if fmt == "html":
        parts = [
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            f"<title>{escape(title)}</title>",
            "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;"
            "padding:0 1rem;color:#18181b}h1{font-size:1.6rem}h2{font-size:1.15rem;margin:0}"
            "article{border-top:1px solid #d4d4d8;padding:1rem 0;break-inside:avoid-page}"
            ".meta{color:#52525b;font-size:.85rem;margin:.15rem 0 .6rem}"
            "pre{white-space:pre-wrap;font:inherit;margin:0}"
            "@media print{body{margin:0;max-width:none}}</style></head><body>",
            f"<h1>{escape(title)}</h1><p class='meta'>Exported {stamp}. "
            "Use Print, then Save as PDF, to keep a copy.</p>",
        ]
        for e in entries:
            lock = (
                f" · Locked by {escape(_name(e.locked_by))} on {e.locked_at:%Y-%m-%d}"
                if e.locked_at and e.locked_by_id
                else ""
            )
            parts.append(
                f"<article><h2>{escape(e.title)}</h2><p class='meta'>{e.entry_date:%Y-%m-%d} · "
                f"{escape(_name(e.author))}{lock}</p><pre>{escape(e.body)}</pre></article>"
            )
        parts.append("</body></html>")
        return "text/html", "".join(parts)
    lines = [f"# {title}", "", f"Exported {stamp}", ""]
    for e in entries:
        lines += [f"## {e.title}", ""]
        lock = (
            f" · Locked by {_name(e.locked_by)} on {e.locked_at:%Y-%m-%d}"
            if e.locked_at and e.locked_by_id
            else ""
        )
        lines += [f"*{e.entry_date:%Y-%m-%d} · {_name(e.author)}{lock}*", "", e.body.strip(), ""]
        lines += ["---", ""]
    return "text/markdown", "\n".join(lines)


def export_response(request, entries, *, title, scope_meta):
    fmt = request.query_params.get("fmt", "md")
    if fmt not in FORMATS:
        raise ValidationError({"fmt": f"Use one of: {', '.join(FORMATS)}."})
    for key in ("from", "to"):
        raw = request.query_params.get(key)
        if raw:
            try:
                day = date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({key: "Use a date like 2026-11-16."}) from None
            entries = (
                entries.filter(entry_date__gte=day)
                if key == "from"
                else entries.filter(entry_date__lte=day)
            )
    rows = list(entries.select_related("author", "locked_by").order_by("entry_date", "created_at"))
    kind, text = render(rows, title=title, fmt=fmt)
    record(
        A.NOTEBOOK_EXPORTED,
        actor=request.user,
        lab=request.lab,
        request=request,
        metadata={"format": fmt, "entries": len(rows), **scope_meta},
    )
    resp = HttpResponse(text, content_type=f"{kind}; charset=utf-8")
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in title.lower())[:50] or "notebook"
    resp["Content-Disposition"] = f'attachment; filename="{safe}.{fmt}"'
    return resp


EXPORT_PARAMS = [
    OpenApiParameter("fmt", OpenApiTypes.STR, enum=list(FORMATS)),
    OpenApiParameter("from", OpenApiTypes.DATE),
    OpenApiParameter("to", OpenApiTypes.DATE),
]

# ---------------------------------------------------------------- my notebook (lab level)


class _Mine(LabScopedViewMixin, generics.GenericAPIView):
    """Your own notebook in this lab. Rows of anyone else are simply not there (404)."""

    model = NotebookEntry
    serializer_class = NotebookEntrySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            NotebookEntry.objects.for_lab(self.request.lab.pk)
            .filter(project__isnull=True, author=self.request.user)
            .select_related("author", "locked_by", "project")
            .order_by("-entry_date", "-created_at")
        )

    def get_object(self):  # the row is already yours; its project is empty by design
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["entry_id"])


class MyNotebookView(_Mine):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(responses=NotebookEntrySerializer(many=True))
    def get(self, request, lab_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=NotebookEntryInputSerializer, responses={201: NotebookEntrySerializer})
    def post(self, request, lab_id):
        ser = NotebookEntryInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        entry = create_entry(
            lab=request.lab, user=request.user, data=dict(ser.validated_data), request=request
        )
        return Response(
            self.get_serializer(self.get_queryset().get(pk=entry.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class MyNotebookEntryView(_Mine):
    lookup_url_kwarg = "entry_id"
    perms = {"PATCH": Perm.CONTRIBUTE_LAB, "DELETE": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=NotebookEntryInputSerializer, responses=NotebookEntrySerializer)
    def patch(self, request, lab_id, entry_id):
        ser = NotebookEntryInputSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        entry = update_entry(
            self.get_object(), user=request.user, data=dict(ser.validated_data), request=request
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=entry.pk)).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, entry_id):
        delete_entry(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyNotebookLockView(_Mine):
    lookup_url_kwarg = "entry_id"
    perms = {"POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=None, responses=NotebookEntrySerializer)
    def post(self, request, lab_id, entry_id):
        entry = lock_entry(self.get_object(), user=request.user, request=request)
        return Response(self.get_serializer(self.get_queryset().get(pk=entry.pk)).data)


class MyNotebookHintsView(_Mine):
    """What your entry says about inventory and protocols: suggestions you can accept (D332)."""

    lookup_url_kwarg = "entry_id"
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, lab_id, entry_id):
        from projects.models import Project

        entry = self.get_object()
        ids = Project.objects.visible_to(request.user, request.lab).values_list("pk", flat=True)
        protocols = Protocol.objects.for_lab(request.lab.pk).filter(project_id__in=list(ids))
        return Response(
            notebook_hints.hints_for(entry, user=request.user, protocols_visible_to=list(protocols))
        )


class MyNotebookExportView(_Mine):
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(parameters=EXPORT_PARAMS, responses={(200, "text/markdown"): bytes})
    def get(self, request, lab_id):
        title = f"Notebook of {_name(request.user)}"
        return export_response(
            request, self.get_queryset(), title=title, scope_meta={"personal": True}
        )


# ---------------------------------------------------------------- a project's notebook


class _Shared(ProjectScopedMixin, generics.GenericAPIView):
    model = NotebookEntry
    serializer_class = NotebookEntrySerializer
    nested = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("author", "locked_by", "project")
            .order_by("-entry_date", "-created_at")
        )


class ProjectNotebookView(_Shared):
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=NotebookEntrySerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=NotebookEntryInputSerializer, responses={201: NotebookEntrySerializer})
    def post(self, request, lab_id, project_id):
        entry = create_entry(
            lab=request.lab,
            user=request.user,
            data=dict(self.body(NotebookEntryInputSerializer)),
            project=self.project,
            request=request,
        )
        return self.out(self.get_queryset().get(pk=entry.pk), status.HTTP_201_CREATED)


class ProjectNotebookEntryView(_Shared):
    lookup_url_kwarg = "pentry_id"
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(request=NotebookEntryInputSerializer, responses=NotebookEntrySerializer)
    def patch(self, request, lab_id, project_id, pentry_id):
        entry = update_entry(
            self.get_object(),
            user=request.user,
            data=dict(self.body(NotebookEntryInputSerializer, partial=True)),
            request=request,
        )
        return self.out(self.get_queryset().get(pk=entry.pk))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, project_id, pentry_id):
        delete_entry(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectNotebookLockView(_Shared):
    lookup_url_kwarg = "pentry_id"
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=None, responses=NotebookEntrySerializer)
    def post(self, request, lab_id, project_id, pentry_id):
        entry = lock_entry(self.get_object(), user=request.user, request=request)
        return self.out(self.get_queryset().get(pk=entry.pk))


class ProjectNotebookHintsView(_Shared):
    lookup_url_kwarg = "pentry_id"
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, lab_id, project_id, pentry_id):
        entry = self.get_object()
        protocols = Protocol.objects.for_lab(request.lab.pk).filter(project=self.project)
        return Response(
            notebook_hints.hints_for(entry, user=request.user, protocols_visible_to=list(protocols))
        )


class ProjectNotebookExportView(_Shared):
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(parameters=EXPORT_PARAMS, responses={(200, "text/markdown"): bytes})
    def get(self, request, lab_id, project_id):
        title = f"{self.project.name} notebook"
        return export_response(
            request, self.get_queryset(), title=title, scope_meta={"project": str(self.project.pk)}
        )
