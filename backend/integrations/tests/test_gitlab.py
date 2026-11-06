"""GitLab (D105, D108): the provider contract on a self-hosted server, then commits, id and URL
rules, the instance rules, the analysis code reference, least scope and metadata-only requests."""

import re
from urllib.parse import urlsplit

import pytest

from integrations import http
from integrations.providers import gitlab
from integrations.tests.fake import response
from integrations.tests.provider_contract import CONTENT_PATHS, ProviderContract

SHA = "0123456789abcdef0123456789abcdef01234567"
SHA2 = "fedcba9876543210fedcba9876543210fedcba98"
HOST = "https://gitlab.example.edu"
API = f"{HOST}/api/v4"
PROJECT_API = f"{API}/projects/lab%2Fpipeline"
COMMIT_API = f"{PROJECT_API}/repository/commits/{SHA}"
SEARCH = f"{API}/projects?membership=true&simple=true&per_page=20&order_by=last_activity_at"


def project(active="2030-01-01T10:00:00Z", **over):
    return {
        "id": 5,
        "path_with_namespace": "lab/pipeline",
        "web_url": f"{HOST}/lab/pipeline",
        "default_branch": "main",
        "last_activity_at": active,
        "description": "Analysis code",
        **over,
    }


def commit(sha=SHA, **over):
    return {
        "id": sha,
        "title": "Fix the filter",
        "author_name": "Ada",
        "committed_date": "2030-02-01T09:00:00.000+00:00",
        "web_url": f"{HOST}/lab/pipeline/-/commit/{sha}",
        **over,
    }


