"""The labbenchos analysis runner (VISION C2 and D2). It runs on its own server, apart from the
app, and only the app server may reach it (docs/DEPLOY.md, "Analysis runner").

POST /run takes one job as JSON, signed by the app with HMAC-SHA256 over the raw body in the
`X-Runner-Signature` header (hex), using RUNNER_SECRET:

    {"ts": <unix seconds>, "job": <random id>, "language": "python" | "r" | "octave",
     "code": <text>, "files": [{"name": <file name>, "data": <base64>}]}

A job older (or newer) than five minutes, or one already seen, is refused. Each job runs in a new
container: gVisor (RUNNER_RUNTIME, default runsc), no network, a read-only image, a size-limited
tmpfs as the only writable place, memory, CPU and process limits, no capabilities, no new
privileges, user nobody, killed at the time limit and removed afterwards. The job goes in as a tar
on the container's stdin (the code as .job/main.<ext>, the input files next to it in the working
directory); what comes back is a tar on its stdout with the printed output and the files the code
wrote to out/. Only regular files from out/ come back, by base name, within count and size caps.

The answer is JSON signed the same way: {"job", "exit_code", "timed_out", "stdout", "stderr",
"outputs": [{"name", "data"}], "skipped_outputs"}, or {"error": <message>} with a 4xx or 503.
The runner never fetches anything: images are built on this server and never pulled.
"""

import base64
import binascii
import hashlib
import hmac
import io
import json
import logging
import os
import posixpath
import subprocess
import tarfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("runner")


def _env_int(name, default):
    return int(os.environ.get(name, default))


SECRET = os.environ.get("RUNNER_SECRET", "").encode()
RUNTIME = os.environ.get("RUNNER_RUNTIME", "runsc")
TIMEOUT = _env_int("RUNNER_TIMEOUT", 120)  # seconds of wall clock per job
MEMORY = os.environ.get("RUNNER_MEMORY", "2g")
CPUS = os.environ.get("RUNNER_CPUS", "1")
PIDS = _env_int("RUNNER_PIDS", 256)
WORK_SIZE = os.environ.get("RUNNER_WORK_SIZE", "256m")  # also caps what can come back
MAX_JOBS = _env_int("RUNNER_MAX_JOBS", 2)

MAX_SKEW = 300  # seconds
MAX_FILES = 20
MAX_INPUT_BYTES = 50 * 2**20  # all input files together
MAX_CODE = 100_000  # characters
MAX_BODY = MAX_INPUT_BYTES * 4 // 3 + MAX_CODE * 4 + 2**20
MAX_OUTPUTS = 20
MAX_OUTPUT_BYTES = 20 * 2**20  # one output file
MAX_OUTPUTS_TOTAL = 50 * 2**20
MAX_LOG = 20_000  # characters of stdout and of stderr

# language -> (image, command run in /work). Images are built here (docs/DEPLOY.md), never pulled.
LANGUAGES = {
    "python": ("labbench-runner-python", ["python3", "/work/.job/main.py"]),
    "r": ("labbench-runner-r", ["Rscript", "/work/.job/main.R"]),
    "octave": (
        "labbench-runner-octave",
        [
            "octave-cli",
            "--norc",
            "--quiet",
            "--eval",
            "warning('off', 'Octave:gnuplot-graphics'); warning('off', 'print:nogs'); "
            "graphics_toolkit('gnuplot'); source('/work/.job/main.m');",
        ],
    ),
}
EXT = {"python": "py", "r": "R", "octave": "m"}

_slots = threading.BoundedSemaphore(MAX_JOBS)
_seen: dict[str, float] = {}  # signature -> when it may be forgotten (replay guard)
_seen_lock = threading.Lock()


class Refused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def sign(body: bytes) -> str:
    return hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def safe_name(name):
    """The base name of `name` if it is a plain file name we accept, else None. Hidden names
    (and so `.job`) and `out` are taken by the runner itself."""
    name = posixpath.basename(str(name).replace("\\", "/"))
    if not name or name.startswith(".") or name == "out" or len(name) > 200:
        return None
    return name if name.isprintable() else None


