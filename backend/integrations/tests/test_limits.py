"""D120: outbound calls are bounded in time and size. A real local server drips, hangs and floods;
the real session code (streaming, the deadline watchdog, the size cap) must give up in time and
close the connection. Only the host check and the HTTPS pin are bypassed (loopback, plain HTTP)."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from integrations import http, jobs, registry, services
from integrations.http import IntegrationError
from integrations.tests.fake import FAKE_PUBLIC, FakeTransport, response

DEADLINE = 1.0
SLACK = 3.0  # scheduling slack on a loaded box; the failures being caught take 8 s or never end


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        server = self.server
        server.hits.append(self.path)
        try:
            getattr(self, "route_" + self.path.strip("/").split("?")[0])()
        except (BrokenPipeError, ConnectionResetError, OSError):
            server.client_gone.set()
        self.close_connection = True

    def head(self, status=200, **headers):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k.replace("_", "-"), v)
        self.end_headers()

    def route_ok(self):
        body = b'{"ok": true}'
        self.head(Content_Length=str(len(body)), Content_Type="application/json")
        self.wfile.write(body)

    def route_drip(self):  # one byte every 0.2 s for 8 s: each read "succeeds", so no timeout
        self.head(Content_Type="application/json")  # no length: close-delimited
        for _ in range(40):
            self.wfile.write(b" ")
            self.wfile.flush()
            time.sleep(0.2)

    def route_silent(self):  # headers now, then nothing
        self.head(Content_Type="application/json")
        self.wfile.flush()
        time.sleep(8)

    def route_late(self):  # nothing for 8 s
        time.sleep(8)

    def route_declared(self):  # claims 100 MB and sends none of it
        self.head(Content_Length=str(100 * 1024 * 1024))
        self.wfile.flush()
        time.sleep(8)

    def route_flood(self):  # no length; sends until the client goes away
        self.head(Content_Type="application/octet-stream")
        block = b"x" * 65536
        for _ in range(4000):  # 256 MB at most
            self.wfile.write(block)

    def route_busy(self):  # 503 with a long Retry-After: backoff must not outlast the deadline
        self.head(503, Retry_After="30", Content_Length="0")


@pytest.fixture
def server(monkeypatch, settings):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    srv.hits, srv.client_gone = [], threading.Event()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    session = requests.Session()
    session.trust_env = False
    monkeypatch.setattr(http, "_session", session)
    monkeypatch.setattr(http, "_check_url", lambda *a, **k: None)  # loopback, plain HTTP
    settings.INTEGRATION_HTTP_DEADLINE = DEADLINE
    settings.INTEGRATION_HTTP_MAX_BYTES = 1000
    srv.url = lambda path: f"http://127.0.0.1:{srv.server_address[1]}/{path}"
    yield srv
    srv.shutdown()
    srv.server_close()


def timed(server, path, **kw):
    start = time.monotonic()
    try:
        http.send("GET", server.url(path), provider=FAKE_PUBLIC, **kw)
    except IntegrationError as exc:
        return time.monotonic() - start, exc
    return time.monotonic() - start, None


def test_a_normal_response_still_works(server):
    resp = http.send("GET", server.url("ok"), provider=FAKE_PUBLIC)
    assert resp.status_code == 200 and resp.json() == {"ok": True}


def test_drip_feed_is_cut_at_the_deadline(server):
    elapsed, exc = timed(server, "drip")
    assert exc is not None and "in time" in str(exc)
    assert elapsed < DEADLINE + SLACK  # without a total deadline this runs the full 8 s
    assert server.client_gone.wait(3)  # and the connection was closed, not left open


def test_a_stalled_body_is_cut_at_the_deadline(server):
    elapsed, exc = timed(server, "silent")
    assert exc is not None and elapsed < DEADLINE + SLACK


def test_a_server_that_never_answers_is_cut_at_the_deadline(server):
    elapsed, exc = timed(server, "late")
    assert exc is not None and elapsed < DEADLINE + SLACK


def test_a_declared_oversize_body_is_refused_before_reading(server):
    elapsed, exc = timed(server, "declared")
    assert exc is not None and "too large" in str(exc)
    assert elapsed < DEADLINE  # refused on the header alone, no waiting for bytes


def test_a_streamed_oversize_body_is_aborted_at_the_cap(server):
    elapsed, exc = timed(server, "flood")
    assert exc is not None and "too large" in str(exc)
    assert elapsed < DEADLINE + SLACK
    assert server.client_gone.wait(3)  # aborted: the sender is cut off long before 256 MB


def test_a_budget_sets_its_own_byte_cap(server):
    with http.budget(max_bytes=5), pytest.raises(http.ResponseTooLarge):  # VISION B4
        http.send("GET", server.url("ok"), provider=FAKE_PUBLIC)


def test_retries_and_backoff_never_outlast_the_deadline(server):
    start = time.monotonic()
    resp = http.send("GET", server.url("busy"), provider=FAKE_PUBLIC)
    assert resp.status_code == 503  # the last answer, handed back instead of sleeping 30 s
    assert time.monotonic() - start < DEADLINE + SLACK
    assert len(server.hits) == 1


def test_an_endpoint_budget_caps_the_sum_of_its_calls(server):
    start = time.monotonic()
    with http.budget(1.5):
        for _ in range(8):  # each call alone is within its 1 s, together they are not
            with pytest.raises(IntegrationError):
                http.send("GET", server.url("drip"), provider=FAKE_PUBLIC)
    assert time.monotonic() - start < 1.5 + SLACK
    assert len(server.hits) <= 2


def test_background_jobs_get_their_own_per_request_deadline(server, settings):
    settings.INTEGRATION_JOB_HTTP_DEADLINE = 0.5
    start = time.monotonic()
    with http.budget(30, per_request=settings.INTEGRATION_JOB_HTTP_DEADLINE):
        with pytest.raises(IntegrationError):
            http.send("GET", server.url("drip"), provider=FAKE_PUBLIC)
    assert time.monotonic() - start < 0.5 + SLACK


def test_service_entry_points_carry_an_endpoint_budget():
    """Every interactive service function is wrapped by `http.interactive`."""
    for name in ("complete_connect", "connect_with_key", "create_link", "search_items"):
        assert getattr(getattr(services, name), "endpoint_budget", False), name


# ---- the daily job: one bad link or lab can't stall the rest


def test_the_daily_job_is_one_time_limited_task_per_lab():
    for task in (jobs.check_lab_links_task, jobs.check_links, jobs.check_links_by_lab):
        assert 0 < task.soft_time_limit < task.time_limit
    assert jobs.LAB_SOFT_LIMIT > 0
    from config.settings import CELERY_BEAT_SCHEDULE

    assert CELERY_BEAT_SCHEDULE["integrations-check-links"]["task"] == (
        "integrations.jobs.check_links_by_lab"
    )


def test_fan_out_queues_one_task_per_lab(make_lab, monkeypatch):
    labs = [make_lab("A"), make_lab("B"), make_lab("C")]
    queued = []
    monkeypatch.setattr(jobs.check_lab_links_task, "delay", lambda lab_id: queued.append(lab_id))
    assert jobs.check_links_by_lab() == len(queued) >= 3
    assert {str(lab.pk) for lab in labs} <= set(queued)


@pytest.fixture
def two_labs(make_lab, make_user, make_project, join, monkeypatch):
    """Two labs, each with public-provider links that need no account."""
    from integrations.models import ExternalLink

    monkeypatch.setitem(registry.PROVIDERS, FAKE_PUBLIC.name, FAKE_PUBLIC)
    out = []
    for name in ("Lab A", "Lab B"):
        lab, user = make_lab(name), make_user()
        join(user, lab, "pi")
        project = make_project(lab)
        links = [
            ExternalLink.objects.create(
                lab=lab,
                project=project,
                provider=FAKE_PUBLIC.name,
                external_id=str(n),
                url=f"https://records.fake.test/r/{n}",
                title=f"R{n}",
                linked_by=user,
            )
            for n in (1, 2)
        ]
        out.append((lab, links))
    return out


@pytest.fixture
def fake_net(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(http, "_session", fake)
    monkeypatch.setattr(http, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(services.time, "sleep", lambda s: None)
    return fake


def item(name):
    return {
        "name": name,
        "url": "https://records.fake.test/r/1",
        "modifiedTime": "2030-01-01T00:00:00Z",
    }


def test_one_failing_link_does_not_stop_the_others(two_labs, fake_net):
    (lab_a, _), (lab_b, _) = two_labs
    base = "https://public.fake.test/records"
    fake_net.on("GET", f"{base}/1", IntegrationError("down"), response(200, item("ok")))
    fake_net.on("GET", f"{base}/2", response(200, item("ok")))
    # the first read of /1 (lab A) fails, every other read succeeds
    assert services.check_lab_links(lab_a)["failed"] == 1
    assert services.check_lab_links(lab_b) == {"checked": 2, "skipped": 0, "failed": 0}


def test_one_failing_lab_does_not_stop_the_others(two_labs, fake_net, monkeypatch):
    (lab_a, _), (lab_b, _) = two_labs
    real = services.check_lab_links

    def flaky(lab):
        if lab.pk == lab_a.pk:
            raise RuntimeError("boom")
        return real(lab)

    base = "https://public.fake.test/records"
    for n in (1, 2):
        fake_net.on("GET", f"{base}/{n}", response(200, item("ok")))
    monkeypatch.setattr(services, "check_lab_links", flaky)
    total = services.check_all_links()
    assert total["failed"] >= 1 and total["checked"] >= 2


def test_a_lab_stops_at_its_time_budget(two_labs, fake_net, settings):
    (lab_a, _), _ = two_labs
    settings.INTEGRATION_JOB_LAB_BUDGET = -1  # already spent
    result = services.check_lab_links(lab_a)
    assert result["checked"] == 0 and result["failed"] == 1  # reported; tomorrow's run resumes


def test_each_link_check_runs_under_its_own_deadline(two_labs, fake_net, settings):
    (lab_a, _), _ = two_labs
    settings.INTEGRATION_JOB_LINK_BUDGET = 7
    settings.INTEGRATION_JOB_HTTP_DEADLINE = 3
    seen = []

    def spy(kwargs):
        limits = http._current()
        seen.append((limits.per_request, limits.deadline - time.monotonic()))
        return response(200, item("ok"))

    for n in (1, 2):
        fake_net.on("GET", f"https://public.fake.test/records/{n}", spy)
    services.check_lab_links(lab_a)
    assert len(seen) == 2
    assert all(per == 3 and 0 < left <= 7 for per, left in seen)
