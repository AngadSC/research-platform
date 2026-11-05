"""Production settings checklist (docs/DEPLOY.md).

Loads config.settings in a fresh interpreter with the variables from deploy/.env.prod.example,
after replacing each placeholder with a realistic dummy value. A fresh process keeps the test
settings out of it. Each failure condition is then checked to actually fail.
"""

import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[2]  # /app in the container
# /deploy is bind-mounted into the dev backend container; the repo root is parents[3] on the host.
ENV_EXAMPLE = Path(__file__).resolve().parents[3] / "deploy" / ".env.prod.example"

LOAD_SCRIPT = """
import json, django
django.setup()
from django.conf import settings as s
print(json.dumps({
    "DEBUG": s.DEBUG,
    "ALLOWED_HOSTS": s.ALLOWED_HOSTS,
    "SESSION_COOKIE_SECURE": s.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": s.CSRF_COOKIE_SECURE,
    "SECRET_KEY_LEN": len(s.SECRET_KEY),
    "INTEGRATION_KEYS": len(s.INTEGRATION_ENCRYPTION_KEYS),
}))
"""


def read_example():
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def realistic(values):
    """Swap placeholders for dummy values that look like the real thing."""
    out = {}
    for key, value in values.items():
        if key == "SECRET_KEY":
            value = secrets.token_urlsafe(64)
        elif key == "INTEGRATION_ENCRYPTION_KEYS":
            value = Fernet.generate_key().decode()
        else:
            value = re.sub(
                r"replace-with-[a-z0-9.-]+", "dummy-" + key.lower().replace("_", "-"), value
            )
        out[key] = value
    return out


def load_settings(tmp_path, overrides):
    """Return (ok, data, stderr) for settings loaded in a subprocess."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT")}
    env.update(realistic(read_example()))
    env.update(overrides)
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        DEV_SECRET_KEY_FILE=str(tmp_path / "secret"),
        DEV_INTEGRATION_KEY_FILE=str(tmp_path / "integration"),
    )
    result = subprocess.run(
        [sys.executable, "-c", LOAD_SCRIPT],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False, None, result.stderr.strip().splitlines()[-1]
    return True, json.loads(result.stdout.strip().splitlines()[-1]), ""


def problems(loaded):
    """The checklist. An empty list means the deployment passes."""
    ok, data, error = loaded
    if not ok:
        return [f"settings refused to load: {error}"]
    found = []
    if data["DEBUG"]:
        found.append("DEBUG is on")
    if not data["ALLOWED_HOSTS"] or "*" in data["ALLOWED_HOSTS"]:
        found.append("ALLOWED_HOSTS is empty or *")
    if not data["SESSION_COOKIE_SECURE"]:
        found.append("session cookie is not secure")
    if not data["CSRF_COOKIE_SECURE"]:
        found.append("CSRF cookie is not secure")
    if data["INTEGRATION_KEYS"] < 1:
        found.append("INTEGRATION_ENCRYPTION_KEYS is missing")
    if data["SECRET_KEY_LEN"] < 50:
        found.append("SECRET_KEY is too short")
    return found


def test_example_passes_checklist(tmp_path):
    assert problems(load_settings(tmp_path, {})) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"DEBUG": "True"},
        {"ALLOWED_HOSTS": ""},
        {"ALLOWED_HOSTS": "*"},
        {"SESSION_COOKIE_SECURE": "False"},
        {"CSRF_COOKIE_SECURE": "False"},
        {"INTEGRATION_ENCRYPTION_KEYS": ""},
        {"SECRET_KEY": "replace-with-generate-a-secret"},
    ],
    ids=[
        "debug-on",
        "hosts-empty",
        "hosts-wildcard",
        "session-insecure",
        "csrf-insecure",
        "no-integration-keys",
        "placeholder-secret",
    ],
)
def test_each_failure_condition_fails(tmp_path, overrides):
    assert problems(load_settings(tmp_path, overrides)), overrides


def test_no_integration_keys_refuses_to_start(tmp_path):
    ok, _, error = load_settings(tmp_path, {"INTEGRATION_ENCRYPTION_KEYS": ""})

    assert not ok
    assert "INTEGRATION_ENCRYPTION_KEYS must be set" in error
