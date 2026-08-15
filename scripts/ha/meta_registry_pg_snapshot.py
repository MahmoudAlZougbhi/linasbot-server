#!/usr/bin/env python3
"""Encrypted, CAS-guarded backup/verify/restore for Meta registry PG tables.

The four-table snapshot contains identifiers and credential ciphertext, so it is
always AES-256-GCM encrypted using a mandatory independent root-only recovery
key.  The possibly exposed runtime credential key is used only to validate the
inner credential envelopes and can never decrypt the outer snapshot.  Files are
atomically created in a root-owned private directory as root:root 0600.  No
command prints row identifiers, OAuth payloads, AAD, ciphertext, or secrets.

All commands require root. Snapshot creation remains explicit ``--apply``;
direct restore ``--apply`` is fail-closed until a reviewed two-node
release/environment/drain coordinator owns it. Restore creates and verifies an encrypted snapshot of the current
target before any database row is changed and uses a current-target digest CAS.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SNAPSHOT_FORMAT = "linas-meta-registry-pg-snapshot-v2"
SNAPSHOT_AAD = b"linas-meta-registry-pg-snapshot-v2\x00four-tables"


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Meta registry snapshot operations require root")


def _snapshot_key(recovery_secret: str) -> bytes:
    secret = str(recovery_secret or "").strip()
    if len(secret) < 32:
        raise RuntimeError("independent snapshot recovery key must contain at least 32 characters")
    return hashlib.sha256(b"linas-meta-registry-pg-snapshot-v2\x00" + secret.encode("utf-8")).digest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if _b64encode(decoded) != raw:
        raise ValueError("snapshot contains non-canonical base64")
    return decoded


def _secure_file_info(path: Path, *, label: str) -> os.stat_result:
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError(f"{label} must be a regular non-symlink file")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError(f"{label} must be root:root mode 0600")
    return info


def _secure_parent(path: Path) -> None:
    info = os.lstat(path.parent)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError("snapshot parent must be a real directory")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("snapshot parent must be root-owned and inaccessible to group/other")


def encode_encrypted_snapshot(snapshot: dict[str, Any], *, recovery_secret: str) -> dict[str, Any]:
    from services.meta_app_registry_pg_store import registry_tables_fingerprint

    plaintext = _canonical_bytes(snapshot)
    nonce = os.urandom(12)
    fingerprint = registry_tables_fingerprint(snapshot)
    authenticated_metadata = {
        "format": SNAPSHOT_FORMAT,
        "created_at": int(time.time()),
        "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
        "fingerprint": fingerprint,
    }
    aad = SNAPSHOT_AAD + b"\x00" + _canonical_bytes(authenticated_metadata)
    ciphertext = AESGCM(_snapshot_key(recovery_secret)).encrypt(nonce, plaintext, aad)
    return {
        **authenticated_metadata,
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
    }


def decode_encrypted_snapshot(envelope: dict[str, Any], *, recovery_secret: str) -> dict[str, Any]:
    from services.meta_app_registry_pg_store import registry_tables_fingerprint

    if not isinstance(envelope, dict) or envelope.get("format") != SNAPSHOT_FORMAT:
        raise ValueError("unsupported Meta registry snapshot format")
    try:
        authenticated_metadata = {
            "format": envelope["format"],
            "created_at": int(envelope["created_at"]),
            "payload_sha256": str(envelope["payload_sha256"]),
            "fingerprint": envelope["fingerprint"],
        }
        aad = SNAPSHOT_AAD + b"\x00" + _canonical_bytes(authenticated_metadata)
        nonce = _b64decode(str(envelope["nonce"]))
        ciphertext = _b64decode(str(envelope["ciphertext"]))
        plaintext = AESGCM(_snapshot_key(recovery_secret)).decrypt(nonce, ciphertext, aad)
        if hashlib.sha256(plaintext).hexdigest() != str(envelope["payload_sha256"]):
            raise ValueError("snapshot payload digest mismatch")
        snapshot = json.loads(plaintext)
    except Exception as exc:  # noqa: BLE001 - normalize to a non-secret error
        raise ValueError("Meta registry snapshot authentication failed") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("Meta registry snapshot payload is invalid")
    if registry_tables_fingerprint(snapshot) != envelope.get("fingerprint"):
        raise ValueError("Meta registry snapshot fingerprint mismatch")
    return snapshot


def write_encrypted_snapshot(path: Path, snapshot: dict[str, Any], *, recovery_secret: str) -> None:
    """Atomically create a new protected snapshot; never overwrite an old one."""

    path = Path(os.path.abspath(os.fspath(path)))
    _secure_parent(path)
    envelope = encode_encrypted_snapshot(snapshot, recovery_secret=recovery_secret)
    fd, temporary_name = tempfile.mkstemp(prefix=".meta-registry-snapshot-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # link() provides no-clobber atomic publication in the same directory.
        os.link(temporary, path, follow_symlinks=False)
        _secure_file_info(path, label="created snapshot")
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_encrypted_snapshot(path: Path, *, recovery_secret: str) -> dict[str, Any]:
    path = Path(os.path.abspath(os.fspath(path)))
    before = _secure_file_info(path, label="snapshot")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("snapshot changed while it was opened")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as handle:
            envelope = json.load(handle)
    finally:
        os.close(fd)
    return decode_encrypted_snapshot(envelope, recovery_secret=recovery_secret)


def load_master_secret_from_env_file(path: Path) -> str:
    """Load only the master key from a canonical root:root 0600 env file."""

    from dotenv import dotenv_values

    from scripts.ha.meta_env_file import require_secure_env_file

    path = Path(os.path.abspath(os.fspath(path)))
    require_secure_env_file(path)
    secret = str(dotenv_values(path, interpolate=False).get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("key env file has no valid Meta credential encryption key")
    return secret


def load_snapshot_recovery_key(path: Path) -> str:
    """Load a single-purpose recovery key that is independent of runtime."""

    from dotenv import dotenv_values

    from scripts.ha.meta_env_file import require_secure_env_file

    path = Path(os.path.abspath(os.fspath(path)))
    require_secure_env_file(path)
    values = {
        str(key): str(value) for key, value in dotenv_values(path, interpolate=False).items() if value is not None
    }
    if set(values) != {"CREDENTIAL_REKEY_RECOVERY_KEY"}:
        raise RuntimeError("snapshot recovery file must contain only CREDENTIAL_REKEY_RECOVERY_KEY")
    secret = values["CREDENTIAL_REKEY_RECOVERY_KEY"].strip()
    if len(secret) < 32:
        raise RuntimeError("snapshot recovery key is invalid")
    return secret


def load_runtime_environment(path: Path, *, require_postgres_backend: bool = True) -> str:
    """Load only the DB controls and master key from one secure env file."""

    from dotenv import dotenv_values

    from scripts.ha.meta_env_file import require_secure_env_file

    path = Path(os.path.abspath(os.fspath(path)))
    require_secure_env_file(path)
    values = dotenv_values(path, interpolate=False)
    backend = str(values.get("META_REGISTRY_BACKEND") or "").strip().lower()
    if require_postgres_backend and backend != "postgres":
        raise RuntimeError("canonical environment must explicitly select Postgres registry authority")
    if not (values.get("LINAS_WHATSAPP_DATABASE_URL") or values.get("DATABASE_URL")):
        raise RuntimeError("canonical environment has no registry Postgres DSN")
    allowed = {
        "META_REGISTRY_BACKEND",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "LINAS_WHATSAPP_DATABASE_URL",
        "DATABASE_URL",
        "LINAS_WHATSAPP_REQUIRE_SSL",
        "LINAS_WHATSAPP_DB_SSLMODE",
        "LINAS_WHATSAPP_DB_POOL_SIZE",
        "LINAS_WHATSAPP_DB_MAX_OVERFLOW",
    }
    for key in allowed:
        os.environ.pop(key, None)
    for key in allowed:
        value = values.get(key)
        if value is not None:
            os.environ[key] = str(value)
    secret = str(values.get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("canonical environment has no valid Meta credential encryption key")
    return secret


def restore_confirmation_token(snapshot_sha256: str) -> str:
    return f"RESTORE_META_REGISTRY_{snapshot_sha256[:16].upper()}"


def _print_fingerprint(prefix: str, fingerprint: dict[str, Any]) -> None:
    print(
        f"{prefix} bindings={fingerprint['binding_count']} credentials={fingerprint['credential_count']} "
        f"oauth={fingerprint['oauth_count']} audit={fingerprint['audit_count']} "
        f"sha256={fingerprint['tables_sha256']}"
    )


def _validate_snapshot_contents(snapshot: dict[str, Any], master_secret: str) -> None:
    from scripts.ha.verify_meta_registry_postgres import (
        validate_credential_decryption,
        validate_state_invariants,
    )

    if snapshot.get("format_version") != 1 or not isinstance(snapshot.get("audit_events"), list):
        raise ValueError("snapshot table structure is invalid")
    state = snapshot.get("state")
    if not isinstance(state, dict):
        raise ValueError("snapshot registry state is invalid")
    issues = validate_state_invariants(state)
    issues.extend(validate_credential_decryption(state, master_secret))
    for raw in snapshot["audit_events"]:
        if not isinstance(raw, dict) or not str(raw.get("id") or "") or not str(raw.get("event") or ""):
            issues.append("audit_row_invalid")
    if issues:
        raise ValueError("snapshot failed structural or credential verification")


def _default_pre_restore_path(source: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return source.with_name(f"{source.name}.pre-restore-{timestamp}.enc")


def _snapshot_command(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session
    from services.meta_app_registry_pg_store import (
        acquire_registry_advisory_lock,
        load_registry_tables_snapshot,
        registry_tables_fingerprint,
    )

    with whatsapp_session(require=True) as session:
        acquire_registry_advisory_lock(session)
        snapshot = load_registry_tables_snapshot(session)
        _validate_snapshot_contents(snapshot, args.current_master_secret)
        fingerprint = registry_tables_fingerprint(snapshot)
        _print_fingerprint("current", fingerprint)
        if not args.apply:
            print(f"DRY-RUN: would atomically create encrypted snapshot at {args.path.resolve()}")
            return 0
        write_encrypted_snapshot(args.path, snapshot, recovery_secret=args.snapshot_recovery_secret)
        verified = registry_tables_fingerprint(
            read_encrypted_snapshot(args.path, recovery_secret=args.snapshot_recovery_secret)
        )
        if verified != fingerprint:
            raise RuntimeError("created snapshot verification failed")
        _print_fingerprint("snapshot-verified", verified)
    return 0


def _verify_command(args: argparse.Namespace) -> int:
    from services.meta_app_registry_pg_store import registry_tables_fingerprint

    snapshot = read_encrypted_snapshot(args.path, recovery_secret=args.snapshot_recovery_secret)
    _validate_snapshot_contents(snapshot, args.snapshot_master_secret)
    fingerprint = registry_tables_fingerprint(snapshot)
    _print_fingerprint("snapshot-valid", fingerprint)
    if not args.against_current:
        return 0

    from db.session import whatsapp_session
    from services.meta_app_registry_pg_store import acquire_registry_advisory_lock, load_registry_tables_snapshot

    with whatsapp_session(require=True) as session:
        acquire_registry_advisory_lock(session)
        current_snapshot = load_registry_tables_snapshot(session)
        _validate_snapshot_contents(current_snapshot, args.current_master_secret)
        current = registry_tables_fingerprint(current_snapshot)
    _print_fingerprint("current", current)
    if current != fingerprint:
        print("MISMATCH: snapshot and current four-table state differ", file=sys.stderr)
        return 3
    print("OK: snapshot exactly matches current four-table state")
    return 0


def _restore_command(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session
    from services.meta_app_registry_pg_store import (
        acquire_registry_advisory_lock,
        load_registry_tables_snapshot,
        registry_tables_fingerprint,
        replace_registry_tables_snapshot,
    )

    desired_snapshot = read_encrypted_snapshot(args.path, recovery_secret=args.snapshot_recovery_secret)
    _validate_snapshot_contents(desired_snapshot, args.snapshot_master_secret)
    desired_fp = registry_tables_fingerprint(desired_snapshot)
    _print_fingerprint("restore-source", desired_fp)
    token = restore_confirmation_token(desired_fp["tables_sha256"])

    with whatsapp_session(require=True) as session:
        acquire_registry_advisory_lock(session)
        current_snapshot = load_registry_tables_snapshot(session)
        _validate_snapshot_contents(current_snapshot, args.current_master_secret)
        current_fp = registry_tables_fingerprint(current_snapshot)
        _print_fingerprint("current", current_fp)
        if not args.apply:
            print(f"DRY-RUN: required confirmation token is {token}")
            print(
                f"DRY-RUN: automatic pre-restore snapshot path is {(args.pre_restore or _default_pre_restore_path(args.path)).resolve()}"
            )
            return 0

        expected = str(args.expected_current_sha256 or "").strip().lower()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise ValueError("--expected-current-sha256 is required for restore")
        if current_fp["tables_sha256"] != expected:
            raise RuntimeError("current target changed after operator preflight")
        if args.confirm != token:
            raise PermissionError("restore confirmation token is missing or incorrect")
        if current_fp == desired_fp:
            print("OK: current tables already match snapshot; no restore performed")
            return 0

        pre_restore = Path(os.path.abspath(os.fspath(args.pre_restore or _default_pre_restore_path(args.path))))
        write_encrypted_snapshot(
            pre_restore,
            current_snapshot,
            recovery_secret=args.snapshot_recovery_secret,
        )
        backup_fp = registry_tables_fingerprint(
            read_encrypted_snapshot(pre_restore, recovery_secret=args.snapshot_recovery_secret)
        )
        if backup_fp != current_fp:
            raise RuntimeError("automatic pre-restore snapshot verification failed")
        _print_fingerprint("pre-restore-backup-verified", backup_fp)

        replace_registry_tables_snapshot(session, desired_snapshot)
        session.flush()
        restored_snapshot = load_registry_tables_snapshot(session)
        _validate_snapshot_contents(restored_snapshot, args.current_master_secret)
        restored_fp = registry_tables_fingerprint(restored_snapshot)
        if restored_fp != desired_fp:
            raise RuntimeError("restored database verification failed; transaction will roll back")
        _print_fingerprint("restore-verified", restored_fp)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot = commands.add_parser("snapshot", help="create an encrypted four-table snapshot")
    snapshot.add_argument("path", type=Path)
    snapshot.add_argument("--apply", action="store_true", help="write snapshot (default: dry-run)")
    snapshot.add_argument("--env-file", type=Path, required=True)
    snapshot.add_argument("--recovery-key-file", type=Path, required=True)

    verify = commands.add_parser("verify", help="authenticate and deeply verify a snapshot")
    verify.add_argument("path", type=Path)
    verify.add_argument("--against-current", action="store_true")
    verify.add_argument("--env-file", type=Path, required=True)
    verify.add_argument("--key-env-file", type=Path, default=None)
    verify.add_argument("--recovery-key-file", type=Path, required=True)

    restore = commands.add_parser("restore", help="CAS-guarded transactional restore/rollback")
    restore.add_argument("path", type=Path)
    restore.add_argument(
        "--apply",
        action="store_true",
        help="blocked pending a reviewed two-node coordinator (default: dry-run)",
    )
    restore.add_argument("--expected-release-sha", default="", help="exact deployed release required for --apply")
    restore.add_argument("--expected-current-sha256", default="")
    restore.add_argument("--confirm", default="")
    restore.add_argument("--pre-restore", type=Path, default=None)
    restore.add_argument("--env-file", type=Path, required=True)
    restore.add_argument("--key-env-file", type=Path, default=None)
    restore.add_argument("--recovery-key-file", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mutation_lock_fd: int | None = None
    try:
        _require_root()
        if args.command == "restore" and args.apply:
            from scripts.ha.production_mutation_guard import acquire_direct_production_mutation_lock

            mutation_lock_fd = acquire_direct_production_mutation_lock(
                expected_sha=args.expected_release_sha,
                script="scripts/ha/meta_registry_pg_snapshot.py",
                env_path=Path(os.path.abspath(os.fspath(args.env_file))),
            )
            print(
                "BLOCKED: direct registry restore requires a signed, current, both-node-drained coordinator",
                file=sys.stderr,
            )
            raise PermissionError(
                "restore --apply requires a reviewed two-node release/env/drain coordinator; direct restore is disabled"
            )
        args.current_master_secret = load_runtime_environment(args.env_file)
        key_env_file = getattr(args, "key_env_file", None)
        args.snapshot_master_secret = (
            load_master_secret_from_env_file(key_env_file) if key_env_file is not None else args.current_master_secret
        )
        args.snapshot_recovery_secret = load_snapshot_recovery_key(args.recovery_key_file)
        if hmac.compare_digest(args.snapshot_recovery_secret, args.current_master_secret) or hmac.compare_digest(
            args.snapshot_recovery_secret,
            args.snapshot_master_secret,
        ):
            raise PermissionError("snapshot recovery key must be independent from every runtime master key")
        if args.command == "restore" and not hmac.compare_digest(
            args.snapshot_master_secret,
            args.current_master_secret,
        ):
            raise PermissionError(
                "pre-rotation snapshot restore requires the separately reviewed cross-product rekey procedure"
            )
        if args.command == "snapshot":
            return _snapshot_command(args)
        if args.command == "verify":
            return _verify_command(args)
        if args.command == "restore":
            return _restore_command(args)
        raise ValueError("unknown command")
    except Exception as exc:  # noqa: BLE001 - never serialize DB rows or secret-bearing values
        print(f"ERROR: Meta registry snapshot operation failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    finally:
        if mutation_lock_fd is not None:
            os.close(mutation_lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
