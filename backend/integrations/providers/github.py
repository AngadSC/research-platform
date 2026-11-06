"""GitHub (ARCHITECTURE section 9, D105 to D107). A fine-grained personal access token with
read-only repository permissions (Metadata, and Contents for commit history), pasted as the API
key. Metadata only: repository and commit records, never file contents, archives or raw files."""

import re
from urllib.parse import quote, urlencode

from django.utils.dateparse import parse_datetime
from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider

API = "https://api.github.com"
_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
_REPO = r"(?!\.{1,2}(?:@|$|/))[A-Za-z0-9_.-]{1,100}"
_SHA = r"[0-9a-f]{40}"
_ID = re.compile(rf"(?P<owner>{_OWNER})/(?P<repo>{_REPO})(?:@(?P<sha>{_SHA}))?")


def _split(external_id):
    m = _ID.fullmatch(external_id)
    if m is None:
        raise http.IntegrationError("GitHub: not a repository or commit id")
    return m["owner"], m["repo"], m["sha"]


def _repo_path(owner, repo):
    return f"{API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"


@sensitive_variables()
def _sign(kwargs, key, secret):
    headers = {
        **kwargs.get("headers", {}),
        "Authorization": f"Bearer {key}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return {**kwargs, "headers": headers}


def _identity(data):
    return str(data["id"]), str(data.get("login", ""))


def _get(account, url):
    resp = http.send("GET", url, provider=PROVIDER, account=account)
    # missing or no access (GitHub says 404), unknown sha (422), empty repository (409), blocked
    if resp.status_code in (404, 409, 410, 422, 451):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("GitHub did not answer the request")
    return resp


def _first_line(message):
    lines = (message or "").splitlines()
    return lines[0][:200] if lines else ""


def fetch_item(account, external_id):
    """A repository (`owner/repo`) or one commit (`owner/repo@<sha>`), metadata only. A commit
    comes from the commit list (one entry), never the single-commit endpoint, which carries
    file diffs. None = gone: 404 (also what GitHub says for a repository the token can't see)."""
    owner, repo, sha = _split(external_id)
    base = _repo_path(owner, repo)
    try:
        if sha is None:
            resp = _get(account, base)
            if resp is None:
                return None
            data = resp.json()
            pushed = data.get("pushed_at") or ""
            return {
                "title": data["full_name"],
                "url": data["html_url"],
                "mime_type": "",
                "modified_at": parse_datetime(pushed) if pushed else None,
                "version": pushed,
                "checksum": "",
                "default_branch": data.get("default_branch", ""),
                "repo_url": data["html_url"],
                "commit": "",
            }
        resp = _get(account, f"{base}/commits?{urlencode({'sha': sha, 'per_page': 1})}")
        rows = resp.json() if resp is not None else []
        if not rows or rows[0]["sha"] != sha:
            return None
        row = rows[0]
        note = _first_line(row["commit"].get("message"))
        return {
            "title": f"{owner}/{repo}@{sha[:7]} {note}".strip(),
            "url": row["html_url"],
            "mime_type": "",
            "modified_at": parse_datetime(row["commit"]["committer"]["date"]),
            "version": sha,
            "checksum": "",
            "repo_url": f"https://github.com/{owner}/{repo}",
            "commit": sha,
        }
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise http.IntegrationError("GitHub returned an unreadable answer") from None


def _repo_row(d):
    pushed = d.get("pushed_at")
    row = {
        "id": d["full_name"],
        "title": d["full_name"],
        "subtitle": (d.get("description") or "")[:120],
        "modified": parse_datetime(pushed) if pushed else None,
        "url": d["html_url"],
    }
    return row if _ID.fullmatch(row["id"]) else None


def search_items(account, query, target_kind):
    """The person's repositories (newest push first; a typed word filters by name). A query that
    names a repository (`owner/repo`) lists that repository and its latest commits."""
    query = (query or "").strip()
    try:
        m = _ID.fullmatch(query)
        if m and not m["sha"]:
            base = _repo_path(m["owner"], m["repo"])
            repo = _get(account, base)
            if repo is None:
                return []
            row = _repo_row(repo.json())
            commits = _get(account, f"{base}/commits?{urlencode({'per_page': 20})}")
            out = [row] if row else []
            for c in commits.json() if commits is not None else []:
                if not re.fullmatch(_SHA, c["sha"]):
                    continue
                note = _first_line(c["commit"].get("message"))
                out.append(
                    {
                        "id": f"{m['owner']}/{m['repo']}@{c['sha']}",
                        "title": f"{c['sha'][:7]} {note}".strip(),
                        "subtitle": (c["commit"].get("author") or {}).get("name", ""),
                        "modified": parse_datetime(c["commit"]["committer"]["date"]),
                        "url": c["html_url"],
                    }
                )
            return out
        resp = _get(account, f"{API}/user/repos?{urlencode({'per_page': 100, 'sort': 'pushed'})}")
        rows = [_repo_row(d) for d in (resp.json() if resp is not None else [])]
        return [r for r in rows if r and query.lower() in r["id"].lower()][:20]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("GitHub returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D86: an analysis' empty code reference takes the repository address and, for a commit
    link, the full commit hash. Written only into empty fields."""
    if kind != "analysis":
        return {}
    return {"code_repo_url": meta.get("repo_url", ""), "code_commit": meta.get("commit", "")}


class _GitHub(Provider):
    def parse_url(self, url, instance_host=""):
        """A commit address names the commit: the id is `owner/repo@<sha>`."""
        base = super().parse_url(url, instance_host)
        if base is None:
            return None
        sha = re.fullmatch(self.url_pattern, url.strip())["sha"]
        return f"{base}@{sha}" if sha else base


PROVIDER = _GitHub(
    name="github",
    label="GitHub",
    auth_type=AuthType.API_KEY,
    category=Category.CODE,
    icon="github",
    link_targets=frozenset({"project", "analysis", "result", "dataset", "manuscript"}),
    link_methods=("search", "paste_url"),
    connect_fields=(
        ConnectField(
            "api_key",
            "Fine-grained access token",
            "GitHub > Settings > Developer settings > Fine-grained tokens. Choose only the "
            "repositories to link and give read-only Metadata and Contents. Add nothing else.",
        ),
    ),
    identity_url=f"{API}/user",
    parse_identity=_identity,
    sign=_sign,
    api_hosts=frozenset({"api.github.com"}),
    link_hosts=frozenset({"github.com"}),
    fetch_item=fetch_item,
    search_items=search_items,
    external_id_pattern=rf"^{_OWNER}/{_REPO}(?:@{_SHA})?$",
    url_pattern=rf"https://github\.com/(?P<id>{_OWNER}/{_REPO})(?:/commit/(?P<sha>{_SHA}))?/?",
    apply_to_target=apply_to_target,
)
