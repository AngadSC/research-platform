"""Profile picture, pronouns and bio (D258)."""

import pytest
from django.conf import settings as django_settings
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from labs.models import LabRole

pytestmark = pytest.mark.django_db

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000101a5f645400000000049454e44ae426082"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"0" * 20
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 " + b"0" * 20
BASELINE_QUERIES = 21  # the members list with two people; five must cost the same
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture(autouse=True)
def store(settings, tmp_path):
    """Every test writes to its own temp dir, never the real lab_files volume."""
    settings.STORAGES = {
        **django_settings.STORAGES,
        "lab_files": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    return FileSystemStorage(location=str(tmp_path))


def api(user=None):
    client = APIClient()
    if user:
        client.force_login(user)
    return client


def upload(client, data, name="me.png", content_type="image/png"):
    file = SimpleUploadedFile(name, data, content_type=content_type)
    return client.put("/api/me/avatar/", {"file": file}, format="multipart")


@pytest.fixture
def lab_pair(make_user, make_lab, join):
    """Two people in one lab, and a stranger in another."""
    lab = make_lab()
    ann, ben, stranger = make_user(), make_user(), make_user()
    join(ann, lab, LabRole.MEMBER)
    join(ben, lab, LabRole.MEMBER)
    ann.lab = lab
    join(stranger, make_lab("Other"), LabRole.PI)
    return ann, ben, stranger


@pytest.mark.parametrize(
    ("data", "ext", "mime"),
    [(PNG, "png", "image/png"), (JPEG, "jpg", "image/jpeg"), (WEBP, "webp", "image/webp")],
)
def test_accepts_the_three_types_by_their_bytes(make_user, store, data, ext, mime):
    user = make_user()
    # the name and browser type lie on purpose: only the bytes count
    resp = upload(api(user), data, name="x.txt", content_type="text/plain")
    assert resp.status_code == 200, resp.content
    user.refresh_from_db()
    assert user.avatar.startswith(f"users/{user.pk}/avatar-") and user.avatar.endswith("." + ext)
    assert resp.json()["avatar_url"].startswith(f"/api/users/{user.pk}/avatar/?v=")
    got = api(user).get(f"/api/users/{user.pk}/avatar/")
    assert got.status_code == 200 and got["Content-Type"] == mime
    assert got["X-Content-Type-Options"] == "nosniff"
    assert "private" in got["Cache-Control"] and "max-age" in got["Cache-Control"]
    assert b"".join(got.streaming_content) == data


@pytest.mark.parametrize(
    ("data", "name", "content_type"),
    [
        (SVG, "me.svg", "image/svg+xml"),
        (SVG, "me.png", "image/png"),
        (b"just some text", "me.png", "image/png"),
        (b"GIF89a" + b"0" * 20, "me.gif", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "me.webp", "image/webp"),
        (b"", "me.png", "image/png"),
    ],
)
def test_rejects_anything_that_is_not_png_jpeg_or_webp(make_user, store, data, name, content_type):
    user = make_user()
    resp = upload(api(user), data, name, content_type)
    assert resp.status_code == 400
    assert "PNG, JPEG or WebP" in str(resp.json())
    user.refresh_from_db()
    assert user.avatar == "" and not store.exists(f"users/{user.pk}")


def test_size_limit_is_512_kb(make_user):
    user = make_user()
    assert upload(api(user), PNG + b"0" * (512 * 1024 - len(PNG))).status_code == 200
    resp = upload(api(user), PNG + b"0" * (512 * 1024 - len(PNG) + 1))
    assert resp.status_code == 400 and "too large" in str(resp.json())


def test_upload_needs_a_file(make_user):
    resp = api(make_user()).put("/api/me/avatar/", {}, format="multipart")
    assert resp.status_code == 400


def test_replace_and_delete_clean_up_the_old_file(make_user, store):
    user = make_user()
    upload(api(user), PNG)
    user.refresh_from_db()
    first = user.avatar
    assert store.exists(first)
    upload(api(user), JPEG)
    user.refresh_from_db()
    assert user.avatar != first and not store.exists(first) and store.exists(user.avatar)
    second = user.avatar
    assert api(user).delete("/api/me/avatar/").status_code == 204
    user.refresh_from_db()
    assert user.avatar == "" and not store.exists(second)
    assert api(user).get(f"/api/users/{user.pk}/avatar/").status_code == 404
    assert api(user).delete("/api/me/avatar/").status_code == 204  # nothing to remove is fine


def test_url_version_changes_with_the_picture(make_user):
    user = make_user()
    first = upload(api(user), PNG).json()["avatar_url"]
    assert upload(api(user), PNG).json()["avatar_url"] != first


def test_self_and_lab_mates_can_see_it_strangers_get_404(lab_pair):
    ann, ben, stranger = lab_pair
    upload(api(ann), PNG)
    url = f"/api/users/{ann.pk}/avatar/"
    assert api(ann).get(url).status_code == 200
    assert api(ben).get(url).status_code == 200
    assert api(stranger).get(url).status_code == 404
    assert api().get(url).status_code == 401
    # no picture: 404 even for a lab mate
    assert api(ann).get(f"/api/users/{ben.pk}/avatar/").status_code == 404


def test_nobody_else_can_change_your_picture(lab_pair):
    ann, ben, _ = lab_pair
    upload(api(ben), PNG)
    ben.refresh_from_db()
    key = ben.avatar
    api(ann).delete("/api/me/avatar/")
    ben.refresh_from_db()
    assert ben.avatar == key


def test_pronouns_and_bio_on_me(make_user):
    user = make_user()
    resp = api(user).patch(
        "/api/me/", {"pronouns": "she/her", "bio": "Line one\nLine two"}, format="json"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["pronouns"], body["bio"], body["avatar_url"]) == (
        "she/her",
        "Line one\nLine two",
        None,
    )
    assert api(user).patch("/api/me/", {"bio": "x" * 501}, format="json").status_code == 400
    assert api(user).patch("/api/me/", {"bio": "x" * 500}, format="json").status_code == 200
    assert api(user).patch("/api/me/", {"pronouns": "x" * 41}, format="json").status_code == 400
    assert api(user).patch("/api/me/", {"pronouns": "a\x00b"}, format="json").status_code == 400
    # the picture itself cannot be set through /me/
    api(user).patch("/api/me/", {"avatar": "users/x/y.png", "avatar_url": "/x"}, format="json")
    user.refresh_from_db()
    assert user.avatar == ""


def test_members_list_shows_pronouns_bio_and_picture_without_extra_queries(
    lab_pair, make_user, join, django_assert_max_num_queries
):
    ann, ben, _ = lab_pair
    api(ann).patch("/api/me/", {"pronouns": "they/them", "bio": "Hi"}, format="json")
    upload(api(ann), PNG)
    url = f"/api/labs/{ann.lab.pk}/members/"
    with django_assert_max_num_queries(BASELINE_QUERIES):
        resp = api(ben).get(url)
    for _ in range(3):  # more members with pictures must not add queries
        other = make_user()
        join(other, ann.lab, LabRole.MEMBER)
        upload(api(other), PNG)
    with django_assert_max_num_queries(BASELINE_QUERIES):
        resp2 = api(ben).get(url)
    assert len(resp2.json()) == len(resp.json()) + 3
    rows = {r["user"]["id"]: r["user"] for r in resp.json()}
    mine = rows[str(ann.pk)]
    assert (mine["pronouns"], mine["bio"]) == ("they/them", "Hi")
    assert mine["avatar_url"].startswith(f"/api/users/{ann.pk}/avatar/?v=")
