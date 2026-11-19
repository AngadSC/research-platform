"""The lab chat, or a project's chat, and one Google Chat conversation, both ways (D315 to D325).

A conversation is a space, a group chat or a direct message: Google names all three
`spaces/<id>`. Each chat links to at most one, and each conversation to at most one chat.

Out: each chat message is posted there as its author, through their own Google Chat connection; a
member who has not connected (or is not in it) is posted by the connection that set the link up,
with their name in front (D317). In: the conversation is read every few seconds (`poll_all`,
Celery beat) and new messages are added to the chat (D316).

Every call goes through `integrations.http.send` with a connected account, so the host allow-list,
token refresh, timeouts and the account's status rules all apply. Nothing but message text and
the sender goes either way, plus the emoji reactions people put on messages in Google (shown with
the message, as counts, and kept up to date). No attachments, edits, or reactions sent back.
"""

import logging
import re
import uuid
from datetime import UTC, timedelta
from urllib.parse import quote

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can, lab_role, require
from core.reactions import clean_external
from integrations.http import AccountUnavailable, IntegrationError, interactive, send
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_chat
from labs.models import ChatSource, GoogleChatBridge, LabChatMessage
from projects.models import ChatMessage

log = logging.getLogger(__name__)

PROVIDER = google_chat.PROVIDER
API = google_chat.API
# Our own posts carry a client-assigned id with this prefix, so reading the space skips them even
# before the post's name is stored (D316). Google allows `client-` plus lower-case letters,
# digits and hyphens, 63 characters at most.
CLIENT_PREFIX = "client-labbench-"
MAX_BODY = 4000  # the lab chat's own limit (ChatMessageInputSerializer)
PAGE = 100  # messages read in per space per run; the rest wait for the next run
LOCK_SECONDS = 60
UNKNOWN_SENDER = "Someone on Google Chat"
INBOUND_PER_HOUR = 300  # per lab: a busy or hostile space can't flood the lab chat

