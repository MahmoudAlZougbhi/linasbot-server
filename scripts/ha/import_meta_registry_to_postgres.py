#!/usr/bin/env python3
"""Guarded one-time import of file-backed Meta registry state into Postgres.

The command is dry-run by default. Direct ``--apply`` is currently fail-closed
until a reviewed two-node release/environment/drain coordinator owns it. The
preflight holds the registry file lock and Postgres registry advisory lock from
source read through target verification.
It will never overwrite a non-empty divergent target unless every destructive
replace guard is supplied, including a verified encrypted pre-import snapshot.

Intended coordinator-owned empty-target import contract (not directly enabled):
  sudo ... --env-file /opt/linasbot/.env \
    --expected-release-sha 40_HEX_DEPLOYED_SHA \
    --store /opt/linasbot_data/meta_registry/registry.json \
    --apply --expected-source-sha256 SHA --expected-target-sha256 SHA_OF_EMPTY

Intended destructive-replacement contract (normally wrong and directly disabled):
  sudo ... --env-file /opt/linasbot/.env --expected-release-sha 40_HEX_DEPLOYED_SHA \
    --apply --dangerously-replace-nonempty \
    --confirm REPLACE_NONEMPTY_META_REGISTRY --prior-backup SNAPSHOT \
    --expected-source-sha256 SHA --expected-target-sha256 SHA \
    --expected-target-tables-sha256 SHA
"""

from __future__ import annotations

import argparse
import fcntl
import hmac
import json
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPLACE_CONFIRMATION = "REPLACE_NONEMPTY_META_REGISTRY"


def _default_store() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT) / "meta_registry" / "registry.json"


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("apply requires root privileges")


