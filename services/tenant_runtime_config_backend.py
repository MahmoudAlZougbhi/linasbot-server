"""Backend resolver for tenant runtime configuration (Postgres vs file cache)."""

from __future__ import annotations

import os


class TenantRuntimeConfigBackendError(RuntimeError):
    code = "TENANT_RUNTIME_CONFIG_BACKEND_ERROR"


def tenant_runtime_config_backend() -> str:
    """Return ``postgres`` or ``file``. Production defaults to postgres when DB is configured."""

    explicit = (os.getenv("LINAS_TENANT_RUNTIME_CONFIG_BACKEND") or "").strip().lower()
    if explicit in {"postgres", "file"}:
        return explicit
    from db.session import whatsapp_db_configured

    if whatsapp_db_configured():
        return "postgres"
    return "file"


def tenant_runtime_config_postgres_required() -> bool:
    return tenant_runtime_config_backend() == "postgres"


def require_tenant_runtime_config_postgres() -> None:
    if not tenant_runtime_config_postgres_required():
        return
    from db.session import ping_whatsapp_db

    health = ping_whatsapp_db()
    if not health.get("reachable"):
        raise TenantRuntimeConfigBackendError("Tenant runtime config requires Postgres but database is unreachable.")
