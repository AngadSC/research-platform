"""Google Chat (D315 to D320): the lab chat and one Google Chat space, both ways.

A writer (`WRITERS`): it posts lab chat messages into the space a lab admin chose, and reads the
new messages in that space so they show in the lab chat. The only other read is a thread someone
chooses to import into a project, as themselves (D320). Never files or attachments. Only Google
Workspace accounts can use the Chat API.

Scopes, all about Chat messages and spaces only:
`chat.messages` reads and posts messages as the person (posting as each person, D317);
`chat.spaces.readonly` lists the spaces, group chats and direct messages they are in, so one
can be picked; `chat.memberships.readonly` names an unnamed group chat by its members (D325);
`directory.readonly` looks up the names of senders in the same Google Workspace, because Chat
gives an app signed in as a person only the sender's number (D320);
`openid` and `userinfo.email` name the account. The `sub` that names it is the same number Google
Chat uses for the sender (`users/<sub>`), which is how a message from Google finds its author here.
The membership and directory scopes are optional: a person may decline them and still connect.
`labs/google_chat.py` then skips those calls, an unnamed group chat is named by kind and date,
and a sender with no name from either lookup shows as "Someone on Google Chat".

D315: its own Google OAuth app (`INTEGRATION_GOOGLE_CHAT_CLIENT_ID`), not Drive's. Google revokes a
whole grant per app, so sharing Drive's app would let "disconnect Google Chat" break Drive and
Calendar, and bundling (D262) would make every Drive sign-in ask for Chat.
"""

from integrations.providers import AuthType, Category, Provider

API = "https://chat.googleapis.com/v1"
MESSAGES = "https://www.googleapis.com/auth/chat.messages"
SPACES = "https://www.googleapis.com/auth/chat.spaces.readonly"
MEMBERSHIPS = "https://www.googleapis.com/auth/chat.memberships.readonly"
EMAIL = "https://www.googleapis.com/auth/userinfo.email"
DIRECTORY = "https://www.googleapis.com/auth/directory.readonly"
PEOPLE = "https://people.googleapis.com/v1"
# A space's resource name, as Google gives it and as we store it: `spaces/<id>`.
SPACE_PATTERN = r"^spaces/[A-Za-z0-9_-]{1,100}$"
THREAD_PATTERN = r"^spaces/[A-Za-z0-9_-]{1,100}/threads/[A-Za-z0-9_.-]{1,100}$"


def _identity(data: dict) -> tuple[str, str]:
    return str(data["sub"]), str(data.get("email", ""))


PROVIDER = Provider(
    name="google_chat",
    label="Google Chat",
    auth_type=AuthType.OAUTH2,
    category=Category.CHAT,
    icon="google-chat",
    metadata_only=False,
    writes=frozenset({"chat_messages"}),
    link_targets=frozenset(),
    scopes=("openid", EMAIL, MESSAGES, SPACES, MEMBERSHIPS, DIRECTORY),
    optional_scopes=(MEMBERSHIPS, DIRECTORY),
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    identity_url="https://openidconnect.googleapis.com/v1/userinfo",
    api_hosts=frozenset(
        {
            "chat.googleapis.com",
            "people.googleapis.com",
            "oauth2.googleapis.com",
            "openidconnect.googleapis.com",
        }
    ),
    # As Drive (D221): always a refresh token, and no include_granted_scopes.
    authorize_params={"access_type": "offline", "prompt": "consent"},
    parse_identity=_identity,
    external_id_pattern=r"^[0-9]{1,40}$",
)
