"""Lab tenancy core (ARCHITECTURE §2, D18, D31). `.unscoped` is allowed only here,
in core/permissions.py, in admin.py files and in migrations."""

import uuid
from typing import ClassVar, Self

from django.db import models
from django.db.models.signals import m2m_changed


class UnscopedQueryError(Exception):
    """A lab model was queried without `.for_lab()` or `.visible_to()`."""


class CrossLabError(Exception):
    """A row would link objects from different labs (or different projects)."""


def project_of(obj):
    """The owning Project of a lab-data object, or None (lab-level or null FK)."""
    path = getattr(obj, "project_path", None)
    if path is None:
        return None
    for part in filter(None, path.split("__")):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _guard(name):
    def method(self, *args, **kwargs):
        self._require_scope()
        return getattr(models.QuerySet, name)(self, *args, **kwargs)

    method.__name__ = name
    return method


class LabScopedQuerySet(models.QuerySet):
    _scoped = False

    def _clone(self):
        clone = super()._clone()
        clone._scoped = self._scoped
        return clone

    def _require_scope(self):
        if not self._scoped:
            raise UnscopedQueryError(
                f"{self.model.__name__} queried without .for_lab() or .visible_to()"
            )

    _fetch_all = _guard("_fetch_all")
    count = _guard("count")
    exists = _guard("exists")
    contains = _guard("contains")
    aggregate = _guard("aggregate")
    iterator = _guard("iterator")
    in_bulk = _guard("in_bulk")
    explain = _guard("explain")

    def delete(self):
        self._require_scope()
        return super().delete()

    delete.queryset_only = True
    delete.alters_data = True

    def update(self, **kwargs):
        self._require_scope()
        banned = {"lab", *self.model.lab_parents}
        for key in kwargs:
            if key in banned or key.removesuffix("_id") in banned:
                raise CrossLabError(f"update() may not change {key!r}")
        return super().update(**kwargs)

    update.alters_data = True

    def for_lab(self, lab) -> Self:
        clone = self.filter(lab_id=getattr(lab, "pk", lab))
        clone._scoped = True
        return clone

    def visible_to(self, user, lab) -> Self:
        from core import permissions

        qs = self.for_lab(lab)
        if permissions.lab_role(user, lab) is None:
            return qs.none()
        path = self.model.project_path
        if path is None:
            return qs
        key = "pk__in" if path == "" else f"{path}__in"
        return qs.filter(**{key: permissions.visible_projects(user, lab)})


class LabScopedManager(models.Manager.from_queryset(LabScopedQuerySet)):
    def get_queryset(self):
        qs = super().get_queryset()
        instance = getattr(self, "instance", None)  # set on related managers
        if instance is not None and getattr(instance, "lab_id", None):
            qs = qs.for_lab(instance.lab_id)
        return qs


def by_secret(model):
    """Cross-lab queryset for looking a row up by an unguessable secret (an invite token hash).
    The lab is not known yet, so the caller must filter on the secret and nothing else."""
    return model.unscoped.all()


class LabScopedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab = models.ForeignKey("labs.Lab", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    lab_parents: ClassVar[tuple[str, ...]] = ()
    project_path: ClassVar[str | None] = None

    objects = LabScopedManager()
    unscoped = models.Manager()  # noqa: DJ012 (must stay after objects: default manager)

    class Meta:
        abstract = True
        base_manager_name = "unscoped"

    def save(self, *args, **kwargs):
        self._check_lab()
        super().save(*args, **kwargs)

    def _check_lab(self):
        for name in self.lab_parents:
            parent = getattr(self, name)
            if parent is None:
                continue
            if self.lab_id is None:
                self.lab_id = parent.lab_id
            elif self.lab_id != parent.lab_id:
                raise CrossLabError(f"{name} belongs to a different lab")
            if getattr(parent, "project_path", None) is not None and self.project_path:
                mine, theirs = project_of(self), project_of(parent)
                if mine is not None and theirs is not None and mine.pk != theirs.pk:
                    raise CrossLabError(f"{name} belongs to a different project")


def check_m2m_same_lab(sender, instance, action, model, pk_set, **kwargs):
    """m2m_changed receiver (D31): reject links across labs or projects."""
    if action != "pre_add" or not pk_set:
        return
    for other in model._base_manager.filter(pk__in=pk_set):
        if other.lab_id != instance.lab_id:
            raise CrossLabError("M2M link across labs")
        a, b = project_of(instance), project_of(other)
        if a is not None and b is not None and a.pk != b.pk:
            raise CrossLabError("M2M link across projects")


def connect_m2m_checks(app_models):
    for model in app_models:
        if not issubclass(model, LabScopedModel):
            continue
        for field in model._meta.many_to_many:
            if issubclass(field.related_model, LabScopedModel):
                m2m_changed.connect(check_m2m_same_lab, sender=field.remote_field.through)
