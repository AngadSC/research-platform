"""Backup pruning and the one-time copy of local lab files into a bucket (DEPLOY.md section 8)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from core.management.commands.backup_upload import expired


def test_expired_keeps_recent_backups():
    now = datetime(2026, 11, 24, tzinfo=UTC)
    objs = [
        {"Key": "backups/db-old.dump", "LastModified": now - timedelta(days=31)},
        {"Key": "backups/db-new.dump", "LastModified": now - timedelta(days=29)},
    ]
    assert expired(objs, now, 30) == ["backups/db-old.dump"]


class FakeS3:
    def __init__(self, objects):
        self.objects, self.deleted = objects, []

    def upload_fileobj(self, fh, bucket, key):
        self.objects[key] = (fh.read(), datetime.now(UTC))

    def head_object(self, Bucket, Key):
        return {"ContentLength": len(self.objects[Key][0])}

    def get_paginator(self, _):
        objs = [{"Key": k, "LastModified": t} for k, (_, t) in self.objects.items()]
        return type("P", (), {"paginate": lambda self, **kw: [{"Contents": objs}]})()

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)


def test_backup_upload_uploads_then_prunes(settings, monkeypatch):
    import io
    import sys

    settings.BACKUP_BUCKET, settings.BACKUP_KEEP_DAYS = "example-test-backups", 30
    old = datetime.now(UTC) - timedelta(days=40)
    s3 = FakeS3({"backups/db-old.dump": (b"x", old)})
    monkeypatch.setattr("boto3.client", lambda *a, **kw: s3)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"dump bytes")))
    call_command("backup_upload", "db-new.dump")
    assert s3.objects["backups/db-new.dump"][0] == b"dump bytes"
    assert s3.deleted == ["backups/db-old.dump"]

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
    with pytest.raises(CommandError, match="empty"):  # an empty dump never triggers pruning
        call_command("backup_upload", "db-empty.dump")
    assert s3.deleted == ["backups/db-old.dump"]


def test_backup_upload_needs_a_bucket(settings):
    settings.BACKUP_BUCKET = ""
    with pytest.raises(CommandError, match="BACKUP_BUCKET"):
        call_command("backup_upload", "db.dump")


def test_copy_lab_files_to_bucket(tmp_path):
    src, dst = tmp_path / "local", tmp_path / "bucket"
    (src / "labs" / "a").mkdir(parents=True)
    (src / "labs" / "a" / "one.pdf").write_bytes(b"one")
    (src / "two.csv").write_bytes(b"two")
    (dst / "labs" / "a").mkdir(parents=True)
    (dst / "labs" / "a" / "one.pdf").write_bytes(b"already there")
    fake_bucket = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(dst)},
    }
    with override_settings(
        LAB_FILES_BUCKET="example-test-bucket",
        LAB_FILES_ROOT=str(src),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            "lab_files": fake_bucket,
        },
    ):
        call_command("copy_lab_files_to_bucket")
        call_command("copy_lab_files_to_bucket")  # rerun copies nothing new
    assert (dst / "two.csv").read_bytes() == b"two"
    assert (dst / "labs" / "a" / "one.pdf").read_bytes() == b"already there"


def test_copy_needs_a_bucket(settings):
    settings.LAB_FILES_BUCKET = ""
    with pytest.raises(CommandError, match="LAB_FILES_BUCKET"):
        call_command("copy_lab_files_to_bucket")
