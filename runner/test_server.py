"""Unit tests for the analysis runner, with docker mocked. Run: python -m unittest -v test_server
(from runner/). With RUNNER_SMOKE=1 and the python image built, test_smoke runs a real container
(RUNNER_RUNTIME=runc where gVisor is not installed)."""

import base64
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import unittest
from unittest import mock

import server

SECRET = b"s" * 40


def signed(job):
    body = json.dumps(job).encode()
    return body, server.hmac.new(SECRET, body, server.hashlib.sha256).hexdigest()


def job(**over):
    j = {"ts": int(time.time()), "job": os.urandom(8).hex(), "language": "python", "code": "1"}
    return {**j, **over}


def b64(data):
    return base64.b64encode(data).decode()


def tar_of(members):
    """members: name -> bytes, or name -> ("link", tarfile type) for a link entry."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            if not isinstance(data, tuple):
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                info.type, info.linkname = data[1], "/etc/passwd"
                tar.addfile(info)
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(server, "SECRET", SECRET)
        p.start()
        self.addCleanup(p.stop)
        server._seen.clear()


class Signature(Base):
    def test_a_good_job_passes(self):
        body, sig = signed(job(files=[{"name": "rt.csv", "data": b64(b"a,b\n")}]))
        got = server.check(body, sig, time.time())
        self.assertEqual(got["files"], [("rt.csv", b"a,b\n")])

    def test_bad_or_missing_signature(self):
        body, sig = signed(job())
        for bad in ("", "0" * 64, sig[:-1] + ("0" if sig[-1] != "0" else "1"), "é"):
            with self.assertRaises(server.Refused) as e:
                server.check(body, bad, time.time())
            self.assertEqual(e.exception.status, 401)
        with self.assertRaises(server.Refused):  # a changed body breaks the signature
            server.check(body.replace(b'"1"', b'"2"'), sig, time.time())

    def test_no_secret_refuses_everything(self):
        with mock.patch.object(server, "SECRET", b""):
            body = json.dumps(job()).encode()
            sig = server.hmac.new(b"", body, server.hashlib.sha256).hexdigest()
            with self.assertRaises(server.Refused):
                server.check(body, sig, time.time())

    def test_old_and_future_jobs_are_refused(self):
        for ts in (time.time() - 301, time.time() + 301, "now", True, None):
            body, sig = signed(job(ts=ts))
            with self.assertRaises(server.Refused) as e:
                server.check(body, sig, time.time())
            self.assertEqual(e.exception.status, 401)

    def test_replay_is_refused(self):
        body, sig = signed(job())
        server.check(body, sig, time.time())
        with self.assertRaises(server.Refused) as e:
            server.check(body, sig, time.time() + 10)
        self.assertEqual(e.exception.status, 409)


class Caps(Base):
    def refused(self, **over):
        body, sig = signed(job(**over))
        with self.assertRaises(server.Refused) as e:
            server.check(body, sig, time.time())
        self.assertEqual(e.exception.status, 400)
        return e.exception.message

    def test_language_and_code(self):
        self.refused(language="bash")
        self.refused(code="")
        self.refused(code="x" * (server.MAX_CODE + 1))

    def test_input_names(self):
        for name in ("../etc/passwd", "a/b.csv", ".job", ".hidden", "out", "", None, "a\nb"):
            self.refused(files=[{"name": name, "data": ""}])
        msg = self.refused(files=[{"name": "a.csv", "data": ""}, {"name": "a.csv", "data": ""}])
        self.assertIn("Two input files", msg)

    def test_input_count_size_and_encoding(self):
        self.refused(files=[{"name": f"f{i}", "data": ""} for i in range(server.MAX_FILES + 1)])
        self.refused(files=[{"name": "a", "data": "not base64!"}])
        with mock.patch.object(server, "MAX_INPUT_BYTES", 10):
            self.refused(
                files=[{"name": "a", "data": b64(b"x" * 6)}, {"name": "b", "data": b64(b"y" * 6)}]
            )


class DockerArgs(unittest.TestCase):
    def test_every_isolation_flag_is_there(self):
        with mock.patch.object(server, "RUNTIME", "runsc"):
            args = server.docker_args("job-1", "python")
        for flag in (
            "--runtime=runsc",
            "--network=none",
            "--log-driver=none",
            "--read-only",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pull=never",
            "--rm",
            f"--memory={server.MEMORY}",
            f"--memory-swap={server.MEMORY}",
            f"--cpus={server.CPUS}",
            f"--pids-limit={server.PIDS}",
        ):
            self.assertIn(flag, args)
        tmpfs = [a for a in args if a.startswith("--tmpfs=/work:")]
        self.assertEqual(len(tmpfs), 1)
        self.assertIn(f"size={server.WORK_SIZE}", tmpfs[0])
        self.assertIn("noexec", tmpfs[0])
        self.assertFalse(
            any(a.startswith(("-v", "--volume", "--mount", "--privileged")) for a in args)
        )
        self.assertEqual(args[args.index("labbench-runner-python") + 1], "run-job")

    def test_each_language_has_its_image(self):
        for lang, image in (("r", "labbench-runner-r"), ("octave", "labbench-runner-octave")):
            self.assertIn(image, server.docker_args("j", lang))


class ReadBack(unittest.TestCase):
    def test_only_regular_files_from_out_come_back_by_base_name(self):
        got = server.read_back(
            tar_of({
                ".stdout": b"hello",
                ".stderr": b"",
                ".exit": b"0\n",
                "out/fig.png": b"PNG",
                "out/sub/table.csv": b"a,b",
                "out/../../etc/x": b"no",
                "secret.txt": b"input, not an output",
                "out/link": ("link", tarfile.SYMTYPE),
                "out/hard": ("link", tarfile.LNKTYPE),
                "out/.hidden": b"no",
            })
        )  # fmt: skip
        self.assertEqual((got["exit_code"], got["stdout"]), (0, "hello"))
        self.assertEqual(
            {o["name"]: base64.b64decode(o["data"]) for o in got["outputs"]},
            {"fig.png": b"PNG", "table.csv": b"a,b"},
        )
        self.assertEqual(got["skipped_outputs"], 1)  # .hidden

    def test_output_caps(self):
        files = {f"out/f{i}.txt": b"x" for i in range(server.MAX_OUTPUTS + 3)}
        got = server.read_back(tar_of({".exit": b"0", **files}))
        self.assertEqual((len(got["outputs"]), got["skipped_outputs"]), (server.MAX_OUTPUTS, 3))
        with mock.patch.object(server, "MAX_OUTPUT_BYTES", 3):
            got = server.read_back(tar_of({".exit": b"0", "out/big": b"xxxx", "out/ok": b"xx"}))
        self.assertEqual([o["name"] for o in got["outputs"]], ["ok"])
        with mock.patch.object(server, "MAX_OUTPUTS_TOTAL", 5):
            got = server.read_back(tar_of({".exit": b"0", "out/a": b"xxx", "out/b": b"xxx"}))
        self.assertEqual([o["name"] for o in got["outputs"]], ["a"])
        got = server.read_back(tar_of({".exit": b"0", "out/a/x": b"1", "out/b/x": b"2"}))
        self.assertEqual(len(got["outputs"]), 1)  # the same base name twice

    def test_sparse_members_and_huge_logs_are_bounded(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
            info = tarfile.TarInfo(".stdout")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"abc"))
        with mock.patch.object(tarfile.TarInfo, "issparse", lambda self: True):
            got = server.read_back(buf.getvalue())
        self.assertEqual(got["stdout"], "")  # a sparse member is skipped outright
        big = server.read_back(tar_of({".exit": b"0", ".stdout": b"y" * (server.MAX_LOG * 9)}))
        self.assertLess(len(big["stdout"]), server.MAX_LOG * 4 + 100)

    def test_long_output_is_cut(self):
        got = server.read_back(tar_of({".exit": b"1", ".stderr": b"e" * (server.MAX_LOG + 50)}))
        self.assertTrue(got["stderr"].endswith("[cut: 50 more characters]"))
        self.assertEqual(got["exit_code"], 1)


class RunJob(unittest.TestCase):
    JOB = {"job": "j1", "language": "python", "code": "print(1)", "files": [("rt.csv", b"1")]}

    def test_the_job_goes_in_on_stdin_and_the_container_is_removed(self):
        back = tar_of({".stdout": b"1\n", ".stderr": b"", ".exit": b"0", "out/a.txt": b"A"})
        calls = []

        def docker(args, stdin, timeout):
            calls.append((args, stdin, timeout))
            return 0, back, b""

        with (
            mock.patch.object(server, "_run_docker", side_effect=docker),
            mock.patch.object(server.subprocess, "run") as rm,
        ):
            got = server.run_job(self.JOB)
        self.assertEqual((got["exit_code"], got["stdout"], got["job"]), (0, "1\n", "j1"))
        run_args, stdin, timeout = calls[0]
        name = next(a for a in run_args if a.startswith("--name=")).removeprefix("--name=")
        self.assertEqual(timeout, server.TIMEOUT)
        with tarfile.open(fileobj=io.BytesIO(stdin)) as tar:
            self.assertEqual(sorted(tar.getnames()), [".job/main.py", "rt.csv"])
        self.assertEqual(rm.call_args[0][0], ["docker", "rm", "-f", name])

    def test_the_time_limit_kills_the_container(self):
        def docker(args, stdin, timeout):
            raise subprocess.TimeoutExpired(args, timeout)

        with (
            mock.patch.object(server, "_run_docker", side_effect=docker),
            mock.patch.object(server.subprocess, "run") as rm,
        ):
            got = server.run_job(self.JOB)
        self.assertTrue(got["timed_out"])
        self.assertEqual(got["outputs"], [])
        self.assertEqual(rm.call_args[0][0][:3], ["docker", "rm", "-f"])

    def test_out_of_memory(self):
        with (
            mock.patch.object(server, "_run_docker", return_value=(137, b"", b"")),
            mock.patch.object(server.subprocess, "run"),
        ):
            got = server.run_job(self.JOB)
        self.assertEqual((got["exit_code"], got["stderr"]), (137, "The run ran out of memory."))

    def test_a_flood_of_output_is_stopped_not_buffered(self):
        flood = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 2_000_000)"]
        with mock.patch.object(server, "WORK_SIZE", "1k"):
            with self.assertRaises(server.OutputTooLarge):
                server._run_docker(flood, b"", 20)
        code, out, _ = server._run_docker([sys.executable, "-c", "print('hi')"], b"", 20)
        self.assertEqual((code, out.strip()), (0, b"hi"))


@unittest.skipUnless(os.environ.get("RUNNER_SMOKE"), "set RUNNER_SMOKE=1 to run a real container")
class Smoke(unittest.TestCase):
    def test_python_writes_a_figure(self):
        code = (
            "import pandas as pd, matplotlib.pyplot as plt\n"
            "d = pd.read_csv('rt.csv')\n"
            "print(d['rt'].mean())\n"
            "d.plot(x='id', y='rt'); plt.savefig('out/rt.png')\n"
            "import urllib.request\n"
            "try:\n"
            "    urllib.request.urlopen('http://example.com', timeout=3); print('NETWORK')\n"
            "except Exception:\n"
            "    print('offline')\n"
            "open('/etc/x', 'w')\n"
        )
        job = {"job": "smoke", "language": "python", "code": code,
               "files": [("rt.csv", b"id,rt\n1,500\n2,520\n")]}  # fmt: skip
        got = server.run_job(job)
        self.assertEqual(got["stdout"].split(), ["510.0", "offline"], got)
        self.assertEqual(got["exit_code"], 1)  # the read-only image refused /etc/x
        self.assertRegex(got["stderr"], "Read-only file system|Permission denied")
        png = base64.b64decode(got["outputs"][0]["data"])
        self.assertEqual((got["outputs"][0]["name"], png[:4]), ("rt.png", b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
