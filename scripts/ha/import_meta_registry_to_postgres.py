#!/usr/bin/env python3
"""Import file-backed meta_registry JSON into Postgres (idempotent).

Reads registry.json under fcntl lock, upserts full state into Postgres via the
meta registry PG store, then verifies binding/credential/oauth counts and ids.
Exits non-zero on mismatch. Does not change META_REGISTRY_BACKEND.

Usage:
  python scripts/ha/import_meta_registry_to_postgres.py [--store PATH]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_store() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT) / "meta_registry" / "registry.json"


def _read_registry_locked(store_path: Path) -> dict:
    lock_path = store_path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(mode=0o600, exist_ok=True)
    os.chmod(lock_path, 0o600)
    with lock_path.open("r+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            if not store_path.exists():
                return {
                    "schema_version": 1,
                    "bindings": {},
                    "credentials": {},
                    "oauth_states": {},
                }
            raw = json.loads(store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise SystemExit(f"registry is not an object: {store_path}")
            return raw
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Path to registry.json (default: $DATA_ROOT/meta_registry/registry.json)",
    )
    args = parser.parse_args(argv)
    store_path = args.store or _default_store()

    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    from services.meta_app_registry_pg_store import load_state, save_state, state_fingerprint

    file_state = _read_registry_locked(store_path)
    file_fp = state_fingerprint(file_state)
    print(
        f"file store={store_path} bindings={file_fp['binding_count']} "
        f"credentials={file_fp['credential_count']} oauth={file_fp['oauth_count']}"
    )

    try:
        with whatsapp_session(require=True) as session:
            save_state(session, file_state)
            pg_state = load_state(session)
            pg_fp = state_fingerprint(pg_state)
    except WhatsAppDatabaseUnavailable as exc:
        print(f"ERROR: Postgres unavailable: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(
        f"postgres bindings={pg_fp['binding_count']} "
        f"credentials={pg_fp['credential_count']} oauth={pg_fp['oauth_count']}"
    )
    if pg_fp != file_fp:
        print("ERROR: post-import fingerprint mismatch", file=sys.stderr)
        print(f"  file={file_fp}", file=sys.stderr)
        print(f"  pg={pg_fp}", file=sys.stderr)
        return 1
    print("OK: import verified (counts + binding/credential/oauth ids match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
