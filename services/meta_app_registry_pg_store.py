"""Load/save Meta registry state dict via SQLAlchemy (Postgres SoT).

Maps bindings / credentials / oauth_states ↔ rows. Preserves sealed ciphertext
as-is. Fail closed — callers must not fall back to file when this store is selected.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.meta_registry import (
    MetaAssetBindingRow,
    MetaBindingCredentialRow,
    MetaOAuthStateRow,
    MetaRegistryAuditEvent,
)
from services.meta_app_registry_common import REGISTRY_SCHEMA_VERSION, MetaBindingConflictError, MetaRegistryError

# Stable transaction-scoped advisory lock key for multi-node registry mutations
# (Postgres only).  The lock must live through the caller's commit/rollback: a
# session-scoped lock released before ``whatsapp_session`` commits permits a
# concurrent writer to commit between the unlock and the first writer's commit.
META_REGISTRY_ADVISORY_LOCK_KEY = 0x4D455441_52454731  # META REG1


def acquire_registry_advisory_lock(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": META_REGISTRY_ADVISORY_LOCK_KEY},
        )


def release_registry_advisory_lock(_session: Session) -> None:
    """Compatibility no-op; PostgreSQL releases this lock at transaction end.

    Keeping this function lets existing callers retain their ``finally`` blocks
    without introducing an early unlock before the surrounding session commits.
    """


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "bindings": {},
        "credentials": {},
        "oauth_states": {},
    }


def _binding_row_to_dict(row: MetaAssetBindingRow) -> dict[str, Any]:
    fields = row.webhook_subscribed_fields or []
    return {
        "binding_id": row.binding_id,
        "tenant_id": row.tenant_id,
        "channel": row.channel,
        "asset_id": row.asset_id,
        "page_id": row.page_id or "",
        "instagram_account_id": row.instagram_account_id or "",
        "app_key": row.app_key,
        "credential_id": row.credential_id,
        "status": row.status,
        "generation": int(row.generation or 1),
        "created_at": float(row.created_at or 0),
        "updated_at": float(row.updated_at or 0),
        "previous_binding_id": row.previous_binding_id or "",
        "page_name": row.page_name or "",
        "instagram_username": row.instagram_username or "",
        "authorized_meta_user_id_hash": row.authorized_meta_user_id_hash or "",
        "superseded_by_binding_id": row.superseded_by_binding_id or "",
        "auth_flow": row.auth_flow or "facebook_login",
        "webhook_subscription_status": row.webhook_subscription_status or "unknown",
        "webhook_subscribed_fields": list(fields),
        "webhook_subscription_error": row.webhook_subscription_error or "",
        "webhook_subscription_checked_at": float(row.webhook_subscription_checked_at or 0),
    }


def load_state(session: Session) -> dict[str, Any]:
    """Load full registry state dict from Postgres."""

    state = empty_state()
    try:
        for binding_row in session.scalars(select(MetaAssetBindingRow)).all():
            state["bindings"][binding_row.binding_id] = _binding_row_to_dict(binding_row)
        for cred_row in session.scalars(select(MetaBindingCredentialRow)).all():
            state["credentials"][cred_row.credential_id] = {
                "binding_id": cred_row.binding_id,
                "aad": cred_row.aad,
                "sealed": cred_row.sealed,
                "created_at": float(cred_row.created_at or 0),
                "archived_at": float(getattr(cred_row, "archived_at", 0) or 0),
            }
        for oauth_row in session.scalars(select(MetaOAuthStateRow)).all():
            payload = dict(oauth_row.payload or {})
            if "expires_at" not in payload:
                payload["expires_at"] = float(oauth_row.expires_at or 0)
            state["oauth_states"][oauth_row.nonce] = payload
    except Exception as exc:  # noqa: BLE001 — fail closed for SoT
        raise MetaRegistryError("Meta registry Postgres store is unreadable") from exc
    return state


def save_state(session: Session, state: dict[str, Any]) -> None:
    """Replace bindings/credentials/oauth_states to match ``state`` (transactional)."""

    if not isinstance(state, dict) or state.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise MetaRegistryError("Meta registry schema is invalid")
    for key in ("bindings", "credentials", "oauth_states"):
        if not isinstance(state.get(key), dict):
            raise MetaRegistryError("Meta registry structure is invalid")

    try:
        # Credentials reference bindings — clear children first.
        session.execute(delete(MetaBindingCredentialRow))
        session.execute(delete(MetaOAuthStateRow))
        session.execute(delete(MetaAssetBindingRow))
        session.flush()

        for binding_id, raw in state["bindings"].items():
            if not isinstance(raw, dict):
                raise MetaRegistryError("Meta registry binding row is invalid")
            fields = raw.get("webhook_subscribed_fields") or []
            session.add(
                MetaAssetBindingRow(
                    binding_id=str(raw.get("binding_id") or binding_id),
                    tenant_id=str(raw["tenant_id"]),
                    channel=str(raw["channel"]),
                    asset_id=str(raw["asset_id"]),
                    page_id=str(raw.get("page_id") or ""),
                    instagram_account_id=str(raw.get("instagram_account_id") or ""),
                    app_key=str(raw["app_key"]),
                    credential_id=str(raw["credential_id"]),
                    status=str(raw["status"]),
                    generation=int(raw.get("generation") or 1),
                    created_at=float(raw.get("created_at") or 0),
                    updated_at=float(raw.get("updated_at") or 0),
                    previous_binding_id=str(raw.get("previous_binding_id") or ""),
                    page_name=str(raw.get("page_name") or ""),
                    instagram_username=str(raw.get("instagram_username") or ""),
                    authorized_meta_user_id_hash=str(raw.get("authorized_meta_user_id_hash") or ""),
                    superseded_by_binding_id=str(raw.get("superseded_by_binding_id") or ""),
                    auth_flow=str(raw.get("auth_flow") or "facebook_login"),
                    webhook_subscription_status=str(raw.get("webhook_subscription_status") or "unknown"),
                    webhook_subscribed_fields=list(fields),
                    webhook_subscription_error=str(raw.get("webhook_subscription_error") or ""),
                    webhook_subscription_checked_at=float(raw.get("webhook_subscription_checked_at") or 0),
                )
            )
        session.flush()

        for credential_id, raw in state["credentials"].items():
            if not isinstance(raw, dict):
                raise MetaRegistryError("Meta registry credential row is invalid")
            session.add(
                MetaBindingCredentialRow(
                    credential_id=str(credential_id),
                    binding_id=str(raw["binding_id"]),
                    sealed=str(raw["sealed"]),
                    aad=str(raw["aad"]),
                    created_at=float(raw.get("created_at") or 0),
                    archived_at=float(raw.get("archived_at") or 0),
                )
            )

        for nonce, raw in state["oauth_states"].items():
            if not isinstance(raw, dict):
                raise MetaRegistryError("Meta registry oauth state is invalid")
            payload = dict(raw)
            session.add(
                MetaOAuthStateRow(
                    nonce=str(nonce),
                    payload=payload,
                    expires_at=float(payload.get("expires_at") or 0),
                )
            )
        session.flush()
    except IntegrityError as exc:
        raise MetaBindingConflictError("asset is already active for another workspace") from exc
    except MetaRegistryError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed
        raise MetaRegistryError("Meta registry Postgres store could not be written") from exc


def append_audit_event(session: Session, safe_event: dict[str, Any]) -> None:
    """Persist one redacted audit row (fields match file audit.jsonl)."""

    session.add(
        MetaRegistryAuditEvent(
            id=str(uuid.uuid4()),
            timestamp=float(safe_event.get("timestamp") or 0),
            event=str(safe_event.get("event") or "unknown"),
            actor_id_hash=str(safe_event.get("actor_id_hash") or ""),
            tenant_id=str(safe_event.get("tenant_id") or ""),
            channel=str(safe_event.get("channel") or ""),
            asset_id_hash=str(safe_event.get("asset_id_hash") or ""),
            app_key=str(safe_event.get("app_key") or ""),
            binding_id=str(safe_event.get("binding_id") or ""),
            result=str(safe_event.get("result") or "ok"),
        )
    )


def _canonical_sha256(value: Any) -> str:
    """Return a deterministic digest without returning any registry identifiers.

    The digest deliberately covers ciphertext and every persisted field.  It is
    safe to log, unlike the former sorted-ID fingerprint, but it must still be
    treated as a comparison token rather than proof that the plaintext is valid.
    """

    try:
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MetaRegistryError("Meta registry state is not canonically serializable") from exc
    return hashlib.sha256(payload).hexdigest()


def state_fingerprint(state: dict[str, Any]) -> dict[str, Any]:
    """Return secret-safe counts and deep canonical hashes for registry state.

    No raw binding, credential, OAuth, tenant, Page, or Instagram identifiers are
    included.  Every field (including generations, ciphertext and OAuth payloads)
    contributes to the section and whole-state digests.
    """

    bindings_raw = state.get("bindings")
    credentials_raw = state.get("credentials")
    oauth_raw = state.get("oauth_states")
    bindings: dict[str, Any] = bindings_raw if isinstance(bindings_raw, dict) else {}
    credentials: dict[str, Any] = credentials_raw if isinstance(credentials_raw, dict) else {}
    oauth_states: dict[str, Any] = oauth_raw if isinstance(oauth_raw, dict) else {}
    canonical_state = {
        "schema_version": state.get("schema_version"),
        "bindings": bindings,
        "credentials": credentials,
        "oauth_states": oauth_states,
    }
    return {
        "schema_version": state.get("schema_version"),
        "binding_count": len(bindings),
        "credential_count": len(credentials),
        "oauth_count": len(oauth_states),
        "bindings_sha256": _canonical_sha256(bindings),
        "credentials_sha256": _canonical_sha256(credentials),
        "oauth_sha256": _canonical_sha256(oauth_states),
        "state_sha256": _canonical_sha256(canonical_state),
    }


def load_registry_tables_snapshot(session: Session) -> dict[str, Any]:
    """Load all four Meta registry tables for encrypted operator snapshots."""

    state = load_state(session)
    try:
        audit_events = [
            {
                "id": row.id,
                "timestamp": float(row.timestamp or 0),
                "event": row.event,
                "actor_id_hash": row.actor_id_hash or "",
                "tenant_id": row.tenant_id or "",
                "channel": row.channel or "",
                "asset_id_hash": row.asset_id_hash or "",
                "app_key": row.app_key or "",
                "binding_id": row.binding_id or "",
                "result": row.result or "ok",
            }
            for row in session.scalars(select(MetaRegistryAuditEvent)).all()
        ]
    except Exception as exc:  # noqa: BLE001 - fail closed for backup material
        raise MetaRegistryError("Meta registry audit table is unreadable") from exc
    audit_events.sort(key=lambda item: str(item.get("id") or ""))
    return {
        "format_version": 1,
        "state": state,
        "audit_events": audit_events,
    }


def registry_tables_fingerprint(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Deep fingerprint all four registry tables without exposing row identifiers."""

    state = snapshot.get("state")
    audits = snapshot.get("audit_events")
    if not isinstance(state, dict) or not isinstance(audits, list):
        raise MetaRegistryError("Meta registry table snapshot is invalid")
    state_fp = state_fingerprint(state)
    return {
        **state_fp,
        "audit_count": len(audits),
        "audit_sha256": _canonical_sha256(audits),
        "tables_sha256": _canonical_sha256(
            {
                "format_version": snapshot.get("format_version"),
                "state": state,
                "audit_events": audits,
            }
        ),
    }


