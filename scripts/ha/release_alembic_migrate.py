#!/usr/bin/env python3
"""Exact-release Alembic migration authority for HA target verification."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alembic.script import ScriptDirectory

MAINTENANCE = Path("/var/lib/linasbot/meta-ha/maintenance")
ENV_FILE = Path("/opt/linasbot/.env")
REPO = Path("/opt/linasbot")
ALEMBIC_INI = REPO / "alembic.ini"

LEGACY_PRE_MERGE_STAMPS = frozenset(
    {
        "20260813_sfu_channels_enabled",
        "20260814_meta_credential_archived_at",
    }
)
REVIEWED_MULTI_HEAD_STAMPS = frozenset({LEGACY_PRE_MERGE_STAMPS})

_MIGRATION_SECURITY_EXACT_PATHS = frozenset(
    {
        "alembic.ini",
        "scripts/ha/release_alembic_migrate.py",
    }
)
_MIGRATION_SECURITY_PREFIXES = ("alembic/",)

_FORBIDDEN_SUBPROCESS_ENV = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "ALEMBIC_CONFIG",
    }
)


@dataclass(frozen=True)
class MigrationEnvSnapshot:
    mapping: dict[str, str]


def _repo_root() -> Path:
    if (REPO / "alembic.ini").is_file():
        return REPO
    return Path(__file__).resolve().parents[2]


def _canonical_alembic_ini(repo: Path) -> Path:
    if (REPO / "alembic.ini").is_file():
        return ALEMBIC_INI
    return repo / "alembic.ini"


def _assert_runtime_environment(expected: dict[str, str]) -> None:
    fixed_root = {
        "HOME": "/root",
        "USER": "root",
        "LOGNAME": "root",
        "SHELL": "/bin/bash",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PWD": "/opt/linasbot",
    }
    for key in _FORBIDDEN_SUBPROCESS_ENV:
        if os.environ.get(key):
            raise RuntimeError(f"migration authority loaded forbidden environment key: {key}")
    unexpected = set(os.environ) - set(expected)
    extra_names = []
    for key in unexpected:
        value = os.environ[key]
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
            "migration authority loaded an extra non-system configuration key: " + ",".join(sorted(extra_names))
        )


def load_migration_env_snapshot(release_sha: str) -> MigrationEnvSnapshot:
    """Read canonical .env exactly once into an immutable subprocess mapping."""
    from dotenv import dotenv_values

    canonical = dotenv_values(ENV_FILE, interpolate=False)
    if not canonical or any(value is None for value in canonical.values()):
        raise RuntimeError("canonical migration environment is ambiguous")
    mapping = {str(key): str(value) for key, value in canonical.items()}
    mapping.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": "/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin",
            "LINAS_HA_VERIFY_ONLY": "true",
            "LINAS_HA_VERIFY_RELEASE_SHA": release_sha,
            "DISABLE_API_DOCS": "1",
        }
    )
    return MigrationEnvSnapshot(mapping=mapping)


def prepare_migration_authority() -> tuple[str, MigrationEnvSnapshot]:
    if os.environ.get("LINAS_HA_VERIFY_ONLY") != "true":
        raise RuntimeError("HA migration verification-only mode is not explicit")
    release = os.environ.get("LINAS_HA_VERIFY_RELEASE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", release) is None:
        raise RuntimeError("HA migration verification release SHA is invalid")
    if not MAINTENANCE.is_file() or MAINTENANCE.is_symlink():
        raise RuntimeError("persistent maintenance authority is missing")
    snapshot = load_migration_env_snapshot(release)
    if any(os.environ.get(key) != value for key, value in snapshot.mapping.items()):
        raise RuntimeError("migration authority loaded a stale canonical environment")
    _assert_runtime_environment(snapshot.mapping)
    return release, snapshot


def _normalize_repo_relative_path(raw: bytes) -> str:
    if b"\x00" in raw.strip(b"\x00"):
        raise RuntimeError("canonical repo path contains NUL byte")
    try:
        path = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("canonical repo path is not valid UTF-8") from exc
    if not path or path.startswith(("/", "\\")):
        raise RuntimeError(f"canonical repo path is not repo-relative: {path!r}")
    if any(char in path for char in "\n\r\t"):
        raise RuntimeError(f"canonical repo path has unsafe control characters: {path!r}")
    if path != path.strip():
        raise RuntimeError(f"canonical repo path has unsafe surrounding whitespace: {path!r}")
    if path.startswith('"') or path.endswith('"'):
        raise RuntimeError(f"canonical repo path looks quote-escaped: {path!r}")
    normalized = Path(path).as_posix()
    if normalized in {".", ".."}:
        raise RuntimeError(f"canonical repo path escapes repository root: {path!r}")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError(f"canonical repo path escapes repository root: {path!r}")
    return normalized


def _is_migration_security_path(path: str) -> bool:
    if path in _MIGRATION_SECURITY_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _MIGRATION_SECURITY_PREFIXES)


def git_ls_files_others_command(repo: Path, *, ignored: bool) -> list[str]:
    command = ["git", "-C", str(repo), "ls-files", "-z", "--others", "--exclude-standard"]
    if ignored:
        command.append("--ignored")
    return command


def _git_ls_files_others_z(repo: Path, *, ignored: bool) -> list[str]:
    command = git_ls_files_others_command(repo, ignored=ignored)
    proc = subprocess.run(command, check=False, capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed"
        raise RuntimeError(f"canonical repo untracked migration paths could not be inspected: {detail}")
    if not proc.stdout:
        return []
    parts = proc.stdout.split(b"\x00")
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    return [_normalize_repo_relative_path(item) for item in parts if item]


def reject_untracked_migration_paths(repo: Path) -> None:
    """Reject ignored and non-ignored untracked files on migration authority paths."""
    offenders: list[str] = []
    for ignored in (False, True):
        label = "ignored" if ignored else "untracked"
        for path in _git_ls_files_others_z(repo, ignored=ignored):
            if _is_migration_security_path(path):
                offenders.append(f"{label}:{path}")
    if offenders:
        raise RuntimeError(f"canonical repo has untracked migration/config paths: {sorted(offenders)}")


def assert_canonical_release_tree(release_sha: str) -> None:
    repo = _repo_root()
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise RuntimeError("canonical repo HEAD could not be resolved")
    if head.stdout.strip() != release_sha:
        raise RuntimeError("canonical repo HEAD does not match LINAS_HA_VERIFY_RELEASE_SHA")
    tree = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", release_sha],
        check=False,
        capture_output=True,
        text=True,
    )
    if tree.returncode != 0:
        raise RuntimeError("canonical repo tree/index/worktree does not match LINAS_HA_VERIFY_RELEASE_SHA")
    reject_untracked_migration_paths(repo)


def _script_directory() -> ScriptDirectory:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repo = _repo_root()
    cfg = Config(str(_canonical_alembic_ini(repo)))
    return ScriptDirectory.from_config(cfg)


def _expected_head() -> str:
    script = _script_directory()
    heads = list(script.get_heads())
    if len(heads) != 1:
        raise RuntimeError(f"release alembic topology is ambiguous: {heads}")
    return str(heads[0])


def ancestors_of(script: ScriptDirectory, revision_id: str) -> set[str]:
    """All revisions from ``revision_id`` down to base, inclusive."""
    result: set[str] = set()
    stack = [revision_id]
    while stack:
        current_id = stack.pop()
        if current_id in result:
            continue
        revision = script.get_revision(current_id)
        if revision is None:
            continue
        result.add(current_id)
        down = revision.down_revision
        if down is None:
            continue
        if isinstance(down, str):
            stack.append(down)
        elif isinstance(down, (tuple, list)):
            stack.extend(str(parent) for parent in down)
        else:
            raise RuntimeError(f"unsupported alembic down_revision type: {type(down)!r}")
    return result


def validate_stamped_before(stamped: set[str], *, expected_head: str) -> None:
    """Fail closed unless every stamped revision is a known ancestor of ``expected_head``."""
    if not stamped:
        raise RuntimeError("database alembic stamp is empty")
    if stamped == {expected_head}:
        return
    script = _script_directory()
    head_ancestors = ancestors_of(script, expected_head)
    unknown = stamped - head_ancestors
    if unknown:
        raise RuntimeError(f"database alembic stamp includes non-ancestor revisions: {sorted(unknown)}")
    if len(stamped) == 1:
        return
    stamped_frozen = frozenset(stamped)
    if stamped_frozen not in REVIEWED_MULTI_HEAD_STAMPS:
        raise RuntimeError(f"database alembic stamp is ambiguous: {sorted(stamped)}")


def _stamped_versions() -> set[str]:
    from sqlalchemy import text

    from db.session import get_engine

    engine = get_engine(require=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
    return {str(row[0]) for row in rows}


def _run_upgrade_subprocess(repo: Path, *, expected_head: str, env_snapshot: MigrationEnvSnapshot) -> None:
    reject_untracked_migration_paths(repo)
    python_bin = repo / "venv/bin/python"
    alembic_ini = _canonical_alembic_ini(repo)
    result = subprocess.run(
        [
            str(python_bin),
            "-B",
            "-I",
            "-m",
            "alembic",
            "-c",
            str(alembic_ini),
            "upgrade",
            expected_head,
        ],
        cwd=repo,
        env=dict(env_snapshot.mapping),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "alembic upgrade failed")


def main() -> None:
    release_sha, env_snapshot = prepare_migration_authority()
    assert_canonical_release_tree(release_sha)

    repo = _repo_root()
    canonical_entry = repo / "scripts/ha/release_alembic_migrate.py"
    if Path(__file__).resolve() != canonical_entry.resolve():
        raise RuntimeError("HA migration entrypoint path is not canonical")
    reject_untracked_migration_paths(repo)
    sys.path.insert(0, str(repo))

    from db.session import whatsapp_db_configured

    if not whatsapp_db_configured():
        raise RuntimeError("PostgreSQL is required for HA migration authority")

    expected_head = _expected_head()
    stamped_before = _stamped_versions()
    validate_stamped_before(stamped_before, expected_head=expected_head)

    assert_canonical_release_tree(release_sha)
    _run_upgrade_subprocess(repo, expected_head=expected_head, env_snapshot=env_snapshot)

    if list(_script_directory().get_heads()) != [expected_head]:
        raise RuntimeError("post-migration alembic topology is ambiguous")

    stamped_after = _stamped_versions()
    if stamped_after != {expected_head}:
        raise RuntimeError(
            f"post-migration alembic stamp mismatch: expected={expected_head} actual={sorted(stamped_after)}"
        )

    from services.web_chat.flags import get_web_chat_ha_readiness

    ok, checks = get_web_chat_ha_readiness()
    if not ok:
        raise RuntimeError(f"post-migration web chat readiness failed: {checks}")


if __name__ == "__main__":
    main()
