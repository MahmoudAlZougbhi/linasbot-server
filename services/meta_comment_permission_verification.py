"""Postgres-backed Meta comment permission verification for active bindings."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Literal

import httpx

from services.meta_app_registry import MetaAppRegistry, MetaAssetBinding, MetaBindingCredential, get_meta_app_registry
from services.meta_graph_routing import required_comment_scopes_for_binding
from services.meta_oauth_graph_http import MetaOAuthError, _debug_token

CommentPermissionStatus = Literal["verified_granted", "verified_missing", "unknown"]
CommentPermissionSource = Literal[
    "oauth_stored_scopes",
    "debug_token",
    "migration_stored_scopes",
    "reconcile_job",
]

_RUNTIME_LOGGER = logging.getLogger("uvicorn.error")
_RECONCILE_BACKOFF_SECONDS = 120.0

__all__ = [
    "CommentPermissionStatus",
    "CommentPermissionSource",
    "comment_permission_blocker_code",
    "comment_permission_enforcement_decision",
    "comment_permission_public_snapshot",
    "comment_permission_token_fingerprint",
    "effective_comment_permission_status",
    "maybe_reconcile_binding_comment_permission",
    "persist_comment_permission_from_credential",
    "reconcile_binding_comment_permission",
    "verification_matches_current_credential",
    "verify_comment_permission_from_stored_scopes",
]


def comment_permission_token_fingerprint(access_token: str) -> str:
    token = str(access_token or "").strip()
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def verification_matches_current_credential(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
) -> bool:
    if str(binding.credential_id or "").strip() != str(binding.comment_permission_credential_id or "").strip():
        return False
    expected = comment_permission_token_fingerprint(credential.access_token)
    stored = str(binding.comment_permission_token_fingerprint or "").strip()
    return bool(expected and stored and expected == stored)


def verify_comment_permission_from_stored_scopes(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
) -> tuple[CommentPermissionStatus, CommentPermissionSource]:
    required = required_comment_scopes_for_binding(binding)
    granted = {str(scope) for scope in (credential.scopes or ())}
    if required.issubset(granted):
        return "verified_granted", "oauth_stored_scopes"
    return "verified_missing", "oauth_stored_scopes"


def effective_comment_permission_status(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
) -> CommentPermissionStatus:
    if not verification_matches_current_credential(binding, credential):
        return "unknown"
    status = str(binding.comment_permission_status or "unknown").strip().lower()
    if status in {"verified_granted", "verified_missing"}:
        return status  # type: ignore[return-value]
    return "unknown"


def comment_permission_public_snapshot(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
) -> dict[str, Any]:
    required = sorted(required_comment_scopes_for_binding(binding))
    granted = sorted(set(required) & set(credential.scopes or ()))
    status = effective_comment_permission_status(binding, credential)
    return {
        "status": status,
        "verified_at": float(binding.comment_permission_verified_at or 0),
        "source": str(binding.comment_permission_source or ""),
        "credential_id": str(binding.comment_permission_credential_id or ""),
        "token_bound": verification_matches_current_credential(binding, credential),
        "scopes_required": required,
        "scopes_granted": granted,
        "scopes_missing": sorted(set(required) - set(credential.scopes or ())),
    }


def comment_permission_blocker_code(status: CommentPermissionStatus) -> str | None:
    if status == "verified_granted":
        return None
    if status == "verified_missing":
        return "missing_comment_permissions"
    return "comment_permissions_could_not_be_verified"


def comment_permission_enforcement_decision(
    *,
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    tenant_id: str,
    per_asset_enabled: bool,
    registry: MetaAppRegistry | None = None,
) -> dict[str, Any]:
    from services.cm.actions import comments_enforcement_decision

    base = comments_enforcement_decision(
        tenant_id=tenant_id,
        channel=binding.channel,
        per_asset_enabled=per_asset_enabled,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    permission = comment_permission_public_snapshot(binding, credential)
    base["permission"] = permission
    if base["allow"]:
        return base
    return base


def _verification_record(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    status: CommentPermissionStatus,
    source: CommentPermissionSource,
    verified_at: float | None = None,
) -> dict[str, Any]:
    return {
        "comment_permission_status": status,
        "comment_permission_verified_at": time.time() if verified_at is None else verified_at,
        "comment_permission_source": source,
        "comment_permission_credential_id": binding.credential_id,
        "comment_permission_token_fingerprint": comment_permission_token_fingerprint(credential.access_token),
    }


def persist_comment_permission_from_credential(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry | None = None,
    source: CommentPermissionSource = "oauth_stored_scopes",
    actor_id: str = "system",
) -> MetaAssetBinding:
    status, resolved_source = verify_comment_permission_from_stored_scopes(binding, credential)
    record = _verification_record(
        binding,
        credential,
        status=status,
        source=source if source != "oauth_stored_scopes" else resolved_source,
    )
    current_registry = registry or get_meta_app_registry()
    return current_registry.update_comment_permission_verification(
        binding.binding_id,
        actor_id=actor_id,
        **record,
    )


def _debug_token_scopes(data: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    raw_scopes = data.get("scopes")
    if isinstance(raw_scopes, list):
        scopes.update(str(item).strip() for item in raw_scopes if str(item).strip())
    granular = data.get("granular_scopes")
    if isinstance(granular, list):
        for item in granular:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("scope") or "").strip()
            if scope:
                scopes.add(scope)
    return scopes


def _resolve_debug_app_credentials(binding: MetaAssetBinding) -> tuple[str, str]:
    from services.meta_app_registry import get_meta_app_configs
    from services.meta_instagram_login_config import instagram_login_app_id, instagram_login_app_secret

    if binding.auth_flow == "instagram_login" and binding.channel == "instagram":
        app_id = instagram_login_app_id()
        secret = instagram_login_app_secret()
        if not app_id or not secret:
            raise MetaOAuthError("Instagram Login app credentials are not configured")
        return app_id, secret
    app = get_meta_app_configs()[binding.app_key]
    return app.app_id, app.app_secret


async def reconcile_binding_comment_permission(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    actor_id: str = "reconcile_job",
    client: httpx.AsyncClient | None = None,
) -> MetaAssetBinding:
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    stored_status, stored_source = verify_comment_permission_from_stored_scopes(binding, credential)
    if stored_status != "unknown":
        return current_registry.update_comment_permission_verification(
            binding.binding_id,
            actor_id=actor_id,
            **_verification_record(binding, credential, status=stored_status, source=stored_source),
        )

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        app_id, app_secret = _resolve_debug_app_credentials(binding)
        try:
            data = await _debug_token(
                http_client,
                token=credential.access_token,
                app_id=app_id,
                app_secret=app_secret,
            )
        except MetaOAuthError as exc:
            if (
                verification_matches_current_credential(binding, credential)
                and binding.comment_permission_status == "verified_granted"
            ):
                _RUNTIME_LOGGER.info(
                    "[meta-comment-perm] reconcile_kept_last_known_good binding_id=%s reason=%s",
                    binding.binding_id,
                    type(exc).__name__,
                )
                return binding
            raise
        except httpx.HTTPError:
            if (
                verification_matches_current_credential(binding, credential)
                and binding.comment_permission_status == "verified_granted"
            ):
                _RUNTIME_LOGGER.info(
                    "[meta-comment-perm] reconcile_kept_last_known_good binding_id=%s reason=transient_http",
                    binding.binding_id,
                )
                return binding
            raise MetaOAuthError("Meta comment permission reconcile request failed") from None

        required = required_comment_scopes_for_binding(binding)
        granted = _debug_token_scopes(data)
        status: CommentPermissionStatus = "verified_granted" if required.issubset(granted) else "verified_missing"
        return current_registry.update_comment_permission_verification(
            binding.binding_id,
            actor_id=actor_id,
            **_verification_record(binding, credential, status=status, source="debug_token"),
        )
    finally:
        if owns_client:
            await http_client.aclose()


def maybe_reconcile_binding_comment_permission(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    now: float | None = None,
) -> bool:
    """Return True when reconcile should run now for an unknown/stale verification."""

    current_registry = registry or get_meta_app_registry()
    try:
        credential = current_registry.get_credential(binding)
    except Exception:
        return False
    status = effective_comment_permission_status(binding, credential)
    if status != "unknown":
        return False
    checked_at = float(binding.comment_permission_verified_at or 0)
    current = time.time() if now is None else now
    if checked_at <= 0:
        return True
    return current - checked_at >= _RECONCILE_BACKOFF_SECONDS


def bootstrap_unknown_comment_permissions(
    *,
    registry: MetaAppRegistry | None = None,
    actor_id: str = "migration_stored_scopes",
) -> dict[str, int]:
    """One-shot migration helper: derive verification from stored credential scopes."""

    current_registry = registry or get_meta_app_registry()
    updated = 0
    skipped = 0
    for binding in current_registry.list_bindings(include_inactive=False, include_superseded=False):
        if binding.status != "active":
            skipped += 1
            continue
        try:
            credential = current_registry.get_credential(binding)
        except Exception:
            skipped += 1
            continue
        if effective_comment_permission_status(binding, credential) != "unknown":
            skipped += 1
            continue
        persist_comment_permission_from_credential(
            binding,
            credential,
            registry=current_registry,
            source="migration_stored_scopes",
            actor_id=actor_id,
        )
        updated += 1
    return {"updated": updated, "skipped": skipped}


def count_active_bindings_with_unknown_comment_permission(
    *,
    registry: MetaAppRegistry | None = None,
) -> int:
    """Count active bindings whose effective comment permission is still unknown."""

    current_registry = registry or get_meta_app_registry()
    pending = 0
    for binding in current_registry.list_bindings(include_inactive=False, include_superseded=False):
        if binding.status != "active":
            continue
        try:
            credential = current_registry.get_credential(binding)
        except Exception:
            pending += 1
            continue
        if effective_comment_permission_status(binding, credential) == "unknown":
            pending += 1
    return pending
