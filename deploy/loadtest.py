"""Live load test: N fake people from the full lab use the site at once, the way the frontend does.

Each person logs in, then for DURATION seconds:
- polls chat unread (10 s) and notifications (20 s), as every page does;
- every 15-40 s opens a "page" (a burst of the GETs that page makes);
- on a chat page, polls the messages every 4 s for 60 s and sometimes posts a message;
- sometimes updates a task.
Usage: python deploy/loadtest.py BASE_URL PASSWORD_FILE USERS DURATION_S  (needs `pip install requests`)
The password is read from a file and never printed."""

import random
import statistics
import sys
import threading
import time
from collections import defaultdict

import requests

BASE, PW_FILE, N, DURATION = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
PASSWORD = open(PW_FILE).read().strip()
KEYS = ["pi", "manager", "coordinator", "priya", "tomas", "hana", "eli", "aisha", "noah", "sofia",
        "liam", "grace", "mateo", "zoe", "ravi", "ella", "ben", "ingrid", "owen", "kai"]

lock = threading.Lock()
timings = defaultdict(list)  # endpoint label -> [ms]
errors = defaultdict(int)  # (label, status) -> count
total = [0]

LAB_PAGES = {
    "home": ["dashboard/", "my-tasks/", "start-here/", "getting-started/", "projects/"],
    "team": ["members/", "team-tasks/", "contributions/"],
    "calendar": ["calendar/?from=2026-11-01&to=2026-12-31", "calendar/events/", "calendar/meetings/"],
    "inventory": ["inventory/", "inventory/orders/"],
    "training": ["training/my/", "training/compliance/", "training/requirements/"],
    "ethics": ["ethics-approvals/"],
    "papers": ["papers/"],
    "notebook": ["notebook/"],
    "funding": ["funding/"],
    "lab_docs": ["lab-documents/", "lab-folders/"],
    "integrations": ["integrations/accounts/", "integrations/providers/"],
    "search": ["search/?q=FAKE", "search/?q=sleep"],
}
PROJECT_PAGES = {
    "overview": ["", "members/", "deadlines/", "workflow-progress/"],
    "tasks": ["tasks/"],
    "docs": ["documents/", "folders/", "attachments/"],
    "data": ["datasets/", "analyses/", "results/", "decisions/", "manuscripts/", "lineage/"],
    "files": ["attachments/", "external-links/"],
    "participants": ["participants/", "participant-flow/"],
}


def label(path):
    parts = [p for p in path.split("?")[0].split("/") if p]
    return "/".join("{id}" if len(p) >= 32 or p.isdigit() else p for p in parts)


class Person:
    def __init__(self, key):
        self.key = key
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "labbench-loadtest"

    def call(self, method, path, **kw):
        url = BASE + path
        if method != "GET":
            kw.setdefault("headers", {})["X-CSRFToken"] = self.s.cookies.get("csrftoken", "")
            kw["headers"]["Referer"] = BASE + "/"
        t = time.perf_counter()
        try:
            r = self.s.request(method, url, timeout=30, **kw)
            status = r.status_code
        except requests.RequestException:
            r, status = None, "exc"
        ms = (time.perf_counter() - t) * 1000
        name = f"{method} {label(path)}"
        with lock:
            total[0] += 1
            timings[name].append(ms)
            if status == "exc" or status >= 400:
                errors[(name, status)] += 1
        return r

    def login(self):
        self.call("GET", "/_allauth/browser/v1/auth/session")
        r = self.call("POST", "/_allauth/browser/v1/auth/login",
                      json={"email": f"full-{self.key}@example.test", "password": PASSWORD})
        if r is None or r.status_code != 200:
            raise SystemExit(f"login failed for {self.key}: {r and r.status_code}")
        labs = self.call("GET", "/api/labs/").json()
        labs = labs.get("results", labs) if isinstance(labs, dict) else labs
        self.lab = next(l["id"] for l in labs if l["name"].startswith("Northfield"))
        projects = self.call("GET", f"/api/labs/{self.lab}/projects/").json()
        projects = projects.get("results", projects) if isinstance(projects, dict) else projects
        self.projects = [p["id"] for p in projects]

    def lab_get(self, sub):
        return self.call("GET", f"/api/labs/{self.lab}/{sub}")

    def run(self, until):
        rnd = random.Random(self.key)
        next_unread = next_notif = next_page = time.time()
        chat_until, chat_project = 0, None
        while time.time() < until:
            now = time.time()
            if now >= next_unread:
                self.lab_get("chat/unread/")
                next_unread = now + 10
            if now >= next_notif:
                self.lab_get("notifications/")
                next_notif = now + 20
            if now < chat_until:
                base = f"projects/{chat_project}/messages/" if chat_project else "chat/messages/"
                self.lab_get(base)
                if rnd.random() < 0.04 and self.key not in ("ingrid", "owen", "kai"):
                    self.call("POST", f"/api/labs/{self.lab}/{base}",
                              json={"body": f"Load test message from {self.key} (FAKE)"})
            elif now >= next_page:
                self.open_page(rnd)
                next_page = now + rnd.uniform(15, 40)
                if rnd.random() < 0.2:
                    chat_until = now + 60
                    chat_project = rnd.choice(self.projects + [None]) if self.projects else None
            time.sleep(4 if now < chat_until else 1)

    def open_page(self, rnd):
        if self.projects and rnd.random() < 0.55:
            pid = rnd.choice(self.projects)
            page = rnd.choice(list(PROJECT_PAGES))
            for sub in PROJECT_PAGES[page]:
                r = self.lab_get(f"projects/{pid}/{sub}")
                if page == "tasks" and r is not None and r.status_code == 200 and rnd.random() < 0.15:
                    tasks = r.json()
                    tasks = tasks.get("results", tasks) if isinstance(tasks, dict) else tasks
                    if tasks:
                        t = rnd.choice(tasks)
                        self.call("PATCH", f"/api/labs/{self.lab}/tasks/{t['id']}/",
                                  json={"title": t["title"]})
        else:
            for sub in LAB_PAGES[rnd.choice(list(LAB_PAGES))]:
                self.lab_get(sub)


def main():
    people = [Person(k) for k in KEYS[:N]]
    for p in people:
        p.login()
    print(f"{len(people)} people logged in; running {DURATION}s against {BASE}")
    until = time.time() + DURATION
    threads = [threading.Thread(target=p.run, args=(until,)) for p in people]
    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start
    allms = sorted(ms for v in timings.values() for ms in v)
    pct = lambda xs, q: xs[min(len(xs) - 1, int(q * len(xs)))]  # noqa: E731
    print(f"requests {total[0]} in {elapsed:.0f}s = {total[0] / elapsed:.1f} req/s")
    print(f"all: p50 {pct(allms, .5):.0f} ms  p95 {pct(allms, .95):.0f} ms  max {allms[-1]:.0f} ms")
    print(f"errors: {sum(errors.values())}")
    for (name, status), n in sorted(errors.items(), key=lambda x: -x[1])[:20]:
        print(f"  {n:5} x {status} {name}")
    print("slowest endpoints by p95 (n, p50, p95, max ms):")
    rows = [(pct(sorted(v), .95), name, len(v), statistics.median(v), max(v))
            for name, v in timings.items()]
    for p95, name, n, p50, mx in sorted(rows, reverse=True)[:20]:
        print(f"  {p95:7.0f} {p50:7.0f} {mx:7.0f}  n={n:4}  {name}")


if __name__ == "__main__":
    main()
