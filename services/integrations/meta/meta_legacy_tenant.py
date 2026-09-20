"""Legacy single-tenant Meta webhook bind — opt-in only. Never silent tenant_id=linas."""

from __future__ import annotations

import os

# Single-tenant env-credential webhooks (registry off) require this flag.
# Production multi-tenant must keep META_MULTI_APP_REGISTRY_ENABLED=true.
LEGACY_OPT_IN_ENV = "LINAS_META_LEGACY_SINGLE_TENANT"
REQUIRE_REGISTRY_ENV = "LINAS_META_REQUIRE_REGISTRY"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def meta_legacy_single_tenant_opt_in() -> bool:
    """Explicit opt-in for env-credential Meta webhooks. Default off."""
    return _truthy(os.getenv(LEGACY_OPT_IN_ENV))


def meta_require_registry() -> bool:
    """Fail closed in prod, or when LINAS_META_REQUIRE_REGISTRY is set."""
    if _truthy(os.getenv(REQUIRE_REGISTRY_ENV)):
        return True
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    if env in {"prod", "production"} and not meta_legacy_single_tenant_opt_in():
        return True
    return False


def legacy_webhook_tenant_id() -> str:
    """Tenant for opt-in legacy route. Empty when not allowed — callers must 503.

    Never defaults to ``linas``. Set LINASBOT_TENANT_ID when opting in.
    """
    if meta_require_registry() or not meta_legacy_single_tenant_opt_in():
        return ""
    return (os.getenv("LINASBOT_TENANT_ID") or "").strip()
