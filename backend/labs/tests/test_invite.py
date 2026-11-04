from datetime import timedelta

import pytest
from django.utils import timezone

from labs.models import Invite, LabRole, hash_token

pytestmark = pytest.mark.django_db


def test_invite_token_hashed_and_expires_in_seven_days(make_lab, make_user):
    lab, inviter = make_lab(), make_user()
    invite, token = Invite.issue(
        lab=lab, email="New@Example.COM", role=LabRole.MEMBER, invited_by=inviter
    )
    assert invite.email == "new@example.com"
    assert invite.token_hash == hash_token(token) and token not in invite.token_hash
    assert timedelta(days=7) - (invite.expires_at - timezone.now()) < timedelta(seconds=5)
    assert invite.is_usable


def test_invite_expiry_accept_revoke(make_lab, make_user):
    lab, inviter = make_lab(), make_user()
    invite, _ = Invite.issue(
        lab=lab, email="a@example.com", role=LabRole.VIEWER, invited_by=inviter
    )
    invite.expires_at = timezone.now() - timedelta(seconds=1)
    assert not invite.is_usable
    invite.expires_at = timezone.now() + timedelta(days=1)
    assert invite.is_usable
    invite.revoked_at = timezone.now()
    assert not invite.is_usable
    invite.revoked_at, invite.accepted_at = None, timezone.now()
    assert not invite.is_usable
