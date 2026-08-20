#!/usr/bin/env python3
"""Admit live /api/ready for an exact SHA without tenant Meta bindings as a gate.

Platform-only SHAs still require HTTP 200. Legacy tenant-gated SHAs may return
503 when the only failing check is Meta tenant flags (Facebook-only, Instagram
inactive, or no channels). Firestore and other platform failures stay refused.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.ha.target_platform_readiness_preflight import (
    GIT_ISOLATED_ENV,
    LIVE_READY_URL,
    TENANT_READY_KEYS,
    fetch_live_ready,
    function_source,
    live_ready_is_platform_admissible,
)

REGISTRY_PATH = "services/meta_app_registry.py"
HEALTH_PATH = "modules/dashboard_api_health.py"


def git_show_text(repo: Path, sha: str, path: str) -> str:
    proc = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(repo),
            "show",
            f"{sha}:{path}",
        ],
        check=False,
        env=GIT_ISOLATED_ENV,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def sha_has_tenant_ready_gates(repo: Path, sha: str) -> bool:
    registry = git_show_text(repo, sha, REGISTRY_PATH)
    health = git_show_text(repo, sha, HEALTH_PATH)
    ready_fn = function_source(registry, "get_meta_registry_readiness") if registry else ""
    if not ready_fn:
        return True
    return any(key in ready_fn or key in health for key in TENANT_READY_KEYS)


def admit_live_ready_for_sha(
    repo: Path,
    sha: str,
    url: str = LIVE_READY_URL,
) -> tuple[int, dict[str, Any]]:
    status, payload = fetch_live_ready(url)
    if sha_has_tenant_ready_gates(repo, sha):
        ok, failing = live_ready_is_platform_admissible(status, payload)
        if not ok:
            raise RuntimeError(
                "legacy /api/ready is not platform-admissible: "
                + json.dumps({"status_code": status, "failing": failing})
            )
        return status, payload
    if status != 200 or payload.get("ok") is not True:
        raise RuntimeError("canonical /api/ready is not healthy")
    return status, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SHA-aware live /api/ready admission")
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--ready-url", default=LIVE_READY_URL)
    parser.add_argument("--probe-tenant-gate", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo_dir)
    try:
        if args.probe_tenant_gate:
            return 0 if sha_has_tenant_ready_gates(repo, args.git_sha) else 1
        admit_live_ready_for_sha(repo, args.git_sha, args.ready_url)
    except Exception as exc:  # noqa: BLE001 — admission must fail closed
        sys.stderr.write(f"live ready admission failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
