#!/usr/bin/env python3
"""Serialize privileged production mutations against the exact deployed release.

This runner is intentionally small and read-only until it executes one allowlisted
script.  It owns the common live lock for the entire child lifetime, verifies the
canonical production environment contract, and refuses to overlap any durable HA
transaction or recovery state.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_DIR = Path("/opt/linasbot")
ENV_PATH = REPO_DIR / ".env"
STATE_ROOT = Path("/var/lib/linasbot/meta-ha")
VOLATILE_MAINTENANCE = Path("/run/linasbot-maintenance")
LOCK_PATH = Path("/run/lock/linasbot-meta-live.lock")
GIT_BIN = "/usr/bin/git"
BASH_BIN = "/bin/bash"
SHA_RE = re.compile(r"[0-9a-f]{40}")
ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")

# Only reviewed production entrypoints may run below the global mutation lock.
ALLOWED_SCRIPTS = frozenset(
    {
        "scripts/prod_apply_copilot_v2_flags.sh",
        "scripts/prod_apply_dashboard_auth.sh",
        "scripts/prod_apply_model_routing_policy.sh",
        "scripts/prod_apply_openai_api_key.sh",
        "scripts/prod_apply_resend_secrets.sh",
        "scripts/prod_cm_apply_flags.sh",
        "scripts/prod_cm_backup.sh",
        "scripts/prod_cm_bridge_readiness.sh",
        "scripts/prod_cm_corpus_inventory.sh",
        "scripts/prod_cm_cutover.sh",
        "scripts/prod_cm_generic_tenant_proof.sh",
        "scripts/prod_cm_import_prices.sh",
        "scripts/prod_cm_linas_content_audit.sh",
        "scripts/prod_cm_migrate_and_validate.sh",
        "scripts/prod_cm_preserve_durable_flags.sh",
        "scripts/prod_cm_price_line_shape_probe.sh",
        "scripts/prod_cm_price_source_ledger.sh",
        "scripts/prod_cm_publish.sh",
        "scripts/prod_cm_publish_faq_only.sh",
        "scripts/prod_cm_repair_linas_prices_publish.sh",
        "scripts/prod_cm_rollback.sh",
        "scripts/prod_cm_rollback_version.sh",
        "scripts/prod_cm_runtime_proof.sh",
        "scripts/prod_cm_set_linas_bridge_flag.sh",
        "scripts/prod_cm_sot_audit.sh",
        "scripts/prod_cm_verify_durable_bridge.sh",
        "scripts/prod_wa_connection_source_migrate.sh",
        "scripts/prod_wa_app_review_bind.sh",
        "scripts/prod_whatsapp_cloud_phase1_ops.sh",
    }
)

# These entrypoints change a non-Meta EnvironmentFile key and/or restart only
# one node today.  They remain inventoried but cannot be launched by this runner
# until a separately reviewed generic two-node env backup/sync/rollback proof is
# implemented.  The existing Meta synchronizer intentionally copies META_* only.
TWO_NODE_ENV_TRANSACTION_REQUIRED = frozenset(
    {
        "scripts/prod_apply_copilot_v2_flags.sh",
        "scripts/prod_apply_dashboard_auth.sh",
        "scripts/prod_apply_model_routing_policy.sh",
        "scripts/prod_apply_openai_api_key.sh",
        "scripts/prod_apply_resend_secrets.sh",
        "scripts/prod_cm_apply_flags.sh",
        "scripts/prod_cm_cutover.sh",
        "scripts/prod_cm_preserve_durable_flags.sh",
        "scripts/prod_cm_rollback.sh",
        "scripts/prod_cm_set_linas_bridge_flag.sh",
        "scripts/prod_cm_verify_durable_bridge.sh",
        "scripts/prod_whatsapp_cloud_phase1_ops.sh",
    }
)

# These two writers are also used from the HA release transaction while the
# node is drained.  That caller must present the exact transaction directory,
# target release, deploy sentinel and inherited common lock; ordinary direct
# invocation is never accepted.
DEPLOY_TRANSACTION_SCRIPTS = frozenset(
    {
        "scripts/prod_cm_preserve_durable_flags.sh",
        "scripts/prod_upsert_model_routing_env.py",
    }
)
DIRECT_MUTATION_SCRIPTS = frozenset(
    {
        "scripts/ha/import_meta_registry_to_postgres.py",
        "scripts/ha/meta_registry_pg_snapshot.py",
    }
)

FIXED_COLLISION_PATHS = (
    "maintenance",
    "bootstrap.active",
    "bootstrap.coordinator.json",
    "deploy.active",
    "deploy-node.active",
    "transaction.json",
    "env.before",
    "workers.before.json",
    "prestage.authority.json",
    "controlled-failover.active",
    "registry-nfs-retire.active",
    "rekey/runtime.guard",
)
SCRIPT_CONTROL_ENV_KEYS = {
    "scripts/prod_cm_apply_flags.sh": frozenset(
        {
            "CM_EMBEDDING_MODEL_VALUE",
            "CM_EMBEDDING_PROVIDER_VALUE",
            "CM_FAQ_CANONICAL_VALUE",
            "CM_PUBLISH_ENABLED_VALUE",
            "CM_RUNTIME_MODE_VALUE",
        }
    ),
    "scripts/prod_cm_rollback_version.sh": frozenset({"CM_ROLLBACK_CONTENT_VERSION_ID"}),
    "scripts/prod_cm_verify_durable_bridge.sh": frozenset({"VERIFY_RELOAD"}),
    "scripts/prod_wa_connection_source_migrate.sh": frozenset({"CONFIRM", "PHASE"}),
}
FIXED_CHILD_ENV = {
    "HOME": "/root",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "LOGNAME": "root",
    "PATH": "/opt/linasbot/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "USER": "root",
}
FORBIDDEN_EXECUTION_ENV_KEYS = frozenset(
    {
        "BASHOPTS",
        "BASH_ENV",
        "CDPATH",
        "ENV",
        "GLOBIGNORE",
        "GCONV_PATH",
        "GLIBC_TUNABLES",
        "IFS",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "LOCPATH",
        "MALLOC_TRACE",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NLSPATH",
        "PATH",
        "PERL5LIB",
        "PERL5OPT",
        "PROMPT_COMMAND",
        "PYTHONBREAKPOINT",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONPLATLIBDIR",
        "PYTHONPYCACHEPREFIX",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "PYTHONWARNINGS",
        "RUBYLIB",
        "RUBYOPT",
        "SHELLOPTS",
        "SSLKEYLOGFILE",
        "_JAVA_OPTIONS",
        "JAVA_TOOL_OPTIONS",
    }
)
FORBIDDEN_EXECUTION_ENV_PREFIXES = (
    "BASH_FUNC_",
    "DYLD_",
    "GIT_CONFIG_",
    "LD_",
    "LINAS_DEPLOY_MUTATION_",
    "LINAS_PRODUCTION_MUTATION_",
)


def _run_git(repo_dir: Path, *args: str, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [GIT_BIN, "-C", str(repo_dir), *args],
        check=False,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _normalize_script(raw: str) -> str:
    candidate = PurePosixPath(str(raw))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError("Production mutation script path is invalid")
    normalized = candidate.as_posix()
    if normalized not in ALLOWED_SCRIPTS:
        raise RuntimeError("Production mutation script is not allowlisted")
    return normalized


def _normalize_deploy_script(raw: str) -> str:
    candidate = PurePosixPath(str(raw))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError("Deploy mutation script path is invalid")
    normalized = candidate.as_posix()
    if normalized not in DEPLOY_TRANSACTION_SCRIPTS:
        raise RuntimeError("Deploy mutation script is not allowlisted")
    return normalized


def _normalize_direct_script(raw: str) -> str:
    candidate = PurePosixPath(str(raw))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError("Direct mutation script path is invalid")
    normalized = candidate.as_posix()
    if normalized not in DIRECT_MUTATION_SCRIPTS:
        raise RuntimeError("Direct mutation script is not allowlisted")
    return normalized


def _require_no_untracked_runtime_source(repo_dir: Path) -> None:
    pathspecs = ("scripts", "services", "db", "modules", "handlers", "storage", ":(top,glob)*.py")
    for ignored in (False, True):
        arguments = ["ls-files", "--others", "--exclude-standard"]
        if ignored:
            arguments.append("--ignored")
        arguments.extend(("--", *pathspecs))
        result = _run_git(repo_dir, *arguments, capture=True)
        if result.returncode != 0:
            raise RuntimeError("Unable to audit untracked production source")
        candidates = result.stdout.decode("utf-8", "strict").splitlines()
        if any(Path(value).suffix.lower() in {".py", ".sh", ".bash"} for value in candidates):
            raise RuntimeError("Untracked or ignored production source can shadow the authorized release")


def _require_exact_release(repo_dir: Path, expected_sha: str, script: str) -> Path:
    if SHA_RE.fullmatch(expected_sha) is None:
        raise RuntimeError("Authorized release SHA is invalid")
    if repo_dir.resolve(strict=True) != repo_dir:
        raise RuntimeError("Production repository path is noncanonical")
    head = _run_git(repo_dir, "rev-parse", "HEAD", capture=True)
    if head.returncode != 0 or head.stdout.decode("ascii", "strict").strip() != expected_sha:
        raise RuntimeError("Authorized release does not equal deployed HEAD")
    if _run_git(repo_dir, "diff", "--quiet", expected_sha, "--").returncode != 0:
        raise RuntimeError("Deployed tracked worktree differs from the authorized release")
    if _run_git(repo_dir, "diff", "--cached", "--quiet", expected_sha, "--").returncode != 0:
        raise RuntimeError("Deployed index differs from the authorized release")
    _require_no_untracked_runtime_source(repo_dir)

    path = repo_dir / script
    current = path.lstat()
    if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
        raise RuntimeError("Allowlisted production script is not a regular file")
    blob = _run_git(repo_dir, "show", f"{expected_sha}:{script}", capture=True)
    if blob.returncode != 0 or blob.stdout != path.read_bytes():
        raise RuntimeError("Production script does not equal its authorized release blob")
    return path


def _require_secure_env(path: Path, *, owner_uid: int = 0, owner_gid: int = 0) -> None:
    current = path.lstat()
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or stat.S_IMODE(current.st_mode) != 0o600
        or current.st_uid != owner_uid
        or current.st_gid != owner_gid
    ):
        raise RuntimeError("Canonical production environment security contract is invalid")


def _looks_like_active_transaction(path: Path) -> bool:
    name = path.name
    return (
        name.endswith(".active")
        or name.endswith(".coordinator.json")
        or name.endswith(".journal.json")
        or name in {"transaction.json", "journal.json", "runtime.guard", "maintenance"}
    )


def _require_no_ha_transaction(
    state_root: Path,
    *,
    volatile_maintenance: Path = VOLATILE_MAINTENANCE,
) -> None:
    for relative in FIXED_COLLISION_PATHS:
        path = state_root / relative
        if path.exists() or path.is_symlink():
            raise RuntimeError("A durable HA transaction or recovery artifact is active")
    if volatile_maintenance.exists() or volatile_maintenance.is_symlink():
        raise RuntimeError("Volatile HA maintenance is active")
    if not state_root.exists():
        return
    if state_root.is_symlink() or not state_root.is_dir():
        raise RuntimeError("Meta HA state root is invalid")
    for path in state_root.rglob("*"):
        if _looks_like_active_transaction(path):
            raise RuntimeError("An unrecognized durable HA transaction artifact is active")


def _preflight(
    *,
    expected_sha: str,
    script: str,
    repo_dir: Path = REPO_DIR,
    env_path: Path = ENV_PATH,
    state_root: Path = STATE_ROOT,
    volatile_maintenance: Path = VOLATILE_MAINTENANCE,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> Path:
    normalized = _normalize_script(script)
    path = _require_exact_release(repo_dir, expected_sha, normalized)
    _require_secure_env(env_path, owner_uid=owner_uid, owner_gid=owner_gid)
    _require_no_ha_transaction(state_root, volatile_maintenance=volatile_maintenance)
    return path


def acquire_direct_production_mutation_lock(
    *,
    expected_sha: str,
    script: str,
    env_path: Path,
    repo_dir: Path = REPO_DIR,
    canonical_env: Path = ENV_PATH,
    state_root: Path = STATE_ROOT,
    volatile_maintenance: Path = VOLATILE_MAINTENANCE,
    lock_path: Path = LOCK_PATH,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> int:
    """Acquire the common lock and gate an exact direct production writer."""

    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Direct production mutation requires root")
    normalized = _normalize_direct_script(script)
    if env_path != canonical_env or env_path.resolve(strict=True) != canonical_env:
        raise RuntimeError("Direct production mutation requires the canonical environment")
    descriptor = _open_lock(lock_path)
    try:
        _require_exact_release(repo_dir, expected_sha, normalized)
        _require_secure_env(canonical_env, owner_uid=owner_uid, owner_gid=owner_gid)
        _require_no_ha_transaction(state_root, volatile_maintenance=volatile_maintenance)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _build_child_environment(
    *,
    expected_sha: str,
    script: str,
    lock_fd: int,
    ambient: dict[str, str],
    env_path: Path = ENV_PATH,
) -> dict[str, str]:
    from dotenv import dotenv_values

    parsed = dotenv_values(env_path, interpolate=False)
    canonical: dict[str, str] = {}
    control_keys = SCRIPT_CONTROL_ENV_KEYS.get(script, frozenset())
    for raw_key, raw_value in parsed.items():
        key = str(raw_key)
        value = "" if raw_value is None else str(raw_value)
        if key in FORBIDDEN_EXECUTION_ENV_KEYS or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES):
            raise RuntimeError("Canonical production environment contains an execution-control key")
        if key.startswith("PYTHON") and (key, value) not in {
            ("PYTHONUNBUFFERED", "1"),
            ("PYTHONDONTWRITEBYTECODE", "1"),
        }:
            raise RuntimeError("Canonical production environment contains a Python semantic-control key")
        if ENV_KEY_RE.fullmatch(key) is None or any(character in value for character in ("\0", "\r", "\n")):
            raise RuntimeError("Canonical production environment contains an invalid entry")
        if key == "EXPECTED_RELEASE_SHA" or key in control_keys:
            continue
        canonical[key] = value
    if not canonical:
        raise RuntimeError("Canonical production environment is empty")
    child = dict(FIXED_CHILD_ENV)
    child.update(canonical)
    child.update({key: ambient[key] for key in control_keys if key in ambient})
    child.update(
        {
            "EXPECTED_RELEASE_SHA": expected_sha,
            "LINAS_PRODUCTION_MUTATION_GUARD_ACTIVE": "true",
            "LINAS_PRODUCTION_MUTATION_SCRIPT": script,
            "LINAS_PRODUCTION_MUTATION_LOCK_FD": str(lock_fd),
        }
    )
    return child


def _open_lock(path: Path = LOCK_PATH) -> int:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise RuntimeError("Production mutation lock path is invalid")
        os.fchmod(descriptor, 0o600)
        if os.geteuid() == 0:
            os.fchown(descriptor, 0, 0)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.set_inheritable(descriptor, True)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _require_inherited_lock(descriptor: int, path: Path = LOCK_PATH) -> None:
    if descriptor < 3 or not os.get_inheritable(descriptor):
        raise RuntimeError("Production mutation lock descriptor is invalid")
    opened = os.fstat(descriptor)
    current = path.lstat()
    if (
        not stat.S_ISREG(opened.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise RuntimeError("Production mutation lock is not inherited from the guarded runner")
    probe = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe, fcntl.LOCK_UN)
            raise RuntimeError("Production mutation lock descriptor does not own the common lock")
    finally:
        os.close(probe)


def _read_secure_regular(path: Path, *, mode: int = 0o600) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != mode
    ):
        raise RuntimeError("Deploy transaction artifact security contract is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("Deploy transaction artifact changed while opening")
        return os.read(descriptor, 65536)
    finally:
        os.close(descriptor)


def _require_deploy_transaction(
    *,
    expected_sha: str,
    tx_dir: Path,
    state_root: Path = STATE_ROOT,
    volatile_maintenance: Path = VOLATILE_MAINTENANCE,
) -> None:
    expected_prefix = f"/var/backups/linasbot-ha/{expected_sha}-"
    if (
        re.fullmatch(rf"{re.escape(expected_prefix)}[0-9]{{14}}-[0-9]+", str(tx_dir)) is None
        or tx_dir.resolve(strict=True) != tx_dir
    ):
        raise RuntimeError("Deploy transaction directory is invalid")
    tx_info = tx_dir.lstat()
    if (
        not stat.S_ISDIR(tx_info.st_mode)
        or stat.S_ISLNK(tx_info.st_mode)
        or tx_info.st_uid != 0
        or tx_info.st_gid != 0
        or stat.S_IMODE(tx_info.st_mode) != 0o700
    ):
        raise RuntimeError("Deploy transaction directory security contract is invalid")
    if _read_secure_regular(tx_dir / "target.sha").decode("ascii", "strict").strip() != expected_sha:
        raise RuntimeError("Deploy transaction target differs from the authorized release")
    if _read_secure_regular(tx_dir / "stage.complete").decode("ascii", "strict").strip() != "staged":
        raise RuntimeError("Deploy transaction stage is incomplete")
    if _read_secure_regular(tx_dir / "activation.state").decode("ascii", "strict").strip() != "runtime-stopped":
        raise RuntimeError("Deploy mutation is outside the drained activation phase")
    sentinel = state_root / "deploy-node.active"
    if _read_secure_regular(sentinel).decode("utf-8", "strict").strip() != str(tx_dir):
        raise RuntimeError("Per-node deploy sentinel belongs to another transaction")
    for marker in (state_root / "maintenance", volatile_maintenance):
        if _read_secure_regular(marker):
            raise RuntimeError("Deploy maintenance marker must be empty")

    allowed = {
        state_root / "maintenance",
        state_root / "deploy.active",
        sentinel,
    }
    for relative in FIXED_COLLISION_PATHS:
        path = state_root / relative
        if path not in allowed and (path.exists() or path.is_symlink()):
            raise RuntimeError("Another durable HA transaction or recovery artifact is active")
    if state_root.is_symlink() or not state_root.is_dir():
        raise RuntimeError("Meta HA state root is invalid")
    for path in state_root.rglob("*"):
        if _looks_like_active_transaction(path) and path not in allowed:
            raise RuntimeError("An unrecognized durable HA transaction artifact is active")


def _deploy_preflight(
    *,
    expected_sha: str,
    script: str,
    tx_dir: Path,
    lock_fd: int,
    repo_dir: Path = REPO_DIR,
    env_path: Path = ENV_PATH,
) -> Path:
    normalized = _normalize_deploy_script(script)
    _require_inherited_lock(lock_fd)
    path = _require_exact_release(repo_dir, expected_sha, normalized)
    _require_secure_env(env_path)
    _require_deploy_transaction(expected_sha=expected_sha, tx_dir=tx_dir)
    return path


def require_mutation_context_from_environment(script: str) -> int:
    """Validate the active ordinary or HA-deploy context and return its lock fd."""

    expected_sha = os.environ.get("EXPECTED_RELEASE_SHA", "")
    raw_fd = os.environ.get("LINAS_PRODUCTION_MUTATION_LOCK_FD", "")
    if not raw_fd.isdigit():
        raise RuntimeError("Production mutation lock descriptor is absent")
    lock_fd = int(raw_fd)
    if os.environ.get("LINAS_PRODUCTION_MUTATION_GUARD_ACTIVE") == "true":
        normalized = _normalize_script(script)
        if os.environ.get("LINAS_PRODUCTION_MUTATION_SCRIPT") != normalized:
            raise RuntimeError("Production mutation context is not bound to this script")
        _require_inherited_lock(lock_fd)
        _preflight(expected_sha=expected_sha, script=normalized)
        return lock_fd
    if os.environ.get("LINAS_DEPLOY_MUTATION_GUARD_ACTIVE") == "true":
        normalized = _normalize_deploy_script(script)
        if os.environ.get("LINAS_DEPLOY_MUTATION_SCRIPT") != normalized:
            raise RuntimeError("Deploy mutation context is not bound to this script")
        _deploy_preflight(
            expected_sha=expected_sha,
            script=normalized,
            tx_dir=Path(os.environ.get("LINAS_DEPLOY_MUTATION_TX_DIR", "")),
            lock_fd=lock_fd,
        )
        return lock_fd
    raise RuntimeError("A guarded production or HA deploy mutation context is required")


def _command_run(args: argparse.Namespace) -> int:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Production mutation runner requires root")
    script = _normalize_script(args.script)
    if script in TWO_NODE_ENV_TRANSACTION_REQUIRED:
        raise RuntimeError("Non-Meta environment mutation requires a two-node HA transaction")
    lock_fd = _open_lock()
    try:
        script_path = _preflight(expected_sha=args.expected_sha, script=script)
        child_env = _build_child_environment(
            expected_sha=args.expected_sha,
            script=script,
            lock_fd=lock_fd,
            ambient=dict(os.environ),
        )
        script_args = list(args.script_args)
        if script_args[:1] == ["--"]:
            script_args = script_args[1:]
        completed = subprocess.run(
            [BASH_BIN, str(script_path), *script_args],
            cwd=REPO_DIR,
            env=child_env,
            pass_fds=(lock_fd,),
            check=False,
        )
        return int(completed.returncode)
    finally:
        os.close(lock_fd)


def _command_verify_context(args: argparse.Namespace) -> int:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Production mutation context requires root")
    script = _normalize_script(args.script)
    if (
        os.environ.get("LINAS_PRODUCTION_MUTATION_GUARD_ACTIVE") != "true"
        or os.environ.get("LINAS_PRODUCTION_MUTATION_SCRIPT") != script
        or os.environ.get("EXPECTED_RELEASE_SHA") != args.expected_sha
    ):
        raise RuntimeError("Production mutation context is not bound to this script")
    raw_fd = os.environ.get("LINAS_PRODUCTION_MUTATION_LOCK_FD", "")
    if not raw_fd.isdigit():
        raise RuntimeError("Production mutation lock descriptor is absent")
    _require_inherited_lock(int(raw_fd))
    _preflight(expected_sha=args.expected_sha, script=script)
    print(f"[prod-mutation] context_verified=true script={script}")
    return 0


def _command_verify_deploy_context(args: argparse.Namespace) -> int:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Deploy mutation context requires root")
    script = _normalize_deploy_script(args.script)
    if (
        os.environ.get("LINAS_DEPLOY_MUTATION_GUARD_ACTIVE") != "true"
        or os.environ.get("LINAS_DEPLOY_MUTATION_SCRIPT") != script
        or os.environ.get("EXPECTED_RELEASE_SHA") != args.expected_sha
        or os.environ.get("LINAS_DEPLOY_MUTATION_TX_DIR") != args.tx_dir
    ):
        raise RuntimeError("Deploy mutation context is not bound to this script")
    raw_fd = os.environ.get("LINAS_PRODUCTION_MUTATION_LOCK_FD", "")
    if not raw_fd.isdigit():
        raise RuntimeError("Production mutation lock descriptor is absent")
    _deploy_preflight(
        expected_sha=args.expected_sha,
        script=script,
        tx_dir=Path(args.tx_dir),
        lock_fd=int(raw_fd),
    )
    print(f"[prod-mutation] deploy_context_verified=true script={script}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--expected-sha", required=True)
    run.add_argument("--script", required=True)
    run.add_argument("script_args", nargs=argparse.REMAINDER)
    verify = commands.add_parser("verify-context")
    verify.add_argument("--expected-sha", required=True)
    verify.add_argument("--script", required=True)
    verify_deploy = commands.add_parser("verify-deploy-context")
    verify_deploy.add_argument("--expected-sha", required=True)
    verify_deploy.add_argument("--script", required=True)
    verify_deploy.add_argument("--tx-dir", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "run":
        return _command_run(args)
    if args.command == "verify-context":
        return _command_verify_context(args)
    if args.command == "verify-deploy-context":
        return _command_verify_deploy_context(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[prod-mutation] blocked={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
