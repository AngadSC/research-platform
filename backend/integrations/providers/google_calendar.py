"""Google Calendar, with Google Meet (D253 to D256). One of the two providers allowed to write
(`WRITERS`): it creates, changes and removes calendar events, and asks Google for a Meet link on
the events it makes. It reads events only to show them to the person who connected the calendar,
when they look, and stores none of them.

Two scopes, both about events only (nothing else of the Google account):
`calendar.events` reads the person's own events (to show them, D256) and makes Meet events on
their primary calendar (D254); `calendar.app.created` lets the app make one calendar of its own
and manage events on that calendar alone, which is where tasks, deadlines and meetings are pushed
(D255), so they never mix into the person's own calendar and can be hidden or removed in one go.
The account is named through Drive's `about` (D264), as the same Google sign-in covers both.

D262: this provider shares one Google sign-in with Google Drive. It uses Drive's Google app
(`client_from`), and connecting either one asks for the scopes of both.
"""

from integrations.providers import AuthType, Category, Provider

API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
APP_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"


# D264: the account is named through Drive's `about`, not `calendars/primary`. The scopes we ask
# for cannot read the primary calendar's own record (`calendar.events` is not accepted there, and
# `calendar.app.created` only reaches calendars this app made), so that call is refused and the
# connect failed with "could not confirm which account". The sign-in is one Google account
# (D262), and Drive's `about` works with the `drive.file` scope that is always in the grant.
IDENTITY_URL = "https://www.googleapis.com/drive/v3/about?fields=user(permissionId,emailAddress)"


def _identity(data: dict) -> tuple[str, str]:
    user = data["user"]
    email = str(user.get("emailAddress", ""))
    return email or str(user["permissionId"]), email


PROVIDER = Provider(
    name="google_calendar",
    label="Google Calendar and Meet",
    auth_type=AuthType.OAUTH2,
    category=Category.MEETINGS,
    icon="google-calendar",
    metadata_only=False,
    writes=frozenset({"calendar_events", "meet_links"}),
    link_targets=frozenset(),
    scopes=(APP_SCOPE, SCOPE),
    bundle=("google_drive",),
    bundle_label="Google",
    client_from="google_drive",  # D262: the same Google app as Drive, so one grant works for both
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    identity_url=IDENTITY_URL,
    api_hosts=frozenset({"www.googleapis.com", "oauth2.googleapis.com"}),
    authorize_params={"access_type": "offline", "prompt": "consent"},
    parse_identity=_identity,
)
