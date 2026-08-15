#!/usr/bin/env python3
"""Read-only, secret-safe verification of Postgres Meta registry authority.

Checks deep table fingerprints and referential/domain invariants.  If the legacy
NFS registry exists it is read under its normal file lock and classified as
matching or stale without printing any identifiers or stored values.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_store() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT) / "meta_registry" / "registry.json"


def _validate_digest(value: str) -> str:
    digest = str(value or "").strip().lower()
    if digest and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
        raise ValueError("expected digest must be lowercase SHA-256")
    return digest


def _is_valid_credentialless_tombstone(raw: dict[str, Any]) -> bool:
    try:
        generation = int(raw.get("generation") or 0)
        created_at = float(raw.get("created_at") or 0)
        updated_at = float(raw.get("updated_at") or 0)
    except (TypeError, ValueError):
        return False
    return bool(
        raw.get("status") == "disconnected"
        and generation >= 2
        and created_at > 0
        and updated_at >= created_at
        and str(raw.get("binding_id") or "").strip()
        and str(raw.get("tenant_id") or "").strip()
        and str(raw.get("credential_id") or "").strip()
        and raw.get("channel") in {"facebook", "instagram"}
        and str(raw.get("asset_id") or "").strip()
        and str(raw.get("app_key") or "").strip()
        and raw.get("auth_flow", "facebook_login") in {"facebook_login", "instagram_login"}
        and re.fullmatch(r"[0-9a-f]{16}", str(raw.get("authorized_meta_user_id_hash") or ""))
    )


def validate_state_invariants(state: dict[str, Any]) -> list[str]:
    """Return safe issue codes only; never include row keys or values."""

    issues: list[str] = []
    bindings = state.get("bindings")
    credentials = state.get("credentials")
    oauth_states = state.get("oauth_states")
    if state.get("schema_version") != 1:
        issues.append("schema_version_invalid")
    if not isinstance(bindings, dict) or not isinstance(credentials, dict) or not isinstance(oauth_states, dict):
        return [*issues, "state_structure_invalid"]

    active_keys: set[tuple[str, ...]] = set()
    for binding_key, raw in bindings.items():
        if not isinstance(raw, dict):
            issues.append("binding_row_invalid")
            continue
        if str(raw.get("binding_id") or "") != str(binding_key):
            issues.append("binding_primary_key_mismatch")
        channel = str(raw.get("channel") or "")
        status = str(raw.get("status") or "")
        auth_flow = str(raw.get("auth_flow") or "facebook_login")
        if channel not in {"facebook", "instagram"}:
            issues.append("binding_channel_invalid")
        if status not in {"active", "inactive", "testing", "disconnected"}:
            issues.append("binding_status_invalid")
        if auth_flow not in {"facebook_login", "instagram_login"}:
            issues.append("binding_auth_flow_invalid")
        try:
            if int(raw.get("generation") or 0) < 1:
                issues.append("binding_generation_invalid")
        except (TypeError, ValueError):
            issues.append("binding_generation_invalid")
        credential_id = str(raw.get("credential_id") or "")
        credential = credentials.get(credential_id)
        if not isinstance(credential, dict):
            if not _is_valid_credentialless_tombstone(raw):
                issues.append("binding_credential_missing")
        elif str(credential.get("binding_id") or "") != str(binding_key):
            issues.append("binding_credential_owner_mismatch")
        if status == "active":
            asset = str(raw.get("asset_id") or "")
            exclusive = (channel, asset) if channel == "facebook" else (channel, auth_flow, asset)
            if not asset or exclusive in active_keys:
                issues.append("active_asset_not_exclusive")
            active_keys.add(exclusive)

    for credential_key, raw in credentials.items():
        if not isinstance(raw, dict):
            issues.append("credential_row_invalid")
            continue
        binding_id = str(raw.get("binding_id") or "")
        owner = bindings.get(binding_id)
        if not isinstance(owner, dict):
            issues.append("credential_binding_missing")
        elif str(owner.get("credential_id") or "") != str(credential_key):
            issues.append("credential_binding_lineage_mismatch")
        if not str(credential_key) or not str(raw.get("sealed") or "").startswith("v1."):
            issues.append("credential_envelope_invalid")
        aad = str(raw.get("aad") or "")
        if not aad.startswith(f"{binding_id}:{credential_key}:"):
            issues.append("credential_aad_mismatch")

    for nonce, raw in oauth_states.items():
        if not str(nonce) or not isinstance(raw, dict):
            issues.append("oauth_state_invalid")
            continue
        try:
            float(raw.get("expires_at") or 0)
        except (TypeError, ValueError):
            issues.append("oauth_expiry_invalid")
    return sorted(set(issues))


def validate_credential_decryption(state: dict[str, Any], master_secret: str) -> list[str]:
    """Prove every credential opens with the canonical key; return safe codes."""

    from services.meta_app_registry_common import MetaCredentialCipher, MetaCredentialError

    credentials = state.get("credentials")
    if not isinstance(credentials, dict):
        return ["credential_structure_invalid"]
    try:
        cipher = MetaCredentialCipher(master_secret)
    except Exception:  # noqa: BLE001 - safe issue code only
        return ["credential_master_key_invalid"]
    issues: list[str] = []
    for raw in credentials.values():
        if not isinstance(raw, dict):
            continue
        try:
            opened = cipher.open(str(raw.get("sealed") or ""), aad=str(raw.get("aad") or ""))
            if not str(opened.get("access_token") or "").strip():
                issues.append("credential_plaintext_invalid")
        except MetaCredentialError:
            issues.append("credential_decryption_failed")
    return sorted(set(issues))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=None, help="legacy root:root 0600 registry.json")
    parser.add_argument("--env-file", type=Path, default=None, help="secure canonical runtime env file")
    parser.add_argument("--expected-pg-sha256", default="", help="optional state digest CAS")
    parser.add_argument("--require-file-parity", action="store_true", help="fail if legacy file is absent/stale")
    parser.add_argument(
        "--allow-non-postgres-backend",
        action="store_true",
        help="diagnostic only; default requires effective backend exactly postgres",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Path(os.path.abspath(os.fspath(args.store or _default_store())))
    try:
        expected = _validate_digest(args.expected_pg_sha256)
        if args.env_file is not None:
            from scripts.ha.meta_registry_pg_snapshot import load_runtime_environment

            load_runtime_environment(
                args.env_file,
                require_postgres_backend=not args.allow_non_postgres_backend,
            )
        from services.meta_app_registry_backend import resolve_meta_registry_backend

        backend = resolve_meta_registry_backend()
        if backend != "postgres" and not args.allow_non_postgres_backend:
            raise RuntimeError("effective Meta registry backend is not exactly postgres")

        from db.session import whatsapp_session
        from services.meta_app_registry_pg_store import (
            acquire_registry_advisory_lock,
            load_registry_tables_snapshot,
            registry_tables_fingerprint,
        )

        with whatsapp_session(require=True) as session:
            acquire_registry_advisory_lock(session)
            pg_snapshot = load_registry_tables_snapshot(session)
            pg_fp = registry_tables_fingerprint(pg_snapshot)
            issues = validate_state_invariants(pg_snapshot["state"])
            master_secret = (os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
            issues.extend(validate_credential_decryption(pg_snapshot["state"], master_secret))
            issues = sorted(set(issues))
        print(
            "postgres "
            f"bindings={pg_fp['binding_count']} credentials={pg_fp['credential_count']} "
            f"oauth={pg_fp['oauth_count']} audit={pg_fp['audit_count']} "
            f"state_sha256={pg_fp['state_sha256']} tables_sha256={pg_fp['tables_sha256']}"
        )
        if issues:
            print(f"ERROR: invariant failures={','.join(issues)}", file=sys.stderr)
            return 2
        if expected and pg_fp["state_sha256"] != expected:
            print("ERROR: Postgres state digest differs from expected CAS", file=sys.stderr)
            return 3

        if store.exists() or store.is_symlink():
            from scripts.ha.import_meta_registry_to_postgres import (
                _locked_registry_source,
                _normalize_file_state_for_postgres,
            )
            from services.meta_app_registry_pg_store import state_fingerprint

            with _locked_registry_source(store) as (file_state, _source_info):
                file_fp = state_fingerprint(_normalize_file_state_for_postgres(file_state))
            relation = (
                "matching"
                if file_fp
                == {
                    key: pg_fp[key]
                    for key in (
                        "schema_version",
                        "binding_count",
                        "credential_count",
                        "oauth_count",
                        "bindings_sha256",
                        "credentials_sha256",
                        "oauth_sha256",
                        "state_sha256",
                    )
                }
                else "stale"
            )
            print(
                "legacy-file "
                f"status={relation} bindings={file_fp['binding_count']} credentials={file_fp['credential_count']} "
                f"oauth={file_fp['oauth_count']} state_sha256={file_fp['state_sha256']}"
            )
            if relation != "matching" and args.require_file_parity:
                return 4
        else:
            print("legacy-file status=absent")
            if args.require_file_parity:
                return 4
        print("OK: Postgres Meta registry authority and invariants verified")
        return 0
    except Exception as exc:  # noqa: BLE001 - never serialize DB/secret-bearing exception text
        print(f"ERROR: registry verification failed ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
