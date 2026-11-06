import pytest
from django.conf import settings as django_settings
from django.core.files.storage import FileSystemStorage


@pytest.fixture(autouse=True)
def lab_files(settings, tmp_path):
    """Every test writes to its own temp dir, never the real lab_files volume."""
    settings.STORAGES = {
        **django_settings.STORAGES,
        "lab_files": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    return FileSystemStorage(location=str(tmp_path))
