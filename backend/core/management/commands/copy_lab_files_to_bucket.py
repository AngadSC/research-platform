"""Copy lab files from local disk (LAB_FILES_ROOT) into the lab files bucket, once, right after
LAB_FILES_BUCKET is first set (DEPLOY.md "Moving lab files to a bucket"). Keys stay the same, so
the database needs no change. Safe to rerun: files already in the bucket are skipped."""

import os

from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Copy lab files from local disk into the lab files bucket."

    def handle(self, **options):
        if not settings.LAB_FILES_BUCKET:
            raise CommandError("Set LAB_FILES_BUCKET first.")
        root = settings.LAB_FILES_ROOT
        if not os.path.isdir(root):
            raise CommandError(f"{root} does not exist.")
        bucket = storages["lab_files"]
        copied = skipped = 0
        for dirpath, _, files in os.walk(root):
            for filename in files:
                path = os.path.join(dirpath, filename)
                name = os.path.relpath(path, root).replace(os.sep, "/")
                if bucket.exists(name):
                    skipped += 1
                    continue
                with open(path, "rb") as fh:
                    saved = bucket.save(name, File(fh))
                if saved != name:  # the database points at `name`, so a renamed copy is lost
                    raise CommandError(f"{name} was saved as {saved}; stopped.")
                copied += 1
        self.stdout.write(f"Copied {copied} files, {skipped} already in the bucket.")
