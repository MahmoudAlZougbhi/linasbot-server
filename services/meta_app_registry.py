"""Encrypted registry for Meta apps, tenant assets, OAuth state, and rollback.

The registry intentionally stores application secrets in the process environment and
tenant/Page tokens only as AES-GCM ciphertext. Active bindings are exclusive per
channel/asset_id globally, so two Meta apps can never answer the same Page or
Instagram account at the same time. A workspace may own multiple assets per channel.

Persistence backend via META_REGISTRY_BACKEND:
  - postgres (default) — Postgres SoT only (fail closed if DB unavailable; no file fallback)
  - file — local/dev or emergency rollback
  - dual — write PG then file; read PG primary (migration helper only)

Helpers: meta_app_registry_common; mixins: bindings/lifecycle/oauth (LOC split).
"""

from __future__ import annotations

import os
import time

from services.meta_app_registry_bindings import MetaAppRegistryBindingsMixin
from services.meta_app_registry_common import (
    APP_A_EXPECTED_ID,
    APP_A_KEY,
    APP_B_KEY,
    FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    META_CHANNEL_SCOPES,
    META_COMMENT_SCOPES,
    META_COMMON_MESSAGING_SCOPES,
    META_FACEBOOK_LOGIN_EXTRA_SCOPES,
    META_FORBIDDEN_SCOPES,
    META_PUBLISH_SCOPES,
    REGISTRY_SCHEMA_VERSION,
    AuthFlow,
    BindingStatus,
    MetaAppClassification,
    MetaAppConfig,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaBindingNotFoundError,
    MetaChannel,
    MetaCredentialCipher,
    MetaCredentialError,
    MetaOAuthStateError,
    MetaRegistryError,
    MetaRegistryNotConfiguredError,
    _app_b_linas_cutover_allowed,
    _bindings_share_exclusive_asset,
    _normalized_graph_version,
    _truthy,
    authorized_meta_user_id_hash,
    binding_asset_key,
    binding_exclusive_asset_key,
    get_meta_app_configs,
    get_meta_graph_api_version,
    identify_signed_meta_app,
    mask_asset_id,
    meta_multi_app_registry_enabled,
    normalize_meta_tenant_id,
    verify_any_meta_challenge_token,
)
from services.meta_app_registry_deletion import MetaAppRegistryDeletionMixin
from services.meta_app_registry_lifecycle import MetaAppRegistryLifecycleMixin
from services.meta_app_registry_oauth import MetaAppRegistryOAuthMixin
from services.meta_app_registry_recovery import MetaAppRegistryRecoveryMixin

__all__ = [
    "APP_A_EXPECTED_ID",
    "APP_A_KEY",
    "APP_B_KEY",
    "FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT",
    "LINAS_INSTAGRAM_ACCOUNT_ID",
    "LINAS_PAGE_ID",
    "META_CHANNEL_SCOPES",
    "META_COMMENT_SCOPES",
    "META_COMMON_MESSAGING_SCOPES",
    "META_FACEBOOK_LOGIN_EXTRA_SCOPES",
    "META_FORBIDDEN_SCOPES",
    "META_PUBLISH_SCOPES",
    "REGISTRY_SCHEMA_VERSION",
    "AuthFlow",
    "BindingStatus",
    "MetaAppClassification",
    "MetaAppConfig",
    "MetaAppRegistry",
    "MetaAssetBinding",
    "MetaBindingConflictError",
    "MetaBindingCredential",
    "MetaBindingNotFoundError",
    "MetaChannel",
    "MetaCredentialCipher",
    "MetaCredentialError",
    "MetaOAuthStateError",
    "MetaRegistryError",
    "MetaRegistryNotConfiguredError",
    "_app_b_linas_cutover_allowed",
    "_bindings_share_exclusive_asset",
    "_normalized_graph_version",
    "_truthy",
    "authorized_meta_user_id_hash",
    "binding_asset_key",
    "binding_exclusive_asset_key",
    "get_meta_app_configs",
    "get_meta_app_registry",
    "get_meta_graph_api_version",
    "get_meta_registry_readiness",
    "diagnose_active_meta_binding",
    "META_PLATFORM_READINESS_KEYS",
    "identify_signed_meta_app",
    "mask_asset_id",
    "meta_multi_app_registry_enabled",
    "normalize_meta_tenant_id",
    "reset_meta_app_registry_for_tests",
    "verify_any_meta_challenge_token",
]


