#!/usr/bin/env python3
"""Read-only deploy preflight: can a new user Connect each channel?

Stdlib only so HA can execute it with `python -I -S`. Never inspects tenant
bindings, tokens, or connection state. Missing users must not block deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CONNECT_ROUTE_MARKERS: tuple[tuple[str, str], ...] = (
    ("modules/meta_connections_api.py", '@app.post("/api/meta/connections/start")'),
    ("modules/meta_connections_api.py", '@app.post("/api/meta/connections/instagram-login/start")'),
    ("modules/meta_connections_api.py", '@app.get("/oauth/instagram/callback")'),
    ("modules/meta_connections_api.py", '@app.get("/oauth/meta/callback")'),
    ("modules/meta_messaging_webhook.py", '@app.get("/webhook/meta-messaging")'),
    ("modules/meta_messaging_webhook.py", '@app.post("/webhook/meta-messaging")'),
    ("modules/meta_instagram_login_webhook.py", '@app.get("/webhook/instagram-login")'),
    ("modules/meta_instagram_login_webhook.py", '@app.post("/webhook/instagram-login")'),
    ("modules/tiktok_business_api.py", '@app.post("/api/tiktok/connect/start")'),
    ("modules/tiktok_business_oauth.py", '@app.get("/oauth/tiktok/callback")'),
    ("modules/tiktok_business_webhook.py", '@app.post("/webhook/tiktok")'),
    ("modules/whatsapp_cloud_api.py", '@app.post("/api/whatsapp/cloud/connect/start")'),
    ("modules/whatsapp_cloud_api.py", '@app.get("/oauth/whatsapp/callback")'),
    ("modules/whatsapp_cloud_webhook.py", '@app.get("/webhook/whatsapp-cloud")'),
    ("modules/whatsapp_cloud_webhook.py", '@app.post("/webhook/whatsapp-cloud")'),
    ("modules/web_chat_public_routes.py", '@app.post("/api/web-chat/session")'),
    ("modules/web_chat_mobile_routes.py", '@app.get("/api/mobile/web-chat")'),
)


def evaluate_deploy_preflight(
    *,
    source_root: Path | None = None,
    git_dir: Path | None = None,
    git_sha: str | None = None,
    env_values: dict[str, str] | None = None,
    check_env: bool = True,
) -> dict[str, Any]:
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    blobs: dict[str, str] = {}
    for relative, marker in CONNECT_ROUTE_MARKERS:
        if relative not in blobs:
            try:
                blobs[relative] = _read_source(relative, source_root=source_root, git_dir=git_dir, git_sha=git_sha)
            except RuntimeError as exc:
                blocking.append({"check": f"route:{relative}", "reason": str(exc)})
                continue
        if marker not in blobs[relative]:
            blocking.append({"check": f"route:{marker}", "reason": "connect_route_missing"})
    if check_env:
        values = env_values if env_values is not None else {}
        blocking.extend(_env_blocking(values))
    return {
        "ok": not blocking,
        "role": "deploy_preflight",
        "lb_gate": False,
        "blocking": blocking,
        "warnings": warnings,
    }


def _read_source(
    relative: str,
    *,
    source_root: Path | None,
    git_dir: Path | None,
    git_sha: str | None,
) -> str:
    if git_dir is not None and git_sha:
        return _git_show(git_dir, git_sha, relative)
    if source_root is None:
        raise RuntimeError("source_unavailable")
    path = source_root / relative
    if not path.is_file():
        raise RuntimeError("source_missing")
    return path.read_text(encoding="utf-8")


def _git_show(git_dir: Path, git_sha: str, relative: str) -> str:
    result = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(git_dir),
            "show",
            f"{git_sha}:{relative}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("source_missing")
    return result.stdout


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _present(values: dict[str, str], names: tuple[str, ...]) -> bool:
    return any((values.get(name) or "").strip() for name in names)


def _env_blocking(values: dict[str, str]) -> list[dict[str, str]]:
    blocking: list[dict[str, str]] = []
    encryption = (values.get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(encryption) < 32:
        blocking.append({"check": "token_storage", "reason": "encryption_key_missing"})
    if not _present(values, ("META_APP_A_ID", "META_APP_ID")):
        blocking.append({"check": "platform_secrets", "reason": "meta_app_id_missing"})
    if not _present(values, ("META_APP_A_SECRET", "META_APP_SECRET")):
        blocking.append({"check": "platform_secrets", "reason": "meta_app_secret_missing"})
    if not _present(values, ("META_APP_A_WEBHOOK_VERIFY_TOKEN", "META_WEBHOOK_VERIFY_TOKEN")):
        blocking.append({"check": "platform_secrets", "reason": "meta_verify_token_missing"})
    backend = (values.get("META_REGISTRY_BACKEND") or "postgres").strip().lower()
    if backend in {"postgres", "dual"} and not _present(values, ("LINAS_WHATSAPP_DATABASE_URL", "DATABASE_URL")):
        blocking.append({"check": "registry_backend", "reason": "database_url_missing"})
    return blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only integration capability preflight")
    parser.add_argument("--source-root", default="")
    parser.add_argument("--git-dir", default="")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--skip-env", action="store_true")
    args = parser.parse_args(argv)
    env_values: dict[str, str] | None = None
    check_env = not args.skip_env
    if check_env and args.env_file:
        env_path = Path(args.env_file)
        if not env_path.is_file():
            report = {
                "ok": False,
                "role": "deploy_preflight",
                "blocking": [{"check": "platform_secrets", "reason": "env_file_missing"}],
                "warnings": [],
            }
            json.dump(report, sys.stdout)
            sys.stdout.write("\n")
            return 1
        env_values = _parse_env_file(env_path)
    elif check_env:
        env_values = {key: str(value) for key, value in os.environ.items()}
    source_root = Path(args.source_root) if args.source_root else None
    git_dir = Path(args.git_dir) if args.git_dir else None
    report = evaluate_deploy_preflight(
        source_root=source_root,
        git_dir=git_dir,
        git_sha=args.git_sha or None,
        env_values=env_values,
        check_env=check_env,
    )
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    if not report["ok"]:
        sys.stderr.write("integration capability preflight failed\n")
        for item in report["blocking"]:
            sys.stderr.write(f"{item['check']}: {item['reason']}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