def check(body: bytes, signature: str, now: float) -> dict:
    """The job in `body` if its signature, age and contents are acceptable, else Refused."""
    if not SECRET or not hmac.compare_digest(sign(body).encode(), signature.encode("latin-1")):
        raise Refused(401, "Bad signature.")
    try:
        job = json.loads(body)
    except ValueError:
        raise Refused(400, "The job is not valid JSON.") from None
    ts = job.get("ts") if isinstance(job, dict) else None
    if not isinstance(ts, (int, float)) or isinstance(ts, bool) or abs(now - ts) > MAX_SKEW:
        raise Refused(401, "The job is too old.")
    with _seen_lock:
        for sig, until in list(_seen.items()):
            if until < now:
                del _seen[sig]
        if signature in _seen:
            raise Refused(409, "This job was already sent.")
        _seen[signature] = now + 2 * MAX_SKEW
    if job.get("language") not in LANGUAGES:
        raise Refused(400, "language must be python, r or octave.")
    code = job.get("code")
    if not isinstance(code, str) or not code.strip() or len(code) > MAX_CODE:
        raise Refused(400, f"code must be 1 to {MAX_CODE} characters.")
    files = job.get("files") or []
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise Refused(400, f"At most {MAX_FILES} input files.")
    decoded, total = [], 0
    for f in files:
        name = f.get("name") if isinstance(f, dict) else None
        if safe_name(name) != name:
            raise Refused(400, f"Rename the file {str(name)[:100]!r}: it is not a plain file name.")
        if name in (n for n, _ in decoded):
            raise Refused(400, f"Two input files are named {name!r}. Rename one of them.")
        try:
            data = base64.b64decode(f.get("data") or "", validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise Refused(400, f"The data of {name!r} is not base64.") from None
        total += len(data)
        if total > MAX_INPUT_BYTES:
            raise Refused(400, f"The input files are too large ({MAX_INPUT_BYTES // 2**20} MB).")
        decoded.append((name, data))
    return {
        "job": str(job.get("job", ""))[:64],
        "language": job["language"],
        "code": code,
        "files": decoded,
    }


def docker_args(name, language):
    image, command = LANGUAGES[language]
    tmpfs = "rw,noexec,nosuid,nodev,mode=1777,size="
    return [
        "docker", "run", "--rm", "-i", f"--name={name}", "--pull=never",
        f"--runtime={RUNTIME}",
        "--network=none",
        "--read-only",
        f"--tmpfs=/work:{tmpfs}{WORK_SIZE}",
        f"--tmpfs=/tmp:{tmpfs}64m",
        "--workdir=/work",
        "--user=65534:65534",
        f"--memory={MEMORY}", f"--memory-swap={MEMORY}",
        f"--cpus={CPUS}",
        f"--pids-limit={PIDS}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--env=HOME=/work",
        image, "run-job", *command,
    ]  # fmt: skip


def job_tar(language, code, files) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in [(f".job/main.{EXT[language]}", code.encode()), *files]:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _log_text(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    if len(text) <= MAX_LOG:
        return text
    return text[:MAX_LOG] + f"\n[cut: {len(text) - MAX_LOG} more characters]"


def read_back(data: bytes) -> dict:
    """What the container sent back: printed output, exit code and the files from out/."""
    got = {"exit_code": None, "stdout": "", "stderr": "", "outputs": [], "skipped_outputs": 0}
    names, total = set(), 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        for m in tar:
            if not m.isfile():  # links, folders and devices never come back
                continue
            path = posixpath.normpath(m.name.removeprefix("./"))
            if path in (".stdout", ".stderr"):
                got[path[1:]] = _log_text(tar.extractfile(m).read())
            elif path == ".exit":
                try:
                    got["exit_code"] = int(tar.extractfile(m).read(16))
                except ValueError:
                    pass
            elif path.startswith("out/"):
                name = safe_name(path)
                if (
                    name is None
                    or name in names
                    or len(got["outputs"]) >= MAX_OUTPUTS
                    or m.size > MAX_OUTPUT_BYTES
                    or total + m.size > MAX_OUTPUTS_TOTAL
                ):
                    got["skipped_outputs"] += 1
                    continue
                names.add(name)
                total += m.size
                body = tar.extractfile(m).read()
                got["outputs"].append({"name": name, "data": base64.b64encode(body).decode()})
    return got


def run_job(job) -> dict:
    name = f"job-{uuid.uuid4().hex}"
    stdin = job_tar(job["language"], job["code"], job["files"])
    try:
        proc = subprocess.run(
            docker_args(name, job["language"]), input=stdin, capture_output=True, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {
            "job": job["job"],
            "exit_code": None,
            "timed_out": True,
            "stdout": "",
            "stderr": f"The run was stopped after {TIMEOUT} seconds.",
            "outputs": [],
            "skipped_outputs": 0,
        }
    finally:  # kills it if it is still running (time limit), and removes it if --rm did not
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
    try:
        got = read_back(proc.stdout)
    except tarfile.TarError:
        got = None
    if got is None or got["exit_code"] is None:  # no tar: out of memory, or docker failed
        log.warning("job %s: docker exit %s: %s", name, proc.returncode, proc.stderr[-500:])
        oom = proc.returncode == 137
        return {
            "job": job["job"],
            "exit_code": proc.returncode,
            "timed_out": False,
            "stdout": "",
            "stderr": "The run ran out of memory."
            if oom
            else f"The run failed to finish. It may have filled its {WORK_SIZE} working space.",
            "outputs": [],
            "skipped_outputs": 0,
        }
    return {"job": job["job"], "timed_out": False, **got}


class Handler(BaseHTTPRequestHandler):
    timeout = 60  # a client that stops sending mid-request does not hold a thread
    server_version = "labbench-runner"
    sys_version = ""

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Runner-Signature", sign(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            return self._send(413, {"error": "The job is too large."})
        body = self.rfile.read(length)
        try:
            job = check(body, self.headers.get("X-Runner-Signature", ""), time.time())
        except Refused as exc:
            return self._send(exc.status, {"error": exc.message})
        if not _slots.acquire(blocking=False):
            return self._send(503, {"error": "The analysis server is busy."})
        try:
            self._send(200, run_job(job))
        finally:
            _slots.release()


def main():
    logging.basicConfig(level=logging.INFO)
    if len(SECRET) < 32:
        raise SystemExit("Set RUNNER_SECRET to at least 32 random characters.")
    bind = os.environ.get("RUNNER_BIND", "0.0.0.0")
    port = _env_int("RUNNER_PORT", 8700)
    log.info("analysis runner on %s:%s, runtime %s", bind, port, RUNTIME)
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
