"""GitHub (D105 to D107): the provider contract on a repository, then commits, id and URL rules,
the analysis code reference, least scope and metadata-only requests."""

import re
from urllib.parse import urlsplit

import pytest

from integrations import http
from integrations.providers import github
from integrations.tests.fake import response
from integrations.tests.provider_contract import CONTENT_PATHS, ProviderContract

SHA = "0123456789abcdef0123456789abcdef01234567"
SHA2 = "fedcba9876543210fedcba9876543210fedcba98"
API = "https://api.github.com"
REPO_API = f"{API}/repos/octo/lab-pipeline"
COMMIT_API = f"{REPO_API}/commits?sha={SHA}&per_page=1"


def repo(pushed="2030-01-01T10:00:00Z", **over):
    return {
        "id": 1,
        "full_name": "octo/lab-pipeline",
        "html_url": "https://github.com/octo/lab-pipeline",
        "default_branch": "main",
        "pushed_at": pushed,
        "description": "Analysis code",
        **over,
    }


def commit(sha=SHA, message="Fix the filter\n\nLong body", **over):
    return {
        "sha": sha,
        "html_url": f"https://github.com/octo/lab-pipeline/commit/{sha}",
        "commit": {
            "message": message,
            "author": {"name": "Ada"},
            "committer": {"date": "2030-02-01T09:00:00Z"},
        },
        **over,
    }


