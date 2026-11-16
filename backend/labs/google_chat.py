"""The lab chat, or a project's chat, and one Google Chat conversation, both ways (D315 to D325).

A conversation is a space, a group chat or a direct message: Google names all three
`spaces/<id>`. Each chat links to at most one, and each conversation to at most one chat.

Out: each chat message is posted there as its author, through their own Google Chat connection; a
member who has not connected (or is not in it) is posted by the connection that set the link up,
with their name in front (D317). In: the conversation is read every few seconds (`poll_all`,
Celery beat) and new messages are added to the chat (D316).

Every call goes through `integrations.http.send` with a connected account, so the host allow-list,
token refresh, timeouts and the account's status rules all apply. Nothing but message text and
the sender goes either way: no attachments, reactions or edits.
"""

import logging
import re
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
LABELLED = 20  # unnamed group chats and messages named by their members, most recent first


def _member_names(account, space) -> list[str]:
    """The names Google will give for a conversation's other members, in listed order."""
    try:
        resp = send(
            "GET",
            f"{API}/{quote(space, safe='/')}/members",
            provider=PROVIDER,
            account=account,
            params={"pageSize": 20},
        )
        rows = resp.json().get("memberships", []) if resp.status_code == 200 else []
        ids = [
            str((m.get("member") or {}).get("name", "")).removeprefix("users/")
            for m in rows
            if isinstance(m, dict)
        ]
    except (AccountUnavailable, IntegrationError, ValueError, AttributeError):
        return []
    ids = [i for i in ids if i and i != account.external_account_id]
    names = google_names(account, ids)
    return [names[i] for i in ids if i in names]


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
            r["display_name"] = _members_label(r["members"]) or (
                "Direct message" if r["kind"] == "direct_message" else "Group chat"
            )
    for r in named:
        r["members"] = []
    return [
        {k: r[k] for k in ("name", "display_name", "kind", "members")} for r in named + chats
    ]


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
    others = GoogleChatBridge.objects.for_lab(lab).filter(space=space)
    if bridge is not None:
        others = others.exclude(pk=bridge.pk)
    if others.exists():  # one conversation feeds one chat
        raise ValidationError(
            {"space": ["That conversation is already linked to another chat here."]}
        )
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


def google_names(account, user_ids) -> dict[str, str]:
    """Google user id -> name, from the Workspace directory (D320). Best effort: whatever Google
    will not name (outside the domain, a failure) is simply missing. Cached a day per lab."""
    ids = sorted({i for i in user_ids if re.fullmatch(r"[0-9]{1,40}", i or "")})
    keys = {i: f"gchat-name:{account.lab_id}:{i}" for i in ids}
    found = cache.get_many(list(keys.values()))  # keyed by cache key
    out = {i: found[k] for i, k in keys.items() if k in found}
    missing = [i for i in ids if i not in out][:200]
    if not missing:
        return {i: n for i, n in out.items() if n}
    try:
        resp = send(
            "GET",
            f"{google_chat.PEOPLE}/people:batchGet",
            provider=PROVIDER,
            account=account,
            params={
                "resourceNames": [f"people/{i}" for i in missing],
                "personFields": "names",
                "sources": [
                    "READ_SOURCE_TYPE_DOMAIN_PROFILE",
                    "READ_SOURCE_TYPE_DOMAIN_CONTACT",
                ],
            },
        )
        rows = resp.json().get("responses", []) if resp.status_code == 200 else []
    except (AccountUnavailable, IntegrationError, ValueError, AttributeError):
        rows = []
    fresh = {}
    for row in rows if isinstance(rows, list) else []:
        try:
            pid = str(row["person"]["resourceName"]).removeprefix("people/")
            name = str(row["person"]["names"][0]["displayName"])
        except (KeyError, IndexError, TypeError):
            continue
        if pid in keys:
            fresh[pid] = "".join(c for c in name if c.isprintable())[:200]
    # Unknown ids are cached as "" so a stranger's id isn't looked up on every poll.
    cache.set_many({keys[i]: fresh.get(i, "") for i in missing}, NAME_CACHE)
    out.update(fresh)
    return {i: n for i, n in out.items() if n}


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

    authors = _authors(bridge.lab, bridge.project)
    model = _model(bridge)
    where = {"project": bridge.project} if bridge.project_id else {}
    strangers = {
        str((i.get("sender") or {}).get("name", "")).removeprefix("users/")
        for i in items
        if isinstance(i, dict) and isinstance(i.get("sender"), dict)
    } - set(authors)
    names = google_names(bridge.account, strangers) if strangers else {}
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
        if str(item.get("clientAssignedMessageId", "")).startswith(CLIENT_PREFIX):
            continue  # one of ours
        if sender.get("type") != "HUMAN":
            continue  # apps and bots stay in Google
        body = from_google_text(item)
        if not body:
            continue
        user_id = str(sender.get("name", "")).removeprefix("users/")
        author = authors.get(user_id)
        external_author = ""
        if author is None:
            external_author = str(
                names.get(user_id) or sender.get("displayName") or UNKNOWN_SENDER
            )[:200]
        try:
            with transaction.atomic():
                model.objects.create(
                    **where,
                    lab=bridge.lab,
                    author=author,
                    external_author=external_author,
                    body=body,
                    source=ChatSource.GOOGLE_CHAT,
                    external_id=name,
                )
            added += 1
        except IntegrityError:
            continue  # already here
    GoogleChatBridge.objects.for_lab(bridge.lab_id).filter(pk=bridge.pk).update(
        cursor=cursor, last_polled_at=timezone.now(), last_error=paused
    )
    return added


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
    names = google_names(account, ids - set(authors)) if ids - set(authors) else {}
    known = set(
        model.objects.for_lab(lab)
        .filter(external_id__in=[str(i.get("name", "")) for i in items])
        .values_list("external_id", flat=True)
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
        if name in known:
            skipped += 1
            continue
        body = from_google_text(item)
        if not body:
            continue
        uid = str(sender.get("name", "")).removeprefix("users/")
        author = authors.get(uid)
        try:
            with transaction.atomic():
                row = model.objects.create(
                    **where,
                    lab=lab,
                    author=author,
                    external_author="" if author else (names.get(uid) or UNKNOWN_SENDER)[:200],
                    body=body,
                    source=ChatSource.GOOGLE_CHAT,
                    external_id=name,
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
