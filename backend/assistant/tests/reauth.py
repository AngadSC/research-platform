"""Test helper for D194: consent and token creation need a recent sign-in or password check.
`force_login` records no authentication, so tests that reach those endpoints call `sign_in`."""

import time

from allauth.account.internal.flows.login import (
    _AUTHENTICATION_METHODS_USER_SESSION_KEY,
    AUTHENTICATION_METHODS_SESSION_KEY,
)
from allauth.account.internal.userkit import user_id_to_str


def sign_in(client, user, *, seconds_ago=0, reauthenticated=True):
    """Log `client` in as `user` with a password sign-in record `seconds_ago` old."""
    client.force_login(user)
    session = client.session
    record = {"method": "password", "at": time.time() - seconds_ago}
    if reauthenticated:
        record["reauthenticated"] = True
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [record]
    session[_AUTHENTICATION_METHODS_USER_SESSION_KEY] = user_id_to_str(user)
    session.save()
    return client
