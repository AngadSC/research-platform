"""Upload one backup file from stdin to BACKUP_BUCKET as `backups/<name>`, then delete backups
older than BACKUP_KEEP_DAYS. deploy/backup.sh calls it every night (DEPLOY.md section 8)."""

import sys
from datetime import timedelta

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

PREFIX = "backups/"


def expired(objects, now, days):
    """Keys of listed objects last modified more than `days` ago."""
    cutoff = now - timedelta(days=days)
    return [o["Key"] for o in objects if o["LastModified"] < cutoff]


class Command(BaseCommand):
    help = "Upload stdin to the backup bucket as backups/<name> and prune old backups."

    def add_arguments(self, parser):
        parser.add_argument("name", help="File name only, for example db-2026-11-24.dump")

    def handle(self, name, **options):
        if not settings.BACKUP_BUCKET:
            raise CommandError("BACKUP_BUCKET is not set.")
        if not name or "/" in name or name.startswith("."):
            raise CommandError("Give a plain file name.")
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.BACKUP_ENDPOINT_URL,
            region_name=settings.BACKUP_REGION,
            aws_access_key_id=settings.BACKUP_ACCESS_KEY_ID,
            aws_secret_access_key=settings.BACKUP_SECRET_ACCESS_KEY,
        )
        bucket, key = settings.BACKUP_BUCKET, PREFIX + name
        s3.upload_fileobj(sys.stdin.buffer, bucket, key)
        size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if not size:
            raise CommandError(f"{key} is empty; old backups were kept.")

        # Prune only after a good upload, so a failing night never removes the last good copy.
        old = []
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
            old += expired(page.get("Contents", []), timezone.now(), settings.BACKUP_KEEP_DAYS)
        for k in old:
            s3.delete_object(Bucket=bucket, Key=k)
        self.stdout.write(f"Uploaded {key} ({size} bytes); removed {len(old)} old backups.")
