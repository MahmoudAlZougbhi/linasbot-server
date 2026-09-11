"""In-memory tenant+customer scoped facts with expiry. No auto sensitive storage."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

_SENSITIVE = re.compile(r"(password|passwd|secret|token|ssn|credit\s*card|cvv|otp|pin)\b", re.I)
_PHONE = re.compile(r"\+?\d[\d\s\-().]{8,}\d")
_DEFAULT_TTL_S = 60 * 60 * 6


@dataclass
class MemoryFact:
    key: str
    value: str
    expires_at: float
    created_at: float = field(default_factory=lambda: time.time())
    source_message_ids: list[str] = field(default_factory=list)
    confidence: float = 0.7


class MemoryStore:
    def __init__(self) -> None:
        self._facts: dict[str, dict[str, MemoryFact]] = {}

    @staticmethod
    def _scope(tenant_id: str, customer_id: str) -> str:
        return f"{tenant_id.strip()}::{customer_id.strip() or 'anon'}"

    def _purge(self, scope: str) -> None:
        now = time.time()
        bucket = self._facts.get(scope) or {}
        alive = {k: v for k, v in bucket.items() if v.expires_at > now}
        if alive:
            self._facts[scope] = alive
        else:
            self._facts.pop(scope, None)

    @staticmethod
    def _safe_value(value: str) -> str | None:
        text = (value or "").strip()
        if not text or _SENSITIVE.search(text):
            return None
        if _PHONE.fullmatch(re.sub(r"\s+", "", text)):
            return None
        return text[:500]

    def remember(
        self,
        tenant_id: str,
        customer_id: str,
        key: str,
        value: str,
        *,
        ttl_s: int = _DEFAULT_TTL_S,
        source_message_ids: list[str] | None = None,
        confidence: float = 0.7,
    ) -> bool:
        safe = self._safe_value(value)
        key_clean = (key or "").strip().casefold()[:80]
        if not safe or not key_clean or not tenant_id.strip() or _SENSITIVE.search(key_clean):
            return False
        scope = self._scope(tenant_id, customer_id)
        self._purge(scope)
        bucket = self._facts.setdefault(scope, {})
        bucket[key_clean] = MemoryFact(
            key=key_clean,
            value=safe,
            expires_at=time.time() + max(60, ttl_s),
            source_message_ids=list(source_message_ids or [])[:8],
            confidence=float(confidence),
        )
        if len(bucket) > 40:
            oldest = sorted(bucket.values(), key=lambda item: item.created_at)[: len(bucket) - 40]
            for item in oldest:
                bucket.pop(item.key, None)
        return True

    def recall(self, tenant_id: str, customer_id: str, key: str | None = None) -> dict[str, str]:
        scope = self._scope(tenant_id, customer_id)
        self._purge(scope)
        bucket = self._facts.get(scope) or {}
        if key:
            item = bucket.get(key.strip().casefold())
            return {item.key: item.value} if item else {}
        return {k: v.value for k, v in bucket.items()}

    def forget(self, tenant_id: str, customer_id: str, key: str | None = None) -> None:
        scope = self._scope(tenant_id, customer_id)
        if key is None:
            self._facts.pop(scope, None)
            return
        bucket = self._facts.get(scope) or {}
        bucket.pop(key.strip().casefold(), None)

    def export_safe(self, tenant_id: str, customer_id: str) -> list[dict[str, Any]]:
        scope = self._scope(tenant_id, customer_id)
        self._purge(scope)
        return [
            {
                "key": item.key,
                "value": item.value,
                "source_message_ids": list(item.source_message_ids),
                "confidence": item.confidence,
            }
            for item in (self._facts.get(scope) or {}).values()
        ]


_STORE = MemoryStore()


def get_memory_store() -> MemoryStore:
    return _STORE


def remember_fact(
    *,
    tenant_id: str,
    customer_id: str,
    key: str,
    value: str,
    source_message_ids: list[str] | None = None,
    confidence: float = 0.7,
    fact_type: str = "preference",
) -> dict[str, Any]:
    ok = _STORE.remember(
        tenant_id,
        customer_id,
        key,
        value,
        source_message_ids=source_message_ids,
        confidence=confidence,
    )
    if not ok:
        return {"ok": False, "reason": "rejected"}
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.customer_ai.memory import store_pg

        with whatsapp_session(require=True) as session:
            if store_pg.table_ready(session):
                store_pg.upsert_fact(
                    session,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    key=(key or "").strip().casefold()[:80],
                    value=(value or "").strip()[:500],
                    source_message_ids=source_message_ids,
                    confidence=confidence,
                    fact_type=fact_type,
                )
    except Exception:
        pass
    return {"ok": True, "fact": {"key": key, "value": value}}


def recall_facts(*, tenant_id: str, customer_id: str, limit: int = 12) -> list[dict[str, Any]]:
    try:
        from db.session import whatsapp_session
        from services.customer_ai.memory import store_pg

        with whatsapp_session(require=True) as session:
            if store_pg.table_ready(session):
                rows = store_pg.list_facts(session, tenant_id=tenant_id, customer_id=customer_id, limit=limit)
                if rows:
                    return rows
    except Exception:
        pass
    rows = _STORE.export_safe(tenant_id, customer_id)
    return rows[-max(1, limit) :]


def reset_memory_for_tests() -> None:
    _STORE._facts.clear()
