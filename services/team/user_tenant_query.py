"""Tenant member lookup by equality, including the legacy field spellings.

A full users-collection scan billed one read per account in the project.
Each variant below is its own limited query. Empty variants cost one read.
"""

from __future__ import annotations

import time
from typing import Any

_QUERY_LIMIT = 100
_CACHE_TTL_SECONDS = 30.0
_FIELDS = ("tenantId", "tenant_id")
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def tenant_id_variants(tenant_id: str) -> list[str]:
    raw = (tenant_id or "").strip()
    if not raw:
        return []
    titled = raw[:1].upper() + raw[1:].lower()
    variants: list[str] = []
    for item in (raw.lower(), raw, raw.upper(), titled):
        if item and item not in variants:
            variants.append(item)
    return variants


def invalidate_tenant_user_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _cache.clear()
        return
    for key in tenant_id_variants(tenant_id):
        _cache.pop(key.lower(), None)


def list_users_for_tenant(service: Any, tenant_id: str) -> list[dict[str, Any]]:
    normalized = service._normalize_tenant_id(tenant_id)
    if not normalized:
        return []
    now = time.time()
    cached = _cache.get(normalized)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return [dict(row) for row in cached[1]]

    from google.cloud.firestore_v1.base_query import FieldFilter

    found: dict[str, dict[str, Any]] = {}
    for field in _FIELDS:
        for value in tenant_id_variants(tenant_id):
            query = service.collection.where(filter=FieldFilter(field, "==", value)).limit(_QUERY_LIMIT)
            try:
                docs = list(query.stream(timeout=service.AUTH_QUERY_TIMEOUT_SECONDS, retry=None))
            except Exception as exc:
                print(f"[auth:tenant_users] query failed field={field} type={type(exc).__name__}", flush=True)
                continue
            for doc in docs:
                try:
                    sanitized = service._sanitize_user(doc.to_dict() or {}, doc_id=doc.id)
                except Exception as exc:
                    print(f"[auth:tenant_users] skip {doc.id}: {exc}", flush=True)
                    continue
                if sanitized is None:
                    continue
                if str(sanitized.get("tenantId") or "").strip() != normalized:
                    continue
                uid = str(sanitized.get("id") or "").strip()
                if uid:
                    found[uid] = sanitized
    rows = list(found.values())
    _cache[normalized] = (now, [dict(row) for row in rows])
    from services.scale.firestore_usage import record_usage

    record_usage("tenant_users", reads=max(1, len(rows)))
    return rows


def list_users_capped(service: Any, *, limit: int = 200) -> list[dict[str, Any]]:
    """Owner-portal page. Stops the admin screen from reading every account."""
    cap = max(1, min(500, int(limit)))
    try:
        docs = list(service.collection.limit(cap).stream(timeout=service.AUTH_QUERY_TIMEOUT_SECONDS, retry=None))
    except Exception as exc:
        print(f"[auth:users_capped] failed type={type(exc).__name__}", flush=True)
        return []
    users: list[dict[str, Any]] = []
    for doc in docs:
        try:
            sanitized = service._sanitize_user(doc.to_dict() or {}, doc_id=doc.id)
        except Exception:
            continue
        if sanitized is not None:
            users.append(sanitized)
    from services.scale.firestore_usage import record_usage

    record_usage("owner_user_page", reads=max(1, len(users)))
    return users
