#!/usr/bin/env python3
"""Run an allowlisted Meta operation with only canonical production Meta settings."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

from scripts.ha.meta_env_file import require_secure_env_file

REPO_DIR = Path("/opt/linasbot")
ENV_PATH = REPO_DIR / ".env"
META_KEY_RE = re.compile(r"^META_[A-Z0-9_]+$")
COMMANDS = {
    "reconcile-app-webhooks": REPO_DIR / "scripts/reconcile_meta_app_webhooks.py",
    "reconcile-comment-webhooks": REPO_DIR / "scripts/reconcile_meta_comment_webhooks.py",
    "validate-social-token": REPO_DIR / "scripts/validate_meta_social_token.py",
}
CONTROL_KEYS = frozenset(
    {
        "META_EXPECT_FACEBOOK_COMMENT_DELIVERY",
        "META_FACEBOOK_COMMENT_SWITCH_ENABLED",
        "META_INSTAGRAM_COMMENT_SWITCH_ENABLED",
        "META_RECONCILE_PAGE_SUBSCRIPTION",
    }
)


def _canonical_meta_values(path: Path) -> dict[str, str]:
    require_secure_env_file(path)
    parsed = dotenv_values(path, interpolate=False)
    values = {
        str(key): "" if value is None else str(value)
        for key, value in parsed.items()
        if META_KEY_RE.fullmatch(str(key))
    }
    if not values:
        raise RuntimeError("Canonical Meta environment is empty")
    return values


def _build_environment(
    *,
    env_path: Path,
    ambient: dict[str, str],
    passthrough: tuple[str, ...],
) -> dict[str, str]:
    if any(key not in CONTROL_KEYS for key in passthrough):
        raise RuntimeError("Meta operation control key is not allowlisted")
    result = {key: value for key, value in ambient.items() if not META_KEY_RE.fullmatch(key)}
    result.update(_canonical_meta_values(env_path))
    for key in passthrough:
        value = str(ambient.get(key) or "").strip().lower()
        if value not in {"true", "false"}:
            raise RuntimeError("Meta operation control value is invalid")
        result[key] = value
    result["PYTHONPATH"] = str(REPO_DIR)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--passthrough", action="append", default=[])
    args = parser.parse_args()
    command = COMMANDS[args.command]
    if not command.is_file():
        raise RuntimeError("Allowlisted Meta operation is unavailable")
    environment = _build_environment(
        env_path=ENV_PATH,
        ambient=dict(os.environ),
        passthrough=tuple(args.passthrough),
    )
    os.execve(
        str(REPO_DIR / "venv/bin/python"),
        [str(REPO_DIR / "venv/bin/python"), str(command)],
        environment,
    )
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"[meta-canonical-env] failed={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