class MetaAppRegistry(
    MetaAppRegistryBindingsMixin,
    MetaAppRegistryLifecycleMixin,
    MetaAppRegistryRecoveryMixin,
    MetaAppRegistryDeletionMixin,
    MetaAppRegistryOAuthMixin,
):
    """Process-safe registry with encrypted credential envelopes (file|postgres|dual)."""


_registry_instance: MetaAppRegistry | None = None


def get_meta_app_registry() -> MetaAppRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MetaAppRegistry()
    return _registry_instance


def reset_meta_app_registry_for_tests() -> None:
    global _registry_instance
    _registry_instance = None


META_PLATFORM_READINESS_KEYS: tuple[str, ...] = (
    "encryption_key_configured",
    "app_a_configured",
    "registry_backend_ready",
)


def diagnose_active_meta_binding(
    registry: MetaAppRegistry,
    binding: MetaAssetBinding,
    *,
    now: int | None = None,
) -> str | None:
    """Return a tenant-binding failure reason, or None when the credential is healthy.

    This is diagnostic only. It must never be used as a platform / LB gate.
    """

    checked_at = int(time.time()) if now is None else now
    try:
        credential = registry.get_credential(binding)
        app = get_meta_app_configs().get(binding.app_key)
        from services.meta_instagram_login_config import required_scopes_for_binding

        required_scopes = required_scopes_for_binding(
            channel=binding.channel,
            auth_flow=binding.auth_flow,
        )
        instagram_login_app_id = (os.getenv("META_INSTAGRAM_LOGIN_APP_ID") or "1035856539045307").strip()
        if app is None or not app.enabled:
            return "app_disabled"
        if credential.token_app_id != app.app_id and not (
            binding.auth_flow == "instagram_login" and credential.token_app_id == instagram_login_app_id
        ):
            return "token_app_mismatch"
        if binding.auth_flow == "facebook_login" and credential.token_profile_id != binding.page_id:
            return "token_profile_mismatch"
        if binding.auth_flow == "instagram_login" and credential.token_profile_id != binding.asset_id:
            return "token_profile_mismatch"
        if not required_scopes.issubset(credential.scopes):
            return "missing_scopes"
        if set(credential.scopes) & META_FORBIDDEN_SCOPES:
            return "forbidden_scopes"
        if credential.expires_at is not None and credential.expires_at <= checked_at:
            return "expired_token"
        if binding.auth_flow == "instagram_login" and binding.active and binding.webhook_subscription_status != "ready":
            return "webhook_not_ready"
    except MetaRegistryError:
        return "credential_unavailable"
    return None


def get_meta_registry_readiness(
    registry: MetaAppRegistry | None = None,
) -> tuple[bool, dict[str, bool]]:
    """Platform-only Meta registry readiness for /api/ready and HA assert_ready.

    Binding, token, webhook, and tenant connection state belong in
    /api/channel-health. The unused registry argument is kept so callers that
    still pass a test registry do not inspect tenant rows on this path.
    """

    from services.meta_app_registry_bindings import resolve_meta_registry_backend

    _ = registry
    checks: dict[str, bool] = {
        "encryption_key_configured": len((os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()) >= 32,
        "app_a_configured": get_meta_app_configs()[APP_A_KEY].enabled,
        "registry_backend_ready": True,
    }
    try:
        backend = resolve_meta_registry_backend()
    except MetaRegistryError:
        checks["registry_backend_ready"] = False
        return False, checks
    if backend in {"postgres", "dual"}:
        from db.session import get_engine, whatsapp_db_configured

        if not whatsapp_db_configured():
            checks["registry_backend_ready"] = False
        else:
            try:
                get_engine(require=True)
            except Exception:  # noqa: BLE001 — readiness must fail closed
                checks["registry_backend_ready"] = False
    platform_ok = all(bool(checks[key]) for key in META_PLATFORM_READINESS_KEYS)
    return platform_ok, checks
