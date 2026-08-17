#!/usr/bin/env python3
"""One-shot, non-routable full readiness probe for an HA target release."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

MAINTENANCE = Path("/var/lib/linasbot/meta-ha/maintenance")
ENV_FILE = Path("/opt/linasbot/.env")
REPO = Path("/opt/linasbot")


def _assert_authority() -> str:
    if os.environ.get("LINAS_HA_VERIFY_ONLY") != "true":
        raise RuntimeError("HA readiness verification-only mode is not explicit")
    release = os.environ.get("LINAS_HA_VERIFY_RELEASE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", release) is None:
        raise RuntimeError("HA readiness verification release SHA is invalid")
    if not MAINTENANCE.is_file() or MAINTENANCE.is_symlink():
        raise RuntimeError("persistent maintenance authority is missing")
    from dotenv import dotenv_values

    canonical = dotenv_values(ENV_FILE, interpolate=False)
    if not canonical or any(value is None for value in canonical.values()):
        raise RuntimeError("canonical readiness-probe environment is ambiguous")
    expected = {str(key): str(value) for key, value in canonical.items()}
    expected.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": "/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin",
            "LINAS_HA_VERIFY_ONLY": "true",
            "LINAS_HA_VERIFY_RELEASE_SHA": release,
            "DISABLE_API_DOCS": "1",
        }
    )
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError("readiness probe loaded a stale canonical environment")
    fixed_root = {
        "HOME": "/root",
        "USER": "root",
        "LOGNAME": "root",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PWD": "/opt/linasbot",
    }
    unexpected = set(os.environ) - set(expected)
    extra_names = []
    for key in unexpected:
        value = os.environ[key]
        if key == "SHELL" and value.strip() in {
            "/bin/bash",
            "/bin/sh",
            "/bin/dash",
            "/usr/bin/bash",
            "/usr/bin/sh",
            "/usr/bin/dash",
            "/usr/sbin/nologin",
            "/sbin/nologin",
        }:
            continue
        if key in fixed_root and value == fixed_root[key]:
            continue
        if key == "INVOCATION_ID" and re.fullmatch(r"[0-9a-f]{32}", value):
            continue
        if key == "JOURNAL_STREAM" and re.fullmatch(r"[0-9]+:[0-9]+", value):
            continue
        if key in {"SYSTEMD_EXEC_PID", "WATCHDOG_PID", "WATCHDOG_USEC"} and re.fullmatch(r"[1-9][0-9]*", value):
            continue
        if key == "MEMORY_PRESSURE_WATCH" and value.startswith("/sys/fs/cgroup/"):
            continue
        if key == "MEMORY_PRESSURE_WRITE" and re.fullmatch(r"[A-Za-z0-9+/=]+", value):
            continue
        if key == "NOTIFY_SOCKET" and value in {
            "/run/systemd/notify",
            "@/org/freedesktop/systemd1/notify",
        }:
            continue
        extra_names.append(key)
    if extra_names:
        raise RuntimeError(
            "readiness probe loaded an extra non-system configuration key: " + ",".join(sorted(extra_names))
        )
    return release


def main() -> None:
    _assert_authority()
    if Path(__file__).resolve() != REPO / "scripts/ha/release_readiness_probe.py":
        raise RuntimeError("HA readiness probe entrypoint path is not canonical")
    sys.path.insert(0, str(REPO))
    # The imports stay intentionally narrow. Dependencies are imported lazily
    # by the exact production readiness evaluator, never by application startup.
    from fastapi.responses import JSONResponse

    from modules.core import app
    from modules.dashboard_api_health import readiness_for_ha_verification

    if {str(getattr(route, "path", "")) for route in app.routes} != {
        "/",
        "/api/health",
        "/api/ready",
    }:
        raise RuntimeError("HA readiness probe route surface is not exact")
    response = asyncio.run(readiness_for_ha_verification())
    if not isinstance(response, JSONResponse):
        raise RuntimeError("HA readiness evaluator returned an unexpected response")
    payload = json.loads(bytes(response.body))
    if response.status_code != 200 or payload.get("ok") is not True:
        raise RuntimeError("target dependency readiness failed")
    forbidden = {"modules.event_handlers", "storage.migrate_bootstrap"}
    if forbidden.intersection(sys.modules):
        raise RuntimeError("HA readiness probe imported side-effectful application startup")


if __name__ == "__main__":
    main()