def replace_registry_tables_snapshot(session: Session, snapshot: dict[str, Any]) -> None:
    """Transactionally replace the four registry tables from a verified snapshot."""

    state = snapshot.get("state")
    audits = snapshot.get("audit_events")
    if snapshot.get("format_version") != 1 or not isinstance(state, dict) or not isinstance(audits, list):
        raise MetaRegistryError("Meta registry table snapshot is invalid")
    save_state(session, state)
    try:
        session.execute(delete(MetaRegistryAuditEvent))
        for raw in audits:
            if not isinstance(raw, dict):
                raise MetaRegistryError("Meta registry audit snapshot row is invalid")
            session.add(
                MetaRegistryAuditEvent(
                    id=str(raw["id"]),
                    timestamp=float(raw.get("timestamp") or 0),
                    event=str(raw.get("event") or "unknown"),
                    actor_id_hash=str(raw.get("actor_id_hash") or ""),
                    tenant_id=str(raw.get("tenant_id") or ""),
                    channel=str(raw.get("channel") or ""),
                    asset_id_hash=str(raw.get("asset_id_hash") or ""),
                    app_key=str(raw.get("app_key") or ""),
                    binding_id=str(raw.get("binding_id") or ""),
                    result=str(raw.get("result") or "ok"),
                )
            )
        session.flush()
    except MetaRegistryError:
        raise
    except Exception as exc:  # noqa: BLE001 - surrounding transaction rolls back
        raise MetaRegistryError("Meta registry audit snapshot could not be restored") from exc