class TestGitLab(ProviderContract):
    provider = gitlab.PROVIDER
    instance_url = f"{HOST}/"
    item_id = "lab/pipeline"
    item_url = f"{HOST}/lab/pipeline"
    title = "lab/pipeline"
    target = "analysis"
    search_query = "pipeline"
    replies = {
        "identity": [("GET", f"{API}/user", 200, {"id": 7, "username": "ada"})],
        "item": [("GET", PROJECT_API, 200, project())],
        "item_changed": [("GET", PROJECT_API, 200, project(active="2030-03-01T10:00:00Z"))],
        "item_gone": [("GET", PROJECT_API, 404, {"message": "404 Project Not Found"})],
        "search": [
            ("GET", f"{SEARCH}&search=pipeline", 200, [project()]),
            ("GET", f"{SEARCH}&search=x", 200, []),
        ],
    }

    def analysis(self, w):
        from provenance.models import Analysis

        self._w = w
        return Analysis.objects.for_lab(w.lab).get(pk=self.make_target())

    # -- ids and addresses

    @pytest.mark.parametrize(
        "good", ["lab/pipeline", "a/b/c", "g/sub.group/p_1-x", f"lab/pipeline@{SHA}"]
    )
    def test_good_ids(self, good):
        assert self.provider.valid_external_id(good)

    @pytest.mark.parametrize(
        "bad",
        [
            "pipeline",
            "lab/",
            "/pipeline",
            "lab//pipeline",
            "lab/..",
            "lab/./x",
            "../pipeline",
            "lab/-/pipeline",
            "lab/pipeline@abc1234",
            f"lab/pipeline@{SHA.upper()}",
            "lab/pipeline?x=1",
            "lab/pipe line",
            "lab/pipeline\n",
            "lab/pipeline%2F..",
        ],
    )
    def test_bad_ids(self, bad):
        assert not self.provider.valid_external_id(bad)

    def test_pasted_addresses_are_pinned_to_the_instance(self):
        parse = self.provider.parse_url
        assert parse(f"{HOST}/lab/pipeline", "gitlab.example.edu") == "lab/pipeline"
        assert parse(f"{HOST}/lab/sub/pipeline/", "gitlab.example.edu") == "lab/sub/pipeline"
        assert parse(f"{HOST}/lab/pipeline/-/commit/{SHA}", "gitlab.example.edu") == (
            f"lab/pipeline@{SHA}"
        )
        for bad in (
            "http://gitlab.example.edu/lab/pipeline",
            "https://evil.test/lab/pipeline",
            "https://user@gitlab.example.edu/lab/pipeline",
            "https://gitlab.example.edu:8443/lab/pipeline",
            f"{HOST}/lab/pipeline/-/tree/main",
            f"{HOST}/lab/pipeline/-/commit/abc1234",
            f"{HOST}/lab/pipeline/-/archive/main/x.zip",
            f"{HOST}/lab/pipeline?ref=main",
            f"{HOST}/lab",
        ):
            assert parse(bad, "gitlab.example.edu") is None, bad
        assert parse(f"{HOST}/lab/pipeline", "") is None  # no account, no instance host

    def test_commit_address_links_the_commit(self, w):
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        link = self.create_link(w, url=f"{HOST}/lab/pipeline/-/commit/{SHA}", external_id=None)
        assert link["external_id"] == f"lab/pipeline@{SHA}"
        assert link["title"] == "lab/pipeline@0123456 Fix the filter"

    # -- the instance

    def test_gitlab_com_is_a_valid_instance_and_hostile_ones_are_refused(self, w):
        self.connect(w)  # the harness' own server first
        w.transport.on("GET", "https://gitlab.com/api/v4/user", response(200, {"id": 9}))
        url = w.url("integrations/gitlab/connect/")
        ok = w.client.post(
            url, {"api_key": "k", "instance_url": "https://gitlab.com"}, "application/json"
        )
        assert ok.status_code in (200, 400)  # one self-hosted account at a time (D81)
        for bad in (
            "http://gitlab.com",
            "https://127.0.0.1",
            "https://user@gitlab.com",
            "https://gitlab.com:8443",
            "https://gitlab.com?x=1",
            "gitlab.com",
        ):
            resp = w.client.post(url, {"api_key": "k", "instance_url": bad}, "application/json")
            assert resp.status_code == 400, bad

    def test_an_address_on_another_host_is_not_linked(self, w):
        w.transport.on(
            "GET", PROJECT_API, response(200, project(web_url="https://evil.test/lab/pipeline"))
        )
        self.connect(w)
        resp = w.call(
            "POST",
            f"projects/{w.project.pk}/external-links/",
            {"provider": "gitlab", "external_id": "lab/pipeline"},
        )
        assert resp.status_code == 400 and "url" in resp.json()

    # -- fetching

    def test_fetch_project_and_commit_metadata(self, w):
        self.connect(w)
        account = self.account(w)
        w.transport.on("GET", PROJECT_API, response(200, project()))
        meta = gitlab.fetch_item(account, "lab/pipeline")
        assert meta["default_branch"] == "main" and meta["version"] == "2030-01-01T10:00:00Z"
        assert meta["commit"] == ""
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        meta = gitlab.fetch_item(account, f"lab/pipeline@{SHA}")
        assert meta["version"] == meta["commit"] == SHA and meta["modified_at"].month == 2
        assert meta["repo_url"] == f"{HOST}/lab/pipeline"

    def test_a_missing_commit_is_gone(self, w):
        self.connect(w)
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(404, {}))
        assert gitlab.fetch_item(self.account(w), f"lab/pipeline@{SHA}") is None

    def test_a_different_commit_back_is_gone_not_trusted(self, w):
        self.connect(w)
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit(sha=SHA2)))
        assert gitlab.fetch_item(self.account(w), f"lab/pipeline@{SHA}") is None

    @pytest.mark.parametrize("status", [403, 429, 500])
    def test_rate_limits_and_errors_are_not_gone(self, w, status):
        self.connect(w)
        w.transport.on("GET", PROJECT_API, response(status, {"message": "secret body"}))
        with pytest.raises(http.IntegrationError) as exc:
            gitlab.fetch_item(self.account(w), "lab/pipeline")
        assert "secret body" not in str(exc.value)

    @pytest.mark.parametrize("body", [{}, {"web_url": "x"}, [], "text", None])
    def test_unreadable_answers_are_integration_errors(self, w, body):
        self.connect(w)
        w.transport.on("GET", PROJECT_API, response(200, body))
        with pytest.raises(http.IntegrationError):
            gitlab.fetch_item(self.account(w), "lab/pipeline")

    def test_a_bad_id_never_reaches_the_network(self, w):
        self.connect(w)
        calls = len(w.transport.calls)
        for bad in ("lab/../x", "lab/p?x=1", "lab"):
            with pytest.raises(http.IntegrationError):
                gitlab.fetch_item(self.account(w), bad)
        assert len(w.transport.calls) == calls

    def test_the_path_is_quoted_into_one_segment(self, w):
        self.connect(w)
        w.transport.on("GET", f"{API}/projects/a%2Fb%2Fc", response(404, {}))
        assert gitlab.fetch_item(self.account(w), "a/b/c") is None

    # -- search

    def test_search_without_a_query_lists_recent_projects(self, w):
        self.connect(w)
        w.transport.on("GET", SEARCH, response(200, [project()]))
        rows = gitlab.search_items(self.account(w), "", "analysis")
        assert [r["id"] for r in rows] == ["lab/pipeline"]

    def test_search_names_a_project_then_lists_its_commits(self, w):
        self.connect(w)
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on(
            "GET",
            f"{PROJECT_API}/repository/commits?per_page=20",
            response(200, [commit(), commit(sha=SHA2)]),
        )
        rows = gitlab.search_items(self.account(w), "lab/pipeline", "analysis")
        assert [r["id"] for r in rows] == [
            "lab/pipeline",
            f"lab/pipeline@{SHA}",
            f"lab/pipeline@{SHA2}",
        ]
        assert rows[1]["title"] == "0123456 Fix the filter" and rows[1]["subtitle"] == "Ada"

    def test_search_drops_rows_with_hostile_names(self, w):
        self.connect(w)
        evil = project(path_with_namespace="lab/../../x")
        w.transport.on("GET", SEARCH, response(200, [evil]))
        assert gitlab.search_items(self.account(w), "", "analysis") == []

    # -- the analysis' code reference (D86)

    def test_link_fills_an_empty_code_reference(self, w):
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        link = self.create_link(w, external_id=f"lab/pipeline@{SHA}")
        analysis = type(self.analysis(w)).objects.for_lab(w.lab).get(pk=link["analysis"])
        assert analysis.code_repo_url == f"{HOST}/lab/pipeline" and analysis.code_commit == SHA
        assert link["version_note"] == "copied"

    def test_existing_code_reference_is_never_overwritten(self, w):
        from provenance.models import Analysis

        analysis = self.analysis(w)
        Analysis.objects.for_lab(w.lab).filter(pk=analysis.pk).update(
            code_repo_url="https://example.org/mine", code_commit="abc1234"
        )
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        link = self.create_link(w, external_id=f"lab/pipeline@{SHA}", analysis=str(analysis.pk))
        analysis.refresh_from_db()
        assert (analysis.code_repo_url, analysis.code_commit) == (
            "https://example.org/mine",
            "abc1234",
        )
        assert link["version_note"] == "kept"

    def test_a_commit_is_never_paired_with_another_repositorys_address(self, w):
        """D121: the record already names a repository; a commit is not added from another."""
        from provenance.models import Analysis

        analysis = self.analysis(w)
        Analysis.objects.for_lab(w.lab).filter(pk=analysis.pk).update(
            code_repo_url="https://example.org/repo-a"
        )
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        link = self.create_link(w, external_id=f"lab/pipeline@{SHA}", analysis=str(analysis.pk))
        analysis.refresh_from_db()
        assert (analysis.code_repo_url, analysis.code_commit) == ("https://example.org/repo-a", "")
        assert link["version_note"] == "kept"

    def test_a_repository_address_off_the_instance_host_is_not_stored(self, w, monkeypatch):
        """D121: `web_url` comes from the (user-chosen) server; it must be on its own host."""
        evil = [("GET", PROJECT_API, 200, project(web_url="https://evil.test/x"))]
        monkeypatch.setitem(self.replies, "item", evil)  # create_link re-registers "item"
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        link = self.create_link(w, external_id=f"lab/pipeline@{SHA}")
        analysis = type(self.analysis(w)).objects.for_lab(w.lab).get(pk=link["analysis"])
        assert (analysis.code_repo_url, analysis.code_commit) == ("", "")
        assert link["version_note"] == "none"

    def test_apply_to_target_only_for_analyses(self):
        meta = {"repo_url": f"{HOST}/lab/pipeline", "commit": SHA}
        assert gitlab.apply_to_target("analysis", meta) == {
            "code_repo_url": f"{HOST}/lab/pipeline",
            "code_commit": SHA,
        }
        for kind in ("dataset", "result", "manuscript", "decision", "document"):
            assert gitlab.apply_to_target(kind, meta) == {}

    # -- least privilege, metadata only

    def test_least_scope_is_one_read_api_token_and_no_oauth(self):
        p = self.provider
        assert [f.name for f in p.connect_fields] == ["instance_url", "api_key"]
        assert not (p.scopes or p.authorize_url or p.token_url or p.revoke_url or any(p.client()))
        assert p.needs_instance_url and not p.api_hosts
        assert "read_api" in p.connect_fields[1].help_text

    def test_only_reads_on_the_instance_host_and_no_content_urls(self, w):
        w.transport.on("GET", PROJECT_API, response(200, project()))
        w.transport.on("GET", COMMIT_API, response(200, commit()))
        w.transport.on(
            "GET", f"{PROJECT_API}/repository/commits?per_page=20", response(200, [commit()])
        )
        w.transport.on("GET", SEARCH, response(200, [project()]))
        self.create_link(w, external_id=f"lab/pipeline@{SHA}")
        gitlab.search_items(self.account(w), "lab/pipeline", "analysis")
        gitlab.search_items(self.account(w), "", "analysis")
        assert w.transport.calls
        for method, url, kwargs in w.transport.calls:
            assert method == "GET" and urlsplit(url).hostname == "gitlab.example.edu", url
            assert not any(re.search(p, url.lower()) for p in CONTENT_PATHS), url
            assert kwargs["headers"]["PRIVATE-TOKEN"].startswith("CANARY-api-key")
