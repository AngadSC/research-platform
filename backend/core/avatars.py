"""Profile pictures (D253). Stored in the private `lab_files` storage under
`users/<user id>/avatar-<random>.<ext>` and only ever served by `UserAvatarView`, after a check
that the viewer shares a lab with the person. The type is read from the bytes, never from the
file name or the browser's content type, and SVG (which can carry script) is not accepted."""

import secrets

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from rest_framework.exceptions import ValidationError

MAX_BYTES = 512 * 1024
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
MESSAGE = "Use a PNG, JPEG or WebP picture of 512 KB or less."


def sniff(head: bytes) -> str | None:
    """The extension for PNG, JPEG or WebP bytes, else None."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def content_type(key: str) -> str:
    return TYPES.get(key.rsplit(".", 1)[-1], "application/octet-stream")


def version(user) -> str:
    """The random part of the file name; it changes whenever the picture does."""
    return user.avatar.rsplit("avatar-", 1)[-1].split(".")[0]


def url(user) -> str | None:
    return f"/api/users/{user.pk}/avatar/?v={version(user)}" if user.avatar else None


def remove(user) -> None:
    if user.avatar:
        storages["lab_files"].delete(user.avatar)
        user.avatar = ""
        user.save(update_fields=["avatar"])


def replace(user, upload) -> None:
    if upload.size > MAX_BYTES:
        raise ValidationError({"file": "That picture is too large. " + MESSAGE})
    data = upload.read(MAX_BYTES + 1)
    ext = sniff(data[:16]) if len(data) <= MAX_BYTES else None
    if ext is None:
        raise ValidationError({"file": "That file is not a picture we accept. " + MESSAGE})
    storage, old = storages["lab_files"], user.avatar
    user.avatar = storage.save(
        f"users/{user.pk}/avatar-{secrets.token_hex(8)}.{ext}", ContentFile(data)
    )
    user.save(update_fields=["avatar"])
    if old:
        storage.delete(old)