class TestGitHub(ProviderContract):
    provider = github.PROVIDER
    item_id = "octo/lab-pipeline"
    item_url = "https://github.com/octo/lab-pipeline"
    title = "octo/lab-pipeline"
    target = "analysis"
    search_query = "pipeline"
    replies = {
        "identity": [("GET", f"{API}/user", 200, {"id": 4242, "login": "octo"})],
        "item": [("GET", REPO_API, 200, repo())],
        "item_changed": [("GET", REPO_API, 200, repo(pushed="2030-03-01T10:00:00Z"))],
        "item_gone": [("GET", REPO_API, 404, {"message": "Not Found"})],
        "search": [
            (
                "GET",
                f"{API}/user/repos?per_page=100&sort=pushed",
                200,
                [repo(), repo(full_name="octo/other", html_url="https://github.com/octo/other")],
            )
        ],
    }

    def analysis(self, w):
        from provenance.models import Analysis

        self._w = w
        return Analysis.objects.for_lab(w.lab).get(pk=self.make_target())

    # -- ids and addresses

    @pytest.mark.parametrize(
        "good",
        ["octo/lab-pipeline", "a/b", "octo/a.b_c-d", f"octo/lab-pipeline@{SHA}", "o-1/.github"],
    )
    def test_good_ids(self, good):
        assert self.provider.valid_external_id(good)

    @pytest.mark.parametrize(
        "bad",
        [
            "octo",
            "octo/",
            "/repo",
            "octo/lab/pipeline",
            "octo/..",
            "octo/.",
            "-octo/repo",
            "octo/repo@abc1234",  # short hash: not an exact commit
            f"octo/repo@{SHA.upper()}",
            f"octo/repo@{SHA}x",
            "octo/repo?x=1",
            "octo/repo#frag",
            "octo/rep o",
            "octo/repo\n",
            "../repo",
            "octo/repo%2F..",
            "o" * 40 + "/repo",
        ],
    )
    def test_bad_ids(self, bad):
        assert not self.provider.valid_external_id(bad)

    def test_pasted_addresses(self):
        parse = self.provider.parse_url
        assert parse("https://github.com/octo/lab-pipeline") == "octo/lab-pipeline"
        assert parse("https://github.com/octo/lab-pipeline/") == "octo/lab-pipeline"
        assert parse(f"https://github.com/octo/lab-pipeline/commit/{SHA}") == (
            f"octo/lab-pipeline@{SHA}"
        )
        for bad in (
            "http://github.com/octo/lab-pipeline",
            "https://www.github.com/octo/lab-pipeline",
            "https://github.com.evil.test/octo/lab-pipeline",
            "https://evil.test/octo/lab-pipeline",
            "https://user@github.com/octo/lab-pipeline",
            "https://github.com:8443/octo/lab-pipeline",
            "https://github.com/octo/lab-pipeline/tree/main",
            "https://github.com/octo/lab-pipeline/commit/abc1234",
            "https://github.com/octo/lab-pipeline?tab=readme",
            "https://github.com/octo/lab-pipeline/archive/main.zip",
            "https://github.com/octo",
            "https://github.com/octo/..",
            "https://raw.githubusercontent.com/octo/lab-pipeline/main/x.py",
        ):
            assert parse(bad) is None, bad

    def test_commit_address_links_the_commit(self, w):
        w.transport.on("GET", COMMIT_API, response(200, [commit()]))
        link = self.create_link(
            w, url=f"https://github.com/octo/lab-pipeline/commit/{SHA}", external_id=None
        )
        assert link["external_id"] == f"octo/lab-pipeline@{SHA}"
        assert link["title"] == "octo/lab-pipeline@0123456 Fix the filter"
        assert link["url"].endswith(f"/commit/{SHA}")

    # -- fetching

    def test_fetch_repo_and_commit_metadata(self, w):
        self.connect(w)
        account = self.account(w)
        self.reply(w, "item")
        meta = github.fetch_item(account, "octo/lab-pipeline")
        assert meta["default_branch"] == "main" and meta["version"] == "2030-01-01T10:00:00Z"
        assert meta["modified_at"].year == 2030 and meta["commit"] == ""
        w.transport.on("GET", COMMIT_API, response(200, [commit()]))
        meta = github.fetch_item(account, f"octo/lab-pipeline@{SHA}")
        assert meta["version"] == meta["commit"] == SHA
        assert meta["modified_at"].month == 2
        assert meta["repo_url"] == "https://github.com/octo/lab-pipeline"

    @pytest.mark.parametrize("status", [404, 409, 410, 422, 451])
    def test_a_missing_commit_is_gone(self, w, status):
        self.connect(w)
        w.transport.on("GET", COMMIT_API, response(status, {"message": "x"}))
        assert github.fetch_item(self.account(w), f"octo/lab-pipeline@{SHA}") is None

    def test_a_different_commit_back_is_gone_not_trusted(self, w):
        self.connect(w)
        w.transport.on("GET", COMMIT_API, response(200, [commit(sha=SHA2)]))
        assert github.fetch_item(self.account(w), f"octo/lab-pipeline@{SHA}") is None

    @pytest.mark.parametrize("status", [403, 429, 500, 502])
    def test_rate_limits_and_errors_are_not_gone(self, w, status):
        self.connect(w)
        w.transport.on("GET", REPO_API, response(status, {"message": "secret body"}))
        with pytest.raises(http.IntegrationError) as exc:
            github.fetch_item(self.account(w), "octo/lab-pipeline")
        assert "secret body" not in str(exc.value)

    @pytest.mark.parametrize("body", [{}, {"full_name": "x"}, [], "text", None])
    def test_unreadable_answers_are_integration_errors(self, w, body):
        self.connect(w)
        w.transport.on("GET", REPO_API, response(200, body))
        with pytest.raises(http.IntegrationError):
            github.fetch_item(self.account(w), "octo/lab-pipeline")

    def test_a_bad_id_never_reaches_the_network(self, w):
        self.connect(w)
        calls = len(w.transport.calls)
        for bad in ("octo/../x", "octo/repo?x=1", "octo/a/b", "octo"):
            with pytest.raises(http.IntegrationError):
                github.fetch_item(self.account(w), bad)
        assert len(w.transport.calls) == calls

    # -- search

    def test_search_filters_the_users_repos_by_name(self, w):
        self.connect(w)
        self.reply(w, "search")
        names = [r["id"] for r in github.search_items(self.account(w), "other", "analysis")]
        assert names == ["octo/other"]
        assert len(github.search_items(self.account(w), "", "analysis")) == 2

    def test_search_names_a_repo_then_lists_its_commits(self, w):
        self.connect(w)
        w.transport.on("GET", REPO_API, response(200, repo()))
        w.transport.on(
            "GET", f"{REPO_API}/commits?per_page=20", response(200, [commit(), commit(sha=SHA2)])
        )
        rows = github.search_items(self.account(w), "octo/lab-pipeline", "analysis")
        assert [r["id"] for r in rows] == [
            "octo/lab-pipeline",
            f"octo/lab-pipeline@{SHA}",
            f"octo/lab-pipeline@{SHA2}",
        ]
        assert rows[1]["title"] == "0123456 Fix the filter" and rows[1]["subtitle"] == "Ada"
        assert all(self.provider.valid_external_id(r["id"]) for r in rows)

    def test_search_drops_rows_with_hostile_names(self, w):
        self.connect(w)
        evil = repo(full_name="octo/../../etc", html_url="https://evil.test/x")
        w.transport.on("GET", f"{API}/user/repos?per_page=100&sort=pushed", response(200, [evil]))
        assert github.search_items(self.account(w), "", "analysis") == []

    def test_search_of_an_unknown_repo_is_empty(self, w):
        self.connect(w)
        w.transport.on("GET", f"{API}/repos/octo/nope", response(404, {}))
        assert github.search_items(self.account(w), "octo/nope", "analysis") == []

    # -- the analysis' code reference (D86)

    def test_link_fills_an_empty_code_reference(self, w):
        w.transport.on("GET", COMMIT_API, response(200, [commit()]))
        link = self.create_link(w, external_id=f"octo/lab-pipeline@{SHA}")
        analysis = type(self.analysis(w)).objects.for_lab(w.lab).get(pk=link["analysis"])
        assert analysis.code_repo_url == "https://github.com/octo/lab-pipeline"
        assert analysis.code_commit == SHA
        assert link["version_note"] == "copied"

    def test_apply_to_target_only_for_analyses_and_only_what_it_has(self):
        meta = {"repo_url": "https://github.com/o/r", "commit": ""}
        assert github.apply_to_target("analysis", meta) == {
            "code_repo_url": "https://github.com/o/r",
            "code_commit": "",
        }
        for kind in ("dataset", "result", "manuscript", "decision", "document"):
            assert github.apply_to_target(kind, meta) == {}

    def test_existing_code_reference_is_never_overwritten(self, w):
        from provenance.models import Analysis

        analysis = self.analysis(w)
        Analysis.objects.for_lab(w.lab).filter(pk=analysis.pk).update(
            code_repo_url="https://example.org/mine", code_commit="abc1234"
        )
        w.transport.on("GET", COMMIT_API, response(200, [commit()]))
        link = self.create_link(
            w, external_id=f"octo/lab-pipeline@{SHA}", analysis=str(analysis.pk)
        )
        analysis.refresh_from_db()
        assert (analysis.code_repo_url, analysis.code_commit) == (
            "https://example.org/mine",
            "abc1234",
        )
        assert link["version_note"] == "kept"

    def test_a_repo_link_fills_only_the_address(self, w):
        link = self.create_link(w)
        analysis = type(self.analysis(w)).objects.for_lab(w.lab).get(pk=link["analysis"])
        assert analysis.code_repo_url == "https://github.com/octo/lab-pipeline"
        assert analysis.code_commit == ""

    # -- least privilege, metadata only

    def test_least_scope_is_one_read_only_token_and_no_oauth(self):
        p = self.provider
        assert [f.name for f in p.connect_fields] == ["api_key"]
        assert not (p.scopes or p.authorize_url or p.token_url or p.revoke_url or any(p.client()))
        assert not p.needs_instance_url and p.api_hosts == {"api.github.com"}
        text = p.connect_fields[0].help_text.lower()
        assert "fine-grained" in text and "read-only" in text

    def test_only_reads_on_the_api_host_and_no_content_urls(self, w):
        w.transport.on("GET", COMMIT_API, response(200, [commit()]))
        w.transport.on("GET", f"{REPO_API}/commits?per_page=20", response(200, [commit()]))
        w.transport.on("GET", REPO_API, response(200, repo()))
        self.create_link(w, external_id=f"octo/lab-pipeline@{SHA}")
        self.reply(w, "search")
        github.search_items(self.account(w), "octo/lab-pipeline", "analysis")
        github.search_items(self.account(w), "", "analysis")
        assert w.transport.calls
        for method, url, kwargs in w.transport.calls:
            parts = urlsplit(url)
            assert method == "GET" and parts.hostname == "api.github.com", url
            assert not any(re.search(p, url.lower()) for p in CONTENT_PATHS), url
            headers = kwargs["headers"]
            assert headers["Authorization"].startswith("Bearer CANARY-api-key")
            assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_no_revoke_call_exists_for_a_token(self, w):
        self.connect(w)
        assert self.provider.revoke_url == ""