def _validate_sha256(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _validate_secure_regular_file(path: Path, *, label: str) -> os.stat_result:
    """Require a root-owned, non-symlink, exact-0600 regular file."""

    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError(f"{label} must be a regular non-symlink file")
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != 0 or info.st_gid != 0:
        raise PermissionError(f"{label} must be root:root mode 0600")
    return info


def _read_registry_from_fd(fd: int) -> dict[str, Any]:
    with os.fdopen(os.dup(fd), "r", encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("registry source is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("registry source schema is invalid")
    for key in ("bindings", "credentials", "oauth_states"):
        if not isinstance(raw.get(key), dict):
            raise ValueError("registry source structure is invalid")
    return raw


def _normalize_file_state_for_postgres(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the explicit PG schema defaults before import/fingerprint compare."""

    normalized: dict[str, Any] = {
        "schema_version": 1,
        "bindings": {},
        "credentials": {},
        "oauth_states": {},
    }
    for binding_key, raw in state["bindings"].items():
        if not isinstance(raw, dict):
            raise ValueError("registry source binding row is invalid")
        binding_id = str(raw.get("binding_id") or binding_key)
        normalized["bindings"][binding_key] = {
            "binding_id": binding_id,
            "tenant_id": str(raw["tenant_id"]),
            "channel": str(raw["channel"]),
            "asset_id": str(raw["asset_id"]),
            "page_id": str(raw.get("page_id") or ""),
            "instagram_account_id": str(raw.get("instagram_account_id") or ""),
            "app_key": str(raw["app_key"]),
            "credential_id": str(raw["credential_id"]),
            "status": str(raw["status"]),
            "generation": int(raw.get("generation") or 1),
            "created_at": float(raw.get("created_at") or 0),
            "updated_at": float(raw.get("updated_at") or 0),
            "previous_binding_id": str(raw.get("previous_binding_id") or ""),
            "page_name": str(raw.get("page_name") or ""),
            "instagram_username": str(raw.get("instagram_username") or ""),
            "authorized_meta_user_id_hash": str(raw.get("authorized_meta_user_id_hash") or ""),
            "superseded_by_binding_id": str(raw.get("superseded_by_binding_id") or ""),
            "auth_flow": str(raw.get("auth_flow") or "facebook_login"),
            "webhook_subscription_status": str(raw.get("webhook_subscription_status") or "unknown"),
            "webhook_subscribed_fields": list(raw.get("webhook_subscribed_fields") or []),
            "webhook_subscription_error": str(raw.get("webhook_subscription_error") or ""),
            "webhook_subscription_checked_at": float(raw.get("webhook_subscription_checked_at") or 0),
            "comment_permission_status": str(raw.get("comment_permission_status") or "unknown"),
            "comment_permission_verified_at": float(raw.get("comment_permission_verified_at") or 0),
            "comment_permission_source": str(raw.get("comment_permission_source") or ""),
            "comment_permission_credential_id": str(raw.get("comment_permission_credential_id") or ""),
            "comment_permission_token_fingerprint": str(raw.get("comment_permission_token_fingerprint") or ""),
        }
    for credential_key, raw in state["credentials"].items():
        if not isinstance(raw, dict):
            raise ValueError("registry source credential row is invalid")
        normalized["credentials"][credential_key] = {
            "binding_id": str(raw["binding_id"]),
            "aad": str(raw["aad"]),
            "sealed": str(raw["sealed"]),
            "created_at": float(raw.get("created_at") or 0),
            "archived_at": float(raw.get("archived_at") or 0),
        }
    for nonce, raw in state["oauth_states"].items():
        if not isinstance(raw, dict):
            raise ValueError("registry source OAuth row is invalid")
        normalized["oauth_states"][nonce] = dict(raw)
    return normalized


def _assert_registry_unchanged(store_path: Path, baseline: os.stat_result) -> None:
    after = os.lstat(store_path)
    before_token = (baseline.st_dev, baseline.st_ino, baseline.st_size, baseline.st_mtime_ns)
    after_token = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if after_token != before_token:
        raise RuntimeError("registry source changed during the guarded import")


@contextmanager
def _locked_registry_file(store_path: Path) -> Iterator[tuple[int, os.stat_result]]:
    """Hold the production file lock and an O_NOFOLLOW source descriptor."""

    _validate_secure_regular_file(store_path, label="registry source")
    lock_path = store_path.with_suffix(".lock")
    _validate_secure_regular_file(lock_path, label="registry lock")
    lock_flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(lock_path, lock_flags)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        source_fd = os.open(store_path, source_flags)
        try:
            opened = os.fstat(source_fd)
            current = os.lstat(store_path)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise RuntimeError("registry source changed while it was opened")
            source_locked = _validate_secure_regular_file(store_path, label="registry source")
            yield source_fd, source_locked
            _assert_registry_unchanged(store_path, source_locked)
        finally:
            os.close(source_fd)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


@contextmanager
def _locked_registry_source(store_path: Path) -> Iterator[tuple[dict[str, Any], os.stat_result]]:
    """Read-only convenience wrapper used by the stale-NFS verifier."""

    with _locked_registry_file(store_path) as (source_fd, source_info):
        yield _read_registry_from_fd(source_fd), source_info


def _is_empty_fingerprint(fingerprint: dict[str, Any]) -> bool:
    return all(int(fingerprint.get(key) or 0) == 0 for key in ("binding_count", "credential_count", "oauth_count"))


def _verify_prior_backup(
    path: Path,
    *,
    recovery_secret: str,
    expected_target_sha256: str,
    expected_target_tables_sha256: str,
) -> None:
    from scripts.ha.meta_registry_pg_snapshot import read_encrypted_snapshot
    from services.meta_app_registry_pg_store import registry_tables_fingerprint

    _validate_secure_regular_file(path, label="prior backup")
    snapshot = read_encrypted_snapshot(path, recovery_secret=recovery_secret)
    fingerprint = registry_tables_fingerprint(snapshot)
    if (
        fingerprint["state_sha256"] != expected_target_sha256
        or fingerprint["tables_sha256"] != expected_target_tables_sha256
    ):
        raise RuntimeError("prior backup does not match the expected current Postgres registry")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Path to root:root 0600 registry.json",
    )
    parser.add_argument("--env-file", type=Path, default=None, help="secure canonical DB/key env (required to apply)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="blocked pending a reviewed two-node coordinator (default: dry-run)",
    )
    parser.add_argument("--expected-release-sha", default="", help="exact deployed release required for --apply")
    parser.add_argument("--expected-source-sha256", default="", help="required source CAS digest for --apply")
    parser.add_argument("--expected-target-sha256", default="", help="required target CAS digest for --apply")
    parser.add_argument(
        "--expected-target-tables-sha256",
        default="",
        help="required four-table CAS digest for non-empty replacement",
    )
    parser.add_argument("--dangerously-replace-nonempty", action="store_true")
    parser.add_argument("--confirm", default="", help=f"exact token for divergent replace: {REPLACE_CONFIRMATION}")
    parser.add_argument("--prior-backup", type=Path, default=None, help="verified encrypted four-table snapshot")
    parser.add_argument(
        "--backup-recovery-key-file",
        type=Path,
        default=None,
        help="independent root-only recovery key for --prior-backup",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store_path = Path(os.path.abspath(os.fspath(args.store or _default_store())))
    mutation_lock_fd: int | None = None

    try:
        if args.apply:
            if args.env_file is None:
                raise PermissionError("--apply requires the canonical environment")
            from scripts.ha.production_mutation_guard import acquire_direct_production_mutation_lock

            mutation_lock_fd = acquire_direct_production_mutation_lock(
                expected_sha=args.expected_release_sha,
                script="scripts/ha/import_meta_registry_to_postgres.py",
                env_path=Path(os.path.abspath(os.fspath(args.env_file))),
            )
            print(
                "BLOCKED: direct registry import requires a signed, current, both-node-drained coordinator",
                file=sys.stderr,
            )
            raise PermissionError(
                "--apply requires a reviewed two-node release/env/drain coordinator; direct import is disabled"
            )
        if args.env_file is not None:
            from scripts.ha.meta_registry_pg_snapshot import load_runtime_environment

            load_runtime_environment(args.env_file, require_postgres_backend=False)
        elif args.apply:
            raise PermissionError("--apply requires --env-file with canonical DB and key settings")

        from db.session import whatsapp_session
        from services.meta_app_registry_pg_store import (
            acquire_registry_advisory_lock,
            load_registry_tables_snapshot,
            load_state,
            registry_tables_fingerprint,
            save_state,
            state_fingerprint,
        )

        if args.apply:
            _require_root()
            expected_source = _validate_sha256(args.expected_source_sha256, label="expected source")
            expected_target = _validate_sha256(args.expected_target_sha256, label="expected target")
        else:
            expected_source = ""
            expected_target = ""

        with _locked_registry_file(store_path) as (source_fd, source_info):
            with whatsapp_session(require=True) as session:
                # The transaction-scoped lock is released only by commit/rollback.
                acquire_registry_advisory_lock(session)
                # Both the file lock and PG advisory lock are now held before
                # reading either authority. They stay held through verification.
                file_state = _normalize_file_state_for_postgres(_read_registry_from_fd(source_fd))
                from scripts.ha.verify_meta_registry_postgres import (
                    validate_credential_decryption,
                    validate_state_invariants,
                )

                source_issues = validate_state_invariants(file_state)
                source_issues.extend(
                    validate_credential_decryption(
                        file_state,
                        (os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip(),
                    )
                )
                if source_issues:
                    raise ValueError("registry source failed structural or credential validation")
                file_fp = state_fingerprint(file_state)
                print(
                    "source "
                    f"bindings={file_fp['binding_count']} credentials={file_fp['credential_count']} "
                    f"oauth={file_fp['oauth_count']} sha256={file_fp['state_sha256']}"
                )
                target_snapshot = load_registry_tables_snapshot(session)
                target_tables_fp = registry_tables_fingerprint(target_snapshot)
                target_state = target_snapshot["state"]
                target_fp = state_fingerprint(target_state)
                print(
                    "target "
                    f"bindings={target_fp['binding_count']} credentials={target_fp['credential_count']} "
                    f"oauth={target_fp['oauth_count']} sha256={target_fp['state_sha256']}"
                )

                if args.apply and (
                    file_fp["state_sha256"] != expected_source or target_fp["state_sha256"] != expected_target
                ):
                    raise RuntimeError("source or target changed after operator preflight")

                if file_fp == target_fp:
                    _assert_registry_unchanged(store_path, source_info)
                    print("OK: source and target already match; no write performed")
                    return 0

                target_nonempty = not _is_empty_fingerprint(target_fp)
                if target_nonempty:
                    if not args.apply:
                        print(
                            "BLOCKED: Postgres is non-empty and divergent; source import would overwrite authority",
                            file=sys.stderr,
                        )
                        return 3
                    if not args.dangerously_replace_nonempty or args.confirm != REPLACE_CONFIRMATION:
                        raise PermissionError("non-empty divergent Postgres replacement was not explicitly confirmed")
                    if args.prior_backup is None:
                        raise PermissionError("non-empty replacement requires a prior encrypted four-table backup")
                    if args.backup_recovery_key_file is None:
                        raise PermissionError("non-empty replacement requires the independent backup recovery key")
                    expected_tables = _validate_sha256(
                        args.expected_target_tables_sha256,
                        label="expected target four-table",
                    )
                    if target_tables_fp["tables_sha256"] != expected_tables:
                        raise RuntimeError("target four-table state changed after operator preflight")
                    backup_path = Path(os.path.abspath(os.fspath(args.prior_backup)))
                    from scripts.ha.meta_registry_pg_snapshot import load_snapshot_recovery_key

                    recovery_secret = load_snapshot_recovery_key(args.backup_recovery_key_file)
                    runtime_secret = (os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
                    if hmac.compare_digest(recovery_secret, runtime_secret):
                        raise PermissionError("backup recovery key must be independent from the runtime master key")
                    _verify_prior_backup(
                        backup_path,
                        recovery_secret=recovery_secret,
                        expected_target_sha256=expected_target,
                        expected_target_tables_sha256=expected_tables,
                    )

                if not args.apply:
                    _assert_registry_unchanged(store_path, source_info)
                    print("DRY-RUN: empty target is eligible; rerun with digest CAS values and --apply")
                    return 0

                save_state(session, file_state)
                session.flush()
                written_fp = state_fingerprint(load_state(session))
                if written_fp != file_fp:
                    raise RuntimeError("post-import deep fingerprint verification failed")
                # Must run before the DB context commits, not only when the file
                # context exits, so a non-cooperating source replacement rolls
                # back the target transaction.
                _assert_registry_unchanged(store_path, source_info)
                print(
                    "OK: guarded import verified "
                    f"bindings={written_fp['binding_count']} credentials={written_fp['credential_count']} "
                    f"oauth={written_fp['oauth_count']} sha256={written_fp['state_sha256']}"
                )
                return 0
    except Exception as exc:  # noqa: BLE001 - never serialize DB/secret-bearing exception text
        print(f"ERROR: guarded import failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    finally:
        if mutation_lock_fd is not None:
            os.close(mutation_lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
