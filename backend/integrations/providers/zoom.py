"""Zoom (D253, D254). One of the two providers allowed to write (`WRITERS`): it creates, changes
and removes Zoom meetings on the connected person's own Zoom account, and nothing else.

Each lab registers one Zoom "General app" (user-managed) and gives it exactly these scopes:
`meeting:write:meeting`, `meeting:update:meeting`, `meeting:delete:meeting` and `user:read:user`.
Zoom grants whatever the app was set up with, so an app with more scopes fails to connect
(`unexpected_scope`, D78) rather than holding more than this needs.
"""

from integrations import http
from integrations.providers import AuthType, Category, Provider

API = "https://api.zoom.us/v2"


def _identity(data: dict) -> tuple[str, str]:
    return str(data["id"]), str(data.get("email", ""))


def revoke(token) -> bool:
    """Zoom wants the app's credentials as Basic auth and the token in the query."""
    import base64

    client_id, client_secret = PROVIDER.client()
    pair = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = http.send(
        "POST",
        PROVIDER.revoke_url,
        provider=PROVIDER,
        params={"token": token},
        headers={"Authorization": f"Basic {pair}"},
    )
    return resp.status_code == 200


PROVIDER = Provider(
    name="zoom",
    label="Zoom",
    auth_type=AuthType.OAUTH2,
    category=Category.MEETINGS,
    icon="zoom",
    metadata_only=False,
    writes=frozenset({"zoom_meetings"}),
    link_targets=frozenset(),
    scopes=(
        "meeting:delete:meeting",
        "meeting:update:meeting",
        "meeting:write:meeting",
        "user:read:user",
    ),
    authorize_url="https://zoom.us/oauth/authorize",
    token_url="https://zoom.us/oauth/token",
    revoke_url="https://zoom.us/oauth/revoke",
    identity_url=f"{API}/users/me",
    api_hosts=frozenset({"zoom.us", "api.zoom.us"}),
    parse_identity=_identity,
    revoke=revoke,
    token_auth="basic",
)
