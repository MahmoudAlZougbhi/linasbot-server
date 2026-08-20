#!/usr/bin/env python3
"""Read-only target-SHA platform readiness probe for HA preflight.

Runs the target artifact's /api/ready evaluator without mutating the live tree
and without using tenant Facebook/Instagram binding state as a blocking gate.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

TENANT_READY_KEYS: tuple[str, ...] = (
    "linas_facebook_app_a_active",
    "linas_instagram_app_a_active",
    "active_credentials_valid",
)


def function_source(module_text: str, name: str) -> str:
    tree = ast.parse(module_text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(module_text, node) or ""
    return ""


def assert_platform_readiness_contract(source_root: Path) -> None:
    registry = (source_root / "services" / "meta_app_registry.py").read_text(encoding="utf-8")
    health = (source_root / "modules" / "dashboard_api_health.py").read_text(encoding="utf-8")
    if "META_PLATFORM_READINESS_KEYS" not in registry:
        raise RuntimeError("target registry is missing platform readiness keys")
    ready_fn = function_source(registry, "get_meta_registry_readiness")
    if not ready_fn:
        raise RuntimeError("target registry is missing get_meta_registry_readiness")
    if "list_bindings" in ready_fn:
        raise RuntimeError("target registry readiness still inspects tenant bindings")
    for key in TENANT_READY_KEYS:
        if key in ready_fn or key in health:
            raise RuntimeError(f"target readiness still carries tenant gate {key}")


def evaluate_target_platform_ready(source_root: Path) -> dict[str, Any]:
    assert_platform_readiness_contract(source_root)
    root = str(source_root.resolve())
    if sys.path[:1] != [root]:
        sys.path.insert(0, root)
    from fastapi.responses import JSONResponse

    from modules.dashboard_api_health import ready

    response = asyncio.run(ready())
    if not isinstance(response, JSONResponse):
        raise RuntimeError("target readiness evaluator returned an unexpected response")
    payload = json.loads(bytes(response.body))
    meta = payload.get("checks", {}).get("meta_social_messaging", {})
    for key in TENANT_READY_KEYS:
        if key in meta:
            raise RuntimeError(f"target ready payload still exposes tenant gate {key}")
    return {
        "ok": response.status_code == 200 and payload.get("ok") is True,
        "status_code": response.status_code,
        "role": payload.get("role"),
        "lb_gate": False,
        "meta_social_messaging": meta,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only target platform readiness preflight")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--chdir", default="")
    args = parser.parse_args(argv)
    source_root = Path(args.source_root)
    if args.chdir:
        os.chdir(args.chdir)
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(args.env_file, interpolate=False)
    try:
        report = evaluate_target_platform_ready(source_root)
    except Exception as exc:  # noqa: BLE001 — preflight must fail closed
        sys.stderr.write(f"target platform readiness preflight failed: {exc}\n")
        return 1
    json.dump(
        {
            "ok": report["ok"],
            "role": "target_platform_readiness_preflight",
            "lb_gate": False,
            "git_sha": args.git_sha,
            "status_code": report["status_code"],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    if not report["ok"]:
        sys.stderr.write("target artifact platform readiness is not healthy\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