_MENTION = re.compile(r"@\[([^\]\n]+)\]\(user:[0-9a-fA-F-]{36}\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)


class RemoteError(ValidationError):
    """Google refused or failed; shown on the settings form, nothing local changed."""


# ---------------------------------------------------------------- accounts and the link


def own_account(lab, user):
    """`user`'s active Google Chat connection in `lab`, or None."""
    return (
        ConnectedAccount.objects.for_lab(lab)
        .filter(user=user, provider=PROVIDER.name, status=AccountStatus.ACTIVE)
        .first()
    )


def bridge_for(lab, project=None):
    """The lab chat's link, or with `project` that project chat's; None when not linked."""
    qs = GoogleChatBridge.objects.for_lab(lab).select_related("account", "created_by", "project")
    if project is None:
        return qs.filter(project__isnull=True).first()
    return qs.filter(project=project).first()


def _model(bridge_or_project_id):
    """The message model a link feeds: project chat or lab chat."""
    pid = getattr(bridge_or_project_id, "project_id", bridge_or_project_id)
    return ChatMessage if pid else LabChatMessage


def _call(account, method, url, **kwargs):
    """One interactive call; RemoteError with a message for the form when it fails."""
    try:
        resp = send(method, url, provider=PROVIDER, account=account, **kwargs)
    except AccountUnavailable as exc:
        raise RemoteError(
            {"space": ["Reconnect Google Chat in Integrations, then try again."]}
        ) from exc
    except IntegrationError as exc:
        raise RemoteError({"space": ["Google Chat did not answer. Try again."]}) from exc
    if resp.status_code == 200:
        return resp
    log.warning("google_chat %s answered %s", method, resp.status_code)
    if resp.status_code == 403:
        raise RemoteError(
            {
                "space": [
                    "Google refused. Google Chat works only with Google Workspace accounts, and "
                    "the site's Google project must have the Chat API turned on."
                ]
            }
        )
    raise RemoteError({"space": ["Google Chat refused the request. Try again."]})


KINDS = {"SPACE": "space", "GROUP_CHAT": "group_chat", "DIRECT_MESSAGE": "direct_message"}
LABELLED = 60  # unnamed group chats and messages named by their members, most recent first


def _member_names(account, space) -> list[str]:
    """The names Google will give for a conversation's other members, in listed order. Uses the
    name on the membership when Google sends one, else the Workspace directory. Cached briefly,
    so reopening the picker is cheap."""
    ckey = f"gchat-members:{account.lab_id}:{account.external_account_id}:{space}"
    cached = cache.get(ckey)
    if cached is not None:
        return cached
    try:
        resp = send(
            "GET",
            f"{API}/{quote(space, safe='/')}/members",
            provider=PROVIDER,
            account=account,
            params={"pageSize": 20},
        )
        rows = resp.json().get("memberships", []) if resp.status_code == 200 else []
        people = [(m.get("member") or {}) for m in rows if isinstance(m, dict)]
    except (AccountUnavailable, IntegrationError, ValueError, AttributeError):
        return []
    pairs = [
        (
            str(p.get("name", "")).removeprefix("users/"),
            "".join(c for c in str(p.get("displayName", "")) if c.isprintable())[:200],
        )
        for p in people
        if isinstance(p, dict) and p.get("type", "HUMAN") == "HUMAN"
    ]
    pairs = [(i, n) for i, n in pairs if i and i != account.external_account_id]
    directory = google_names(account, [i for i, n in pairs if not n])
    out = [n or directory.get(i, "") for i, n in pairs]
    out = [n for n in out if n]
    if out:
        cache.set(ckey, out, 600)
    return out


def member_map(account, space) -> dict[str, dict[str, str]]:
    """Google user id -> {"name", "photo"} from the conversation's own member list. Google puts a
    name on a membership when it will, which covers people the directory does not (outside the
    domain, or a connection made before the directory scope was granted). Cached briefly."""
    ckey = f"gchat-membermap:{account.lab_id}:{account.external_account_id}:{space}"
    cached = cache.get(ckey)
    if cached is not None:
        return cached
    out: dict[str, dict[str, str]] = {}
    token = ""
    for _ in range(5):  # up to 5 pages of 100
        params = {"pageSize": 100, **({"pageToken": token} if token else {})}
        try:
            resp = send(
                "GET",
                f"{API}/{quote(space, safe='/')}/members",
                provider=PROVIDER,
                account=account,
                params=params,
            )
            data = resp.json() if resp.status_code == 200 else {}
        except (AccountUnavailable, IntegrationError, ValueError, AttributeError):
            break
        for m in data.get("memberships", []) if isinstance(data, dict) else []:
            p = (m.get("member") or {}) if isinstance(m, dict) else {}
            uid = str(p.get("name", "")).removeprefix("users/")
            name = "".join(c for c in str(p.get("displayName", "")) if c.isprintable())[:200]
            if uid and name and p.get("type", "HUMAN") == "HUMAN":
                out[uid] = {"name": name, "photo": ""}
        token = str(data.get("nextPageToken", "")) if isinstance(data, dict) else ""
        if not token:
            break
    cache.set(ckey, out, 600)
    return out


def _people_for(account, space, ids) -> dict[str, dict[str, str]]:
    """Names for Google ids: the Workspace directory first, then the conversation's members."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    people = dict(google_people(account, ids))
    if any(i not in people for i in ids):
        for uid, person in member_map(account, space).items():
            if uid in ids and uid not in people:
                people[uid] = person
    return people


def _members_label(names: list[str]) -> str:
    """An unnamed group chat or direct message, named by its other members ("Ana, Ben +2")."""
    shown = names[:3]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" +{more}" if shown and more > 0 else "")


@interactive
def list_spaces(lab, user) -> list[dict]:
    """The conversations `user` is in, for a picker: spaces by name, then group chats and direct
    messages, most recently active first, named by their members (D325)."""
    account = own_account(lab, user)
    if account is None:
        raise RemoteError({"space": ["Connect Google Chat in Integrations first."]})
    resp = _call(account, "GET", f"{API}/spaces", params={"pageSize": 1000})
    try:
        spaces = resp.json().get("spaces", [])
        rows = [
            {
                "name": str(sp["name"]),
                "display_name": str(sp.get("displayName", ""))[:200],
                "kind": KINDS.get(str(sp.get("spaceType", "")), "space"),
                "active": _parse_time(sp.get("lastActiveTime")),
            }
            for sp in spaces
            if isinstance(sp, dict)
            and re.fullmatch(google_chat.SPACE_PATTERN, str(sp.get("name", "")))
        ]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RemoteError({"space": ["Google Chat sent an answer we could not read."]}) from exc
    named = sorted(
        (r for r in rows if r["kind"] == "space"), key=lambda r: r["display_name"].lower()
    )
    chats = sorted(
        (r for r in rows if r["kind"] != "space"),
        key=lambda r: r["active"] or timezone.now().replace(year=1970),
        reverse=True,
    )[:LABELLED]
    for r in chats:
        r["members"] = _member_names(account, r["name"])
        if not r["display_name"]:
            kind = "Direct message" if r["kind"] == "direct_message" else "Group chat"
            when = r["active"].strftime("%b %-d") if r["active"] else ""
            r["display_name"] = _members_label(r["members"]) or (
                f"{kind} · {when}" if when else kind
            )
    for r in named:
        r["members"] = []
    return [{k: r[k] for k in ("name", "display_name", "kind", "members")} for r in named + chats]


def _cursor(moment) -> str:
    """A time as Google's filter wants it, in UTC to the microsecond. Stored this way only, so
    cursors compare as times. A Google time with nanoseconds is cut to microseconds; the next
    read may then return that message again, and the unique `external_id` drops it."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_time(value):
    try:
        moment = parse_datetime(str(value))
    except (ValueError, TypeError):
        return None
    return moment if moment is not None and moment.tzinfo is not None else None


@interactive
@transaction.atomic
def link_space(*, lab, by, space, project=None, request=None) -> GoogleChatBridge:
    """Point the lab chat (or `project`'s chat) at `space`, read and posted through `by`'s own
    connection. Only messages sent from now on cross over: nothing older is copied either way.
    The lab chat needs `manage_lab_integrations`; a project chat `edit_project` (D325)."""
    _require_manage(by, lab, project)
    account = own_account(lab, by)
    if account is None:
        raise RemoteError({"space": ["Connect Google Chat in Integrations first."]})
    if not re.fullmatch(google_chat.SPACE_PATTERN, space or ""):
        raise ValidationError({"space": ["Pick a space from the list."]})
    # The space must be one this account is in; this is also where its name comes from.
    resp = _call(account, "GET", f"{API}/{quote(space, safe='/')}")
    try:
        data = resp.json()
        if data.get("name") != space:
            raise ValueError
        name = str(data.get("displayName", ""))[:200] or _members_label(
            _member_names(account, space)
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise RemoteError({"space": ["Google Chat sent an answer we could not read."]}) from exc
    bridge = _bridges(lab, project).select_for_update().first()
    if bridge is None:
        bridge = GoogleChatBridge(lab=lab, project=project)
    bridge.account = account
    bridge.created_by = by
    bridge.space = space
    bridge.space_name = name
    bridge.cursor = _cursor(timezone.now())
    bridge.last_error = ""
    bridge.last_polled_at = None
    bridge.save()
    record(
        AuditAction.GOOGLE_CHAT_LINKED,
        actor=by,
        lab=lab,
        target=bridge,
        request=request,
        metadata={"space": space, **({"project": str(project.pk)} if project else {})},
    )
    return bridge


def _bridges(lab, project):
    qs = GoogleChatBridge.objects.for_lab(lab)
    return qs.filter(project=project) if project else qs.filter(project__isnull=True)


def _require_manage(user, lab, project):
    if project is None:
        require(user, Perm.MANAGE_LAB_INTEGRATIONS, lab)
    else:
        require(user, Perm.EDIT_PROJECT, project)


@transaction.atomic
def unlink_space(*, lab, by, project=None, request=None) -> None:
    _require_manage(by, lab, project)
    bridge = _bridges(lab, project).select_for_update().first()
    if bridge is None:
        return
    record(
        AuditAction.GOOGLE_CHAT_UNLINKED,
        actor=by,
        lab=lab,
        target=bridge,
        request=request,
        metadata={"space": bridge.space, **({"project": str(project.pk)} if project else {})},
    )
    bridge.delete()


def _usable(bridge) -> bool:
    """The link works only while its connection is active and its owner still in the lab (and,
    for a project chat, still able to see the project)."""
    account = bridge.account
    return (
        account.status == AccountStatus.ACTIVE
        and account.user.is_active
        and lab_role(account.user, bridge.lab) is not None
        and (bridge.project_id is None or can(account.user, Perm.VIEW_PROJECT, bridge.project))
    )


def _fail(bridge, message) -> None:
    GoogleChatBridge.objects.for_lab(bridge.lab_id).filter(pk=bridge.pk).update(
        last_error=message[:200], last_polled_at=timezone.now()
    )


# ---------------------------------------------------------------- out: the lab chat to Google


def to_google_text(body: str) -> str:
    """Our stored markdown, as Google Chat writes it: mentions as plain "@Name", bold in single
    asterisks. Everything else (italics, strike, code, links) reads fine as it is."""
    return _BOLD.sub(r"*\1*", _MENTION.sub(r"@\1", body))


def queue_relay(message) -> None:
    """After the post commits: relay it, if its chat (lab or project) is linked."""
    project_id = getattr(message, "project_id", None)
    if not _bridges(message.lab_id, project_id).exists():
        return
    from labs import jobs

    lab_id, pk, pid = str(message.lab_id), str(message.pk), str(project_id or "")
    transaction.on_commit(lambda: jobs.relay_lab_chat_message.delay(lab_id, pk, pid), robust=True)


def _post(account, bridge, message, text) -> str | None:
    """Post `text` as `account`; the new message's name, or None when Google refused."""
    resp = send(
        "POST",
        f"{API}/{quote(bridge.space, safe='/')}/messages",
        provider=PROVIDER,
        account=account,
        params={"messageId": f"{CLIENT_PREFIX}{message.pk}"},
        json={"text": text},
    )
    if resp.status_code == 409:  # already posted under this id (a retry): nothing to do
        return ""
    if resp.status_code != 200:
        log.warning("google_chat post answered %s", resp.status_code)
        return None
    try:
        return str(resp.json()["name"])[:255]
    except (ValueError, KeyError, TypeError):
        return ""


def _plain_name(value) -> str:
    """A name safe to put in bold in Google: no asterisks, underscores or line breaks."""
    text = re.sub(r"[*_~`\s]+", " ", str(value or "")).strip()
    return "".join(c for c in text if c.isprintable())[:100]


def _relayed(message, text) -> str:
    """Text posted for someone through the link's connection. The email and the fixed marker
    can't be chosen by the member, unlike a display name (security review of D317)."""
    if not message.author_id:
        return text
    author = message.author
    name = _plain_name(author.display_name)
    who = f"{name} ({author.email})" if name else author.email
    return f"*{who}* via LabBench: {text}"


def relay(message) -> bool:
    """Post one chat message to its linked conversation. As its author when they have connected
    Google Chat and are in it; otherwise through the link's connection with their name first."""
    bridge = bridge_for(message.lab, getattr(message, "project", None))
    if bridge is None or message.source != ChatSource.APP or message.external_id:
        return False
    if not _usable(bridge):
        _fail(bridge, "The Google Chat connection that set this up is no longer active.")
        return False
    text = to_google_text(message.body)
    name = None
    try:
        mine = own_account(message.lab, message.author) if message.author_id else None
        if mine is not None and mine.pk != bridge.account_id:
            try:
                name = _post(mine, bridge, message, text)
            except (AccountUnavailable, IntegrationError):
                name = None
        elif mine is not None:  # the link's own owner: just them
            name = _post(mine, bridge, message, text)
        if name is None:
            name = _post(bridge.account, bridge, message, _relayed(message, text))
    except AccountUnavailable:
        _fail(bridge, "Reconnect Google Chat: the connection that set this up has expired.")
        return False
    except IntegrationError:
        raise  # temporary: the task retries
    if name is None:
        _fail(bridge, "Google Chat refused a message. Check the space still exists.")
        return False
    if name:
        type(message).objects.for_lab(message.lab_id).filter(pk=message.pk).update(external_id=name)
    return True


def delete_remote(lab, external_id, author_id, project=None) -> None:
    """Best effort: remove a message we posted, as whoever can (its author's own connection,
    then the link's). Google allows deleting your own messages only, so one of them can."""
    bridge = bridge_for(lab, project)
    if bridge is None or not external_id.startswith(bridge.space + "/messages/"):
        return
    accounts = []
    if author_id:
        mine = (
            ConnectedAccount.objects.for_lab(lab)
            .filter(user_id=author_id, provider=PROVIDER.name, status=AccountStatus.ACTIVE)
            .first()
        )
        if mine is not None:
            accounts.append(mine)
    accounts.append(bridge.account)
    for account in accounts:
        try:
            resp = send(
                "DELETE",
                f"{API}/{quote(external_id, safe='/')}",
                provider=PROVIDER,
                account=account,
            )
        except (AccountUnavailable, IntegrationError):
            continue
        if resp.status_code in (200, 404):
            return


# ---------------------------------------------------------------- in: Google to the lab chat


def from_google_text(message: dict) -> str:
    """A Google message as lab chat text. Our mention syntax is broken up, so text from Google
    can never draw a mention chip or notify anyone here."""
    text = str(message.get("text") or "").strip()
    if not text:
        if message.get("attachment"):
            return "_Sent an attachment in Google Chat._"
        return ""
    text = text.replace("@[", "@​[")
    if len(text) > MAX_BODY:
        text = text[: MAX_BODY - 1] + "…"
    return text


NAME_CACHE = 24 * 3600
REACTION_REFRESH_SECONDS = 120  # per link: how often reactions on recent messages are re-read
REACTION_WINDOW = 100  # the latest messages whose reactions are re-read


def _photo_url(value) -> str:
    """A Google profile picture address, only if it is https on Google's image host."""
    url = str(value or "")
    m = re.fullmatch(r"https://([a-z0-9-]+\.)*googleusercontent\.com/[^\s\"'<>]{1,400}", url)
    return url if m else ""


def google_people(account, user_ids) -> dict[str, dict[str, str]]:
    """Google user id -> {"name", "photo"}, from the Workspace directory (D320). Best effort:
    whatever Google will not name (outside the domain, a failure) is simply missing. Cached a day
    per lab; a failed lookup is never cached, so it cannot hide a colleague for a day."""
    ids = sorted({i for i in user_ids if re.fullmatch(r"[0-9]{1,40}", i or "")})
    keys = {i: f"gchat-person:{account.lab_id}:{i}" for i in ids}
    found = cache.get_many(list(keys.values()))  # keyed by cache key
    out = {i: found[k] for i, k in keys.items() if k in found}
    missing = [i for i in ids if i not in out][:200]
    if missing:
        try:
            resp = send(
                "GET",
                f"{google_chat.PEOPLE}/people:batchGet",
                provider=PROVIDER,
                account=account,
                params={
                    "resourceNames": [f"people/{i}" for i in missing],
                    "personFields": "names,photos",
                    "sources": [
                        "READ_SOURCE_TYPE_DOMAIN_PROFILE",
                        "READ_SOURCE_TYPE_DOMAIN_CONTACT",
                    ],
                },
            )
            ok = resp.status_code == 200
            if not ok:
                log.warning("Google directory lookup failed: HTTP %s", resp.status_code)
            rows = resp.json().get("responses", []) if ok else []
        except (AccountUnavailable, IntegrationError, ValueError, AttributeError):
            ok, rows = False, []
        fresh = {}
        for row in rows if isinstance(rows, list) else []:
            try:
                person = row["person"]
                pid = str(person["resourceName"]).removeprefix("people/")
                name = str(person["names"][0]["displayName"])
            except (KeyError, IndexError, TypeError):
                continue
            photo = ""
            for ph in person.get("photos") or []:
                if isinstance(ph, dict) and not ph.get("default"):
                    photo = _photo_url(ph.get("url"))
                    break
            if pid in keys:
                fresh[pid] = {
                    "name": "".join(c for c in name if c.isprintable())[:200],
                    "photo": photo,
                }
        # Unknown ids are cached as empty so a stranger's id isn't looked up on every poll, but
        # only when Google answered.
        empty = {"name": "", "photo": ""}
        if ok:
            # A blank answer is remembered for an hour only, so fixing the connection (a fresh
            # sign-in that grants the directory scope) shows names soon, not tomorrow.
            cache.set_many({keys[i]: fresh[i] for i in fresh}, NAME_CACHE)
            cache.set_many({keys[i]: empty for i in missing if i not in fresh}, 3600)
        else:
            cache.set_many({keys[i]: v for i, v in fresh.items()}, NAME_CACHE)
        out.update(fresh)
    return {i: v for i, v in out.items() if v.get("name")}


def google_names(account, user_ids) -> dict[str, str]:
    """Google user id -> name; see `google_people`."""
    return {i: v["name"] for i, v in google_people(account, user_ids).items()}


def _authors(lab, project=None) -> dict[str, object]:
    """Google user id -> lab member (who can see `project`, if given), from members' active
    Google Chat connections. The id was named by Google when they connected, so no one can
    claim someone else's."""
    rows = (
        ConnectedAccount.objects.for_lab(lab)
        .filter(provider=PROVIDER.name)
        .select_related("user")
        .order_by("connected_at")
    )
    holders: dict[str, set] = {}
    users = {}
    for r in rows:
        if (
            r.status == AccountStatus.ACTIVE
            and r.user.is_active
            and lab_role(r.user, lab)
            and (project is None or can(r.user, Perm.VIEW_PROJECT, project))
        ):
            holders.setdefault(r.external_account_id, set()).add(r.user_id)
            users[r.user_id] = r.user
    # A Google account several members connected (a shared login) credits none of them.
    return {gid: users[next(iter(ids))] for gid, ids in holders.items() if len(ids) == 1}


def poll(bridge) -> int:
    """Read the conversation's new messages into its chat. Returns how many were added."""
    if not _usable(bridge):
        _fail(bridge, "The Google Chat connection that set this up is no longer active.")
        return 0
    try:
        resp = send(
            "GET",
            f"{API}/{quote(bridge.space, safe='/')}/messages",
            provider=PROVIDER,
            account=bridge.account,
            params={
                "pageSize": PAGE,
                "orderBy": "createTime ASC",
                "filter": f'createTime > "{bridge.cursor}"',
            },
        )
    except AccountUnavailable:
        _fail(bridge, "Reconnect Google Chat: the connection that set this up has expired.")
        return 0
    except IntegrationError:
        _fail(bridge, "Google Chat did not answer.")
        return 0
    if resp.status_code != 200:
        log.warning("google_chat list answered %s", resp.status_code)
        _fail(bridge, "Google Chat refused to read the space. Is the connection still in it?")
        return 0
    try:
        items = resp.json().get("messages", [])
        if not isinstance(items, list):
            raise TypeError
    except (ValueError, TypeError, AttributeError):
        _fail(bridge, "Google Chat sent an answer we could not read.")
        return 0

    started = timezone.now()
    authors = _authors(bridge.lab, bridge.project)
    model = _model(bridge)
    where = {"project": bridge.project} if bridge.project_id else {}
    # Names and pictures for everyone who wrote: a member's Google picture is the fallback when
    # they have none here, and a stranger's is all there is.
    senders = {
        str((i.get("sender") or {}).get("name", "")).removeprefix("users/")
        for i in items
        if isinstance(i, dict) and isinstance(i.get("sender"), dict)
    }
    people = _people_for(bridge.account, bridge.space, senders)
    added = 0
    cursor = bridge.cursor
    room = INBOUND_PER_HOUR - (
        model.objects.for_lab(bridge.lab_id)
        .filter(
            source=ChatSource.GOOGLE_CHAT,
            created_at__gte=timezone.now() - timedelta(hours=1),
            **where,
        )
        .count()
    )
    paused = ""
    for item in items:
        if added >= room:
            paused = "Paused: too many messages from Google Chat this hour. The rest come later."
            break  # the cursor stays before this one, so nothing is lost
        try:
            name = str(item["name"])
            created = _parse_time(item["createTime"])
            sender = item.get("sender") or {}
        except (KeyError, TypeError, AttributeError):
            continue
        if created is None or not isinstance(sender, dict):
            continue
        cursor = max(cursor, _cursor(created))
        if not name.startswith(bridge.space + "/messages/") or len(name) > 255:
            continue
        client_id = str(item.get("clientAssignedMessageId", ""))
        echoed = None
        if client_id.startswith(CLIENT_PREFIX):
            # One of ours. Skip it where it was written; another chat linked to the same
            # conversation takes it in under its writer's name.
            echoed = _written_elsewhere(bridge, client_id.removeprefix(CLIENT_PREFIX))
            if echoed is None:
                continue
        elif sender.get("type") != "HUMAN":
            continue  # apps and bots stay in Google
        body = echoed.body if echoed else from_google_text(item)
        if not body:
            continue
        user_id = str(sender.get("name", "")).removeprefix("users/")
        author = echoed.author if echoed else authors.get(user_id)
        external_author = external_avatar = ""
        if author is None and not echoed:
            person = people.get(user_id, {})
            external_author = str(
                person.get("name") or sender.get("displayName") or UNKNOWN_SENDER
            )[:200]
            external_avatar = person.get("photo", "")
        elif not echoed:
            external_avatar = people.get(user_id, {}).get("photo", "")
        try:
            with transaction.atomic():
                model.objects.create(
                    **where,
                    lab=bridge.lab,
                    author=author,
                    external_author=external_author,
                    external_avatar=external_avatar,
                    body=body,
                    source=ChatSource.GOOGLE_CHAT,
                    external_id=name,
                    external_reactions=clean_external(item.get("emojiReactionSummaries")),
                )
            added += 1
        except IntegrityError:
            continue  # already here
    GoogleChatBridge.objects.for_lab(bridge.lab_id).filter(pk=bridge.pk).update(
        cursor=cursor, last_polled_at=timezone.now(), last_error=paused
    )
    _repair_names(bridge, authors, model, where, started)
    refresh_reactions(bridge, model, where)
    return added


def _written_elsewhere(bridge, key):
    """The app message a post to Google came from, if it was written in a different chat than
    `bridge`'s: that is a message to carry in. None when it was written here, or is unknown."""
    try:
        pk = uuid.UUID(key)
    except ValueError:
        return None
    where = {"project": bridge.project} if bridge.project_id else {}
    if _model(bridge).objects.for_lab(bridge.lab_id).filter(pk=pk, **where).exists():
        return None
    for model in (LabChatMessage, ChatMessage):
        found = model.objects.for_lab(bridge.lab_id).filter(pk=pk).select_related("author").first()
        if found is not None:
            return found
    return None


def _repair_names(bridge, authors, model, where, before) -> None:
    """Messages that came in as "Someone on Google Chat" get their real name once Google will give
    it (a reconnect that grants the directory, say). Looks at the latest 1000 messages, at most
    once an hour per conversation, and only when there is something to fix."""
    unknown = list(
        model.objects.for_lab(bridge.lab_id)
        .filter(
            **where,
            source=ChatSource.GOOGLE_CHAT,
            external_author=UNKNOWN_SENDER,
            created_at__lt=before,  # not the ones this very poll just brought in
        )
        .values_list("pk", "external_id")[:1000]
    ) + list(
        model.objects.for_lab(bridge.lab_id)
        .filter(
            **where,
            source=ChatSource.GOOGLE_CHAT,
            external_avatar="",
            created_at__lt=before,
        )
        .exclude(external_author=UNKNOWN_SENDER)
        .values_list("pk", "external_id")[:1000]
    )
    if not unknown or not cache.add(f"gchat-repair:{bridge.pk}", 1, 3600):
        return
    try:
        items = _messages(
            bridge.account,
            bridge.space,
            params={"pageSize": 1000, "orderBy": "createTime DESC"},
        )
    except ValidationError:
        return
    sender_of = {
        str(i.get("name", "")): str((i.get("sender") or {}).get("name", "")).removeprefix("users/")
        for i in items
        if isinstance(i.get("sender"), dict)
    }
    ids = {uid for ext, uid in sender_of.items() if uid} - set(authors)
    people = _people_for(bridge.account, bridge.space, ids)
    for pk, ext in unknown:
        uid = sender_of.get(ext, "")
        person = people.get(uid, {})
        if not person.get("name"):
            continue
        # a member's own name stays theirs (it comes from their account); only the picture is added
        fix = {} if uid in authors else {"external_author": person["name"][:200]}
        if person.get("photo"):
            fix["external_avatar"] = person["photo"]
        if fix:
            model.objects.for_lab(bridge.lab_id).filter(pk=pk).update(**fix)


def refresh_reactions(bridge, model, where) -> int:
    """People react after a message arrives, and the poll only reads messages newer than its
    cursor, so every couple of minutes the latest few are read again and their reaction counts
    brought up to date. Returns how many messages changed. Best effort: a failure changes nothing.
    """
    if not cache.add(f"gchat-reactions:{bridge.pk}", 1, REACTION_REFRESH_SECONDS):
        return 0
    try:
        items = _messages(
            bridge.account,
            bridge.space,
            params={"pageSize": REACTION_WINDOW, "orderBy": "createTime DESC"},
        )
    except ValidationError:
        return 0
    now = {
        str(i.get("name", "")): clean_external(i.get("emojiReactionSummaries"))
        for i in items
        if str(i.get("name", "")).startswith(bridge.space + "/messages/")
    }
    if not now:
        return 0
    changed = 0
    rows = model.objects.for_lab(bridge.lab_id).filter(**where, external_id__in=list(now))
    for pk, ext, have in rows.values_list("pk", "external_id", "external_reactions"):
        if (have or {}) != now[ext]:
            model.objects.for_lab(bridge.lab_id).filter(pk=pk).update(external_reactions=now[ext])
            changed += 1
    return changed


def poll_all() -> int:
    """The scheduled run: every link, lab by lab, never two runs on one link."""
    from labs.models import Lab

    added = 0
    for lab in Lab.objects.all():  # lab by lab, as every job does (D49)
        bridges = GoogleChatBridge.objects.for_lab(lab).select_related(
            "lab", "project", "account", "account__user"
        )
        for bridge in bridges:
            key = f"google-chat-poll:{bridge.pk}"
            if not cache.add(key, 1, LOCK_SECONDS):
                continue
            try:
                added += poll(bridge)
            except Exception:  # noqa: BLE001 - one link's failure never stops the others
                log.exception("google_chat poll failed")
            finally:
                cache.delete(key)
    return added


# ------------------------------------------------------- importing into a chat (D320, D327)

THREAD_SCAN = 500  # recent messages read to find a space's threads
THREAD_MAX = 1000  # messages imported from one thread at most
THREADS_SHOWN = 50


def _need_account(lab, user):
    account = own_account(lab, user)
    if account is None:
        raise RemoteError({"space": ["Connect Google Chat in Integrations first."]})
    return account


def _space_ok(space):
    if not re.fullmatch(google_chat.SPACE_PATTERN, space or ""):
        raise ValidationError({"space": ["Pick a space from the list."]})


def _messages(account, space, *, params) -> list[dict]:
    resp = _call(account, "GET", f"{API}/{quote(space, safe='/')}/messages", params=params)
    try:
        items = resp.json().get("messages", [])
        return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
    except (ValueError, AttributeError):
        return []


def _snippet(text, limit=120) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


@interactive
def list_threads(lab, user, space) -> list[dict]:
    """The space's recently active threads, newest first: id, first words, how many messages
    (among the recent ones read) and when the last was sent. Read as `user`, so only spaces
    they are in can be read."""
    _space_ok(space)
    account = _need_account(lab, user)
    items = _messages(
        account, space, params={"pageSize": THREAD_SCAN, "orderBy": "createTime DESC"}
    )
    threads: dict[str, dict] = {}
    for item in reversed(items):  # oldest first, so the first text seen opens the thread
        name = str((item.get("thread") or {}).get("name", ""))
        created = _parse_time(item.get("createTime"))
        if not name.startswith(space + "/threads/") or created is None:
            continue
        if not re.fullmatch(google_chat.THREAD_PATTERN, name):
            continue
        t = threads.setdefault(name, {"name": name, "first": "", "count": 0, "last_at": created})
        t["count"] += 1
        t["last_at"] = max(t["last_at"], created)
        if not t["first"]:
            t["first"] = _snippet(item.get("text") or "")
    rows = sorted(threads.values(), key=lambda t: t["last_at"], reverse=True)
    return rows[:THREADS_SHOWN]


@interactive
def import_messages(*, lab, user, space, thread="", project=None, request=None) -> dict:
    """Copy one thread, or with no `thread` the conversation's latest messages, into the lab
    chat or `project`'s chat (D327). Read as `user`, so only conversations they are in. Each
    message keeps its sender (a member, as for synced messages, else their Google name) and its
    time, so it sits in the history where it was said and never counts as unread. Already-copied
    or synced messages are skipped. Nothing is sent back to Google, no one is notified and our
    mention syntax is broken up, as for synced messages (D316). Only whoever may link that chat
    may import into it, since the messages appear under other people's names."""
    _require_manage(user, lab, project)
    _space_ok(space)
    if thread and (
        not re.fullmatch(google_chat.THREAD_PATTERN, thread)
        or not thread.startswith(space + "/threads/")
    ):
        raise ValidationError({"thread": ["Pick a thread from the list."]})
    account = _need_account(lab, user)
    if thread:
        items = _messages(
            account,
            space,
            params={
                "pageSize": THREAD_MAX,
                "orderBy": "createTime ASC",
                "filter": f'thread.name = "{thread}"',
            },
        )
        items = [i for i in items if str((i.get("thread") or {}).get("name", "")) == thread]
    else:
        latest = _messages(
            account, space, params={"pageSize": THREAD_MAX, "orderBy": "createTime DESC"}
        )
        items = list(reversed(latest))

    model = _model(project.pk if project else None)
    where = {"project": project} if project else {}
    authors = _authors(lab, project)
    ids = {
        str((i.get("sender") or {}).get("name", "")).removeprefix("users/")
        for i in items
        if isinstance(i.get("sender"), dict)
    }
    people = _people_for(account, space, ids)
    known = {
        ext: (pk, who, pic)
        for ext, pk, who, pic in model.objects.for_lab(lab)
        .filter(**where, external_id__in=[str(i.get("name", "")) for i in items])
        .values_list("external_id", "pk", "external_author", "external_avatar")
    }
    known_reacts = dict(
        model.objects.for_lab(lab)
        .filter(**where, external_id__in=list(known))
        .values_list("external_id", "external_reactions")
    )
    imported = skipped = 0
    now = timezone.now()
    for item in items:
        name = str(item.get("name", ""))
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        created = _parse_time(item.get("createTime"))
        if (
            not name.startswith(space + "/messages/")
            or len(name) > 255
            or created is None
            or sender.get("type") != "HUMAN"
        ):
            continue
        uid = str(sender.get("name", "")).removeprefix("users/")
        person = people.get(uid, {})
        if name in known:
            # Fill in a name or picture that was missing when the message first came in.
            pk, who, pic = known[name]
            fix = {}
            if who in ("", UNKNOWN_SENDER) and person.get("name") and uid not in authors:
                fix["external_author"] = person["name"]
            if not pic and person.get("photo"):
                fix["external_avatar"] = person["photo"]
            reacts = clean_external(item.get("emojiReactionSummaries"))
            if reacts != (known_reacts.get(name) or {}):
                fix["external_reactions"] = reacts
            if fix:
                model.objects.for_lab(lab).filter(pk=pk).update(**fix)
            skipped += 1
            continue
        body = from_google_text(item)
        if not body:
            continue
        author = authors.get(uid)
        try:
            with transaction.atomic():
                row = model.objects.create(
                    **where,
                    lab=lab,
                    author=author,
                    external_author="" if author else (person.get("name") or UNKNOWN_SENDER)[:200],
                    external_avatar=person.get("photo", ""),
                    body=body,
                    source=ChatSource.GOOGLE_CHAT,
                    external_id=name,
                    external_reactions=clean_external(item.get("emojiReactionSummaries")),
                )
                # Its own time, never later than now (created_at is set on create).
                model.objects.for_lab(lab).filter(pk=row.pk).update(created_at=min(created, now))
            imported += 1
        except IntegrityError:
            skipped += 1
    record(
        AuditAction.GOOGLE_CHAT_IMPORTED,
        actor=user,
        lab=lab,
        target=project or lab,
        request=request,
        metadata={
            "space": space,
            "thread": thread,
            "imported": imported,
            "skipped": skipped,
            **({"project": str(project.pk)} if project else {}),
        },
    )
    return {"imported": imported, "skipped": skipped}
