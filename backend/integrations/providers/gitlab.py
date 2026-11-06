"""GitLab (ARCHITECTURE section 9, D105, D108). A personal access token with the `read_api` scope
as the API key, on gitlab.com or a self-hosted server (the account's instance URL, D82). Metadata
only: project and commit records, never file contents, archives or raw files."""

import re
from urllib.parse import quote, urlencode

from django.utils.dateparse import parse_datetime
from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider

_SEG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}"
_PATH = rf"{_SEG}(?:/{_SEG}){{1,19}}"  # group/project, with subgroups
_SHA = r"[0-9a-f]{40}"
_ID = re.compile(rf"(?P<path>{_PATH})(?:@(?P<sha>{_SHA}))?")


def _split(external_id):
    m = _ID.fullmatch(external_id)
    if m is None or any(s in (".", "..") for s in m["path"].split("/")):
        raise http.IntegrationError("GitLab: not a project or commit id")
    return m["path"], m["sha"]


def _project_url(account, path):
    return f"{account.instance_url}/api/v4/projects/{quote(path, safe='')}"


@sensitive_variables()
def _sign(kwargs, key, secret):
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "PRIVATE-TOKEN": key}}


def _identity(data):
    return str(data["id"]), str(data.get("username", ""))


def _get(account, url):
    resp = http.send("GET", url, provider=PROVIDER, account=account)
    if resp.status_code in (404, 410):  # missing, or no access (GitLab says 404)
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("GitLab did not answer the request")
    return resp


def _first_line(message):
    lines = (message or "").splitlines()
    return lines[0][:200] if lines else ""


def fetch_item(account, external_id):
    """A project (`group/project`) or one commit (`group/project@<sha>`), metadata only."""
    path, sha = _split(external_id)
    base = _project_url(account, path)
    try:
        resp = _get(account, base)
        if resp is None:
            return None
        project = resp.json()
        if sha is None:
            active = project.get("last_activity_at") or ""
            return {
                "title": project["path_with_namespace"],
                "url": project["web_url"],
                "mime_type": "",
                "modified_at": parse_datetime(active) if active else None,
                "version": active,
                "checksum": "",
                "default_branch": project.get("default_branch") or "",
                "repo_url": project["web_url"],
                "commit": "",
            }
        resp = _get(account, f"{base}/repository/commits/{sha}")
        if resp is None:
            return None
        row = resp.json()
        if row["id"] != sha:
            return None
        return {
            "title": f"{path}@{sha[:7]} {_first_line(row.get('title'))}".strip(),
            "url": row["web_url"],
            "mime_type": "",
            "modified_at": parse_datetime(row["committed_date"]),
            "version": sha,
            "checksum": "",
            "repo_url": project["web_url"],
            "commit": sha,
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("GitLab returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """The person's projects (latest activity first; a typed word searches by name). A query that
    names a project (`group/project`) lists that project and its latest commits."""
    query = (query or "").strip()
    try:
        m = _ID.fullmatch(query)
        if m and not m["sha"] and "/" in query:
            path, _ = _split(query)
            base = _project_url(account, path)
            resp = _get(account, base)
            if resp is None:
                return []
            project = resp.json()
            commits = _get(account, f"{base}/repository/commits?{urlencode({'per_page': 20})}")
            out = [_project_row(project)]
            for c in commits.json() if commits is not None else []:
                if not re.fullmatch(_SHA, c["id"]):
                    continue
                out.append(
                    {
                        "id": f"{path}@{c['id']}",
                        "title": f"{c['id'][:7]} {_first_line(c.get('title'))}".strip(),
                        "subtitle": c.get("author_name", ""),
                        "modified": parse_datetime(c["committed_date"]),
                        "url": c["web_url"],
                    }
                )
            return [r for r in out if r]
        params = {"membership": "true", "simple": "true", "per_page": 20}
        params["order_by"] = "last_activity_at"
        if query:
            params["search"] = query
        resp = _get(account, f"{account.instance_url}/api/v4/projects?{urlencode(params)}")
        rows = [_project_row(d) for d in (resp.json() if resp is not None else [])]
        return [r for r in rows if r][:20]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("GitLab returned an unreadable answer") from None


def _project_row(d):
    active = d.get("last_activity_at")
    row = {
        "id": d["path_with_namespace"],
        "title": d["path_with_namespace"],
        "subtitle": (d.get("description") or "")[:120],
        "modified": parse_datetime(active) if active else None,
        "url": d["web_url"],
    }
    return row if _ID.fullmatch(row["id"]) else None


def apply_to_target(kind, meta):
    """D86: an analysis' empty code reference takes the project address and, for a commit link,
    the full commit hash. Written only into empty fields."""
    if kind != "analysis":
        return {}
    return {"code_repo_url": meta.get("repo_url", ""), "code_commit": meta.get("commit", "")}


class _GitLab(Provider):
    def parse_url(self, url, instance_host=""):
        """A commit address names the commit: the id is `group/project@<sha>`."""
        base = super().parse_url(url, instance_host)
        if base is None:
            return None
        sha = re.fullmatch(self.url_pattern, url.strip())["sha"]
        return f"{base}@{sha}" if sha else base


PROVIDER = _GitLab(
    name="gitlab",
    label="GitLab",
    auth_type=AuthType.API_KEY,
    category=Category.CODE,
    icon="gitlab",
    link_targets=frozenset({"project", "analysis", "result", "dataset", "manuscript"}),
    link_methods=("search", "paste_url"),
    connect_fields=(
        ConnectField(
            "instance_url",
            "GitLab address",
            "https://gitlab.com, or your institution's own GitLab server.",
        ),
        ConnectField(
            "api_key",
            "Personal access token",
            "GitLab > Preferences > Access tokens. Tick only read_api.",
        ),
    ),
    needs_instance_url=True,
    identity_url="/api/v4/user",
    parse_identity=_identity,
    sign=_sign,
    fetch_item=fetch_item,
    search_items=search_items,
    external_id_pattern=rf"^{_PATH}(?:@{_SHA})?$",
    url_pattern=rf"https://[A-Za-z0-9.-]+/(?P<id>{_PATH})(?:/-/commit/(?P<sha>{_SHA}))?/?",
    apply_to_target=apply_to_target,
)
