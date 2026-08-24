#!/usr/bin/env python3
"""Protected HA runner for Meta comment permission backfill (pre-LB gate).

Invoked from deploy_meta_release_ha.sh after Alembic migrate and before LB
admission once the permission-hardening release is authorized.

Requires LINAS_HA_VERIFY_RELEASE_SHA to match the deployed repo HEAD.
Never prints tokens or secrets.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/opt/linasbot")
BACKFILL = REPO / "scripts/backfill_meta_comment_permission_verification.py"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _die(message: str, code: int = 1) -> None:
    print(f"[meta-comment-backfill-ha] FATAL {message}", file=sys.stderr)
    raise SystemExit(code)


def main() -> int:
    expected_sha = (os.environ.get("LINAS_HA_VERIFY_RELEASE_SHA") or "").strip()
    if _SHA_RE.fullmatch(expected_sha) is None:
        _die("LINAS_HA_VERIFY_RELEASE_SHA missing or invalid")
    if not BACKFILL.is_file():
        _die("backfill script missing from authorized release")

    actual_sha = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    head = (actual_sha.stdout or "").strip()
    if actual_sha.returncode != 0 or head != expected_sha:
        _die("repo HEAD does not match LINAS_HA_VERIFY_RELEASE_SHA")

    blob = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "rev-parse",
            f"{expected_sha}:scripts/backfill_meta_comment_permission_verification.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if blob.returncode != 0:
        _die("backfill script not present in authorized release blob")

    dry_run = (os.environ.get("LINAS_HA_COMMENT_BACKFILL_DRY_RUN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    cmd = [str(REPO / "venv/bin/python"), "-B", "-I", str(BACKFILL)]
    if dry_run:
        cmd.append("--dry-run")

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(cmd, cwd=str(REPO), env=env, check=False, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode == 0:
        print("[meta-comment-backfill-ha] PASS")
        return 0
    if result.returncode == 2:
        print("[meta-comment-backfill-ha] BLOCK unknown active bindings remain after backfill", file=sys.stderr)
        return 2
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    _die(f"backfill helper failed exit={result.returncode}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
