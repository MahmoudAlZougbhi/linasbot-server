"""Load/save Meta registry state dict via SQLAlchemy (Postgres SoT).

Maps bindings / credentials / oauth_states ↔ rows. Preserves sealed ciphertext
as-is. Fail closed — callers must not fall back to file when this store is selected.
"""

from __future__ import annotations

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

# Stable advisory lock key for multi-node registry mutations (Postgres only).
META_REGISTRY_ADVISORY_LOCK_KEY = 0x4D455441_52454731  # META REG1


def acquire_registry_advisory_lock(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_lock(:k)"),
            {"k": META_REGISTRY_ADVISORY_LOCK_KEY},
        )


def release_registry_advisory_lock(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": META_REGISTRY_ADVISORY_LOCK_KEY},
        )


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


def state_fingerprint(state: dict[str, Any]) -> dict[str, Any]:
    """Counts + sorted ids for import verification / dual-read mismatch checks."""

    bindings_raw = state.get("bindings")
    credentials_raw = state.get("credentials")
    oauth_raw = state.get("oauth_states")
    bindings: dict[str, Any] = bindings_raw if isinstance(bindings_raw, dict) else {}
    credentials: dict[str, Any] = credentials_raw if isinstance(credentials_raw, dict) else {}
    oauth_states: dict[str, Any] = oauth_raw if isinstance(oauth_raw, dict) else {}
    return {
        "binding_count": len(bindings),
        "credential_count": len(credentials),
        "oauth_count": len(oauth_states),
        "binding_ids": sorted(str(k) for k in bindings.keys()),
        "credential_ids": sorted(str(k) for k in credentials.keys()),
        "oauth_keys": sorted(str(k) for k in oauth_states.keys()),
    }
