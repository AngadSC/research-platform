import itertools

import pytest

from core.models import Institution, User
from labs.models import Lab, LabMembership
from projects.models import Project

_n = itertools.count()


@pytest.fixture(autouse=True)
def _local_cache(settings):
    """Tests use a per-process cache, never Valkey; cleared so throttles do not leak."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def make_user(db):
    def make(**kw):
        kw.setdefault("email", f"user{next(_n)}@example.com")
        return User.objects.create_user(password="pw", **kw)

    return make


@pytest.fixture
def make_lab(db, make_user):
    def make(name="Lab"):
        inst, _ = Institution.objects.get_or_create(name="Test Institution")
        return Lab.objects.create(institution=inst, name=name, created_by=make_user())

    return make


@pytest.fixture
def make_project(db, make_user):
    def make(lab, name="Project", **kw):
        return Project.objects.create(lab=lab, name=name, created_by=make_user(), **kw)

    return make


@pytest.fixture
def join(db):
    def do(user, lab, role):
        return LabMembership.objects.create(lab=lab, user=user, role=role)

    return do


@pytest.fixture
def verify_email(db):
    from allauth.account.models import EmailAddress

    def do(user, verified=True):
        return EmailAddress.objects.create(
            user=user, email=user.email, verified=verified, primary=True
        )

    return do
