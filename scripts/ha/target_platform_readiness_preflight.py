#!/usr/bin/env python3
"""Read-only target-SHA platform readiness probe for HA preflight.

Proves the target artifact's Meta platform keys without mutating the live tree
and without using tenant Facebook/Instagram binding state as a blocking gate.

The compact target archive is materialized under /var/lib/linasbot/meta-ha,
never on /run tmpfs. Leftover /run/linasbot-target-ready.* trees from a
previous fail-closed run are reclaimed before a new workspace is created.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TENANT_READY_KEYS: tuple[str, ...] = (
    "linas_facebook_app_a_active",
    "linas_instagram_app_a_active",
    "active_credentials_valid",
)
PLATFORM_META_KEYS: tuple[str, ...] = (
    "encryption_key_configured",
    "app_a_configured",
    "registry_backend_ready",
)
COMPACT_ARCHIVE_PATHS: tuple[str, ...] = (
    "modules",
    "services",
    "utils",
    "handlers",
    "storage",
    "db",
    "config.py",
)
CANONICAL_STATE_ROOT = Path("/var/lib/linasbot/meta-ha")
CANONICAL_RUN_DIR = Path("/run")
MAX_ARCHIVE_BYTES = 64 << 20
TARGET_READY_DIR_RE = re.compile(r"^linasbot-target-ready\.[a-z0-9_]{8}$")
TARGET_READY_SCRIPT_RE = re.compile(r"^linasbot-target-platform-ready(\.py|\.[A-Za-z0-9]{6,10})$")
GIT_ISOLATED_ENV = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}
LIVE_READY_URL = "http://127.0.0.1:8003/api/ready"


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


def failing_platform_checks(checks: dict[str, Any]) -> dict[str, Any]:
    failing: dict[str, Any] = {}
    for name, check in checks.items():
        if isinstance(check, dict):
            if check.get("ok") is True:
                continue
            failing[name] = check
            continue
        failing[name] = check
    return failing


def is_legacy_tenant_meta_failure(check: dict[str, Any]) -> bool:
    if check.get("ok") is True:
        return False
    if any(check.get(key) is False for key in PLATFORM_META_KEYS):
        return False
    return any(key in check for key in TENANT_READY_KEYS)


def live_ready_is_platform_admissible(
    status_code: int,
    payload: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("role") not in {None, "readiness"}:
        return False, {"error": "live_ready_role_invalid"}
    raw_checks = payload.get("checks")
    checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}
    failing = failing_platform_checks(checks)
    if status_code == 200 and payload.get("ok") is True and not failing:
        return True, {}
    if status_code == 503 and set(failing) <= {"meta_social_messaging"}:
        meta = failing.get("meta_social_messaging")
        if isinstance(meta, dict) and is_legacy_tenant_meta_failure(meta):
            return True, failing
    return False, failing


def fetch_live_ready(url: str = LIVE_READY_URL) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.load(response)
            return int(response.status), payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.load(exc)
        except (json.JSONDecodeError, TypeError, ValueError) as decode_exc:
            raise RuntimeError("live /api/ready is not JSON") from decode_exc
        return int(exc.code), payload if isinstance(payload, dict) else {}
    except OSError as exc:
        raise RuntimeError("live /api/ready could not be reached") from exc


def _unlink_validated(path: Path, *, parent: Path, require_root: bool) -> None:
    if path.parent.resolve() != parent.resolve():
        raise RuntimeError("volatile target-ready file parent is invalid")
    if TARGET_READY_SCRIPT_RE.fullmatch(path.name) is None:
        raise RuntimeError("volatile target-ready file name is invalid")
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("volatile target-ready file is unsafe")
    if require_root and info.st_uid != 0:
        raise RuntimeError("volatile target-ready file is not root-owned")
    path.unlink()


def _rmtree_validated(path: Path, *, parent: Path, require_root: bool) -> None:
    if path.parent.resolve() != parent.resolve():
        raise RuntimeError("volatile target-ready directory parent is invalid")
    if TARGET_READY_DIR_RE.fullmatch(path.name) is None:
        raise RuntimeError("volatile target-ready directory name is invalid")
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("volatile target-ready directory is unsafe")
    if require_root and info.st_uid != 0:
        raise RuntimeError("volatile target-ready directory is not root-owned")
    shutil.rmtree(path)


def reclaim_volatile_target_ready(
    *,
    run_dir: Path,
    state_root: Path | None = None,
    require_root: bool = True,
) -> list[str]:
    reclaimed: list[str] = []
    if require_root and os.geteuid() != 0:
        raise RuntimeError("volatile target-ready reclaim requires root")
    roots = (run_dir,) if state_root is None else (run_dir, state_root)
    for directory in roots:
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("volatile target-ready reclaim root is unsafe")
        try:
            entries = list(directory.iterdir())
        except FileNotFoundError as exc:
            raise RuntimeError("volatile target-ready reclaim root is missing") from exc
        for entry in entries:
            try:
                info = entry.lstat()
            except FileNotFoundError:
                continue
            if TARGET_READY_SCRIPT_RE.fullmatch(entry.name):
                if stat.S_ISLNK(info.st_mode):
                    raise RuntimeError("volatile target-ready leftover is a symlink")
                _unlink_validated(entry, parent=directory, require_root=require_root)
                reclaimed.append(str(entry))
                continue
            if TARGET_READY_DIR_RE.fullmatch(entry.name):
                if stat.S_ISLNK(info.st_mode):
                    raise RuntimeError("volatile target-ready leftover is a symlink")
                _rmtree_validated(entry, parent=directory, require_root=require_root)
                reclaimed.append(str(entry))
    return reclaimed


def materialize_target_archive(repo: Path, target_sha: str, destination: Path) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", target_sha) is None:
        raise RuntimeError("target SHA is invalid")
    archive = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(repo),
            "archive",
            "--format=tar",
            target_sha,
            "--",
            *COMPACT_ARCHIVE_PATHS,
        ],
        check=True,
        env=GIT_ISOLATED_ENV,
        capture_output=True,
    )
    if len(archive.stdout) < 1 or len(archive.stdout) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("target platform-readiness archive size is invalid")
    subprocess.run(
        ["/usr/bin/tar", "-x", "-C", str(destination)],
        check=True,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        input=archive.stdout,
    )
    if not (destination / "modules" / "dashboard_api_health.py").is_file():
        raise RuntimeError("target platform-readiness archive is missing dashboard health")
    if not (destination / "services" / "meta_app_registry.py").is_file():
        raise RuntimeError("target platform-readiness archive is missing Meta registry")


def evaluate_target_platform_ready(source_root: Path) -> dict[str, Any]:
    assert_platform_readiness_contract(source_root)
    root = str(source_root.resolve())
    if sys.path[:1] != [root]:
        sys.path.insert(0, root)
    from services.meta_app_registry import get_meta_registry_readiness

    meta_ok, meta_checks = get_meta_registry_readiness()
    if not isinstance(meta_checks, dict):
        raise RuntimeError("target registry readiness is not a closed mapping")
    for key in TENANT_READY_KEYS:
        if key in meta_checks:
            raise RuntimeError(f"target ready payload still exposes tenant gate {key}")
    platform = {key: bool(meta_checks.get(key)) for key in PLATFORM_META_KEYS}
    ok = bool(meta_ok) and all(platform.values())
    wrapped = {"ok": ok, **platform}
    return {
        "ok": ok,
        "status_code": 200 if ok else 503,
        "role": "target_platform_readiness_preflight",
        "lb_gate": False,
        "meta_social_messaging": platform,
        "checks": {"meta_social_messaging": wrapped},
        "failing": failing_platform_checks({"meta_social_messaging": wrapped}),
    }


def _maybe_unlink_ephemeral_script() -> None:
    path = Path(__file__).resolve()
    if path.parent != CANONICAL_STATE_ROOT:
        return
    if TARGET_READY_SCRIPT_RE.fullmatch(path.name) is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def run_preflight(
    *,
    repo: Path,
    target_sha: str,
    state_root: Path,
    env_file: str,
    chdir: str,
) -> dict[str, Any]:
    if state_root != CANONICAL_STATE_ROOT:
        raise RuntimeError("target-ready state root is not canonical")
    reclaimed = reclaim_volatile_target_ready(
        run_dir=CANONICAL_RUN_DIR,
        state_root=state_root,
        require_root=True,
    )
    if reclaimed:
        sys.stderr.write("reclaimed volatile target-ready paths: " + ",".join(reclaimed) + "\n")
    status, payload = fetch_live_ready()
    admissible, live_failing = live_ready_is_platform_admissible(status, payload)
    if not admissible:
        sys.stderr.write("live platform dependencies are not healthy\n")
        json.dump({"status_code": status, "failing": live_failing}, sys.stderr)
        sys.stderr.write("\n")
        raise RuntimeError("live platform dependencies are not healthy")
    if chdir:
        os.chdir(chdir)
    if env_file:
        from dotenv import load_dotenv

        load_dotenv(env_file, interpolate=False)
    source_root = Path(tempfile.mkdtemp(prefix="linasbot-target-ready.", dir=state_root))
    os.chmod(source_root, 0o700)
    try:
        materialize_target_archive(repo, target_sha, source_root)
        return evaluate_target_platform_ready(source_root)
    finally:
        _rmtree_validated(source_root, parent=state_root, require_root=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only target platform readiness preflight")
    parser.add_argument("--source-root", default="")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--chdir", default="")
    parser.add_argument("--repo-dir", default="")
    parser.add_argument("--state-root", default="")
    args = parser.parse_args(argv)
    try:
        if args.repo_dir:
            report = run_preflight(
                repo=Path(args.repo_dir),
                target_sha=args.git_sha,
                state_root=Path(args.state_root),
                env_file=args.env_file,
                chdir=args.chdir,
            )
        else:
            source_root = Path(args.source_root)
            if not args.source_root:
                raise RuntimeError("target platform-readiness source root is required")
            if args.chdir:
                os.chdir(args.chdir)
            if args.env_file:
                from dotenv import load_dotenv

                load_dotenv(args.env_file, interpolate=False)
            report = evaluate_target_platform_ready(source_root)
    except Exception as exc:  # noqa: BLE001 — preflight must fail closed
        sys.stderr.write(f"target platform readiness preflight failed: {exc}\n")
        return 1
    finally:
        if args.repo_dir:
            _maybe_unlink_ephemeral_script()
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
        json.dump(
            {
                "status_code": report["status_code"],
                "failing": report["failing"],
            },
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
