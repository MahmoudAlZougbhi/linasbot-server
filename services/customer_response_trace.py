"""Safe customer-response TRACE for owner self-diagnosis.

Persists factual interaction evidence only — never chain-of-thought / private prompts.
Also indexes recent activity_flow rows for tenant-scoped retrieval.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

_SECRET_KEYS = {"api_key", "access_token", "authorization", "secret", "password", "bearer"}


def _safe_str(value: Any, max_len: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def build_safe_trace(
    *,
    tenant_id: str,
    channel: str | None,
    conversation_id: str | None,
    customer_message: str | None,
    ai_response: str | None,
    cm_refs: dict[str, Any] | None = None,
    retrieved_sections: list[str] | None = None,
    knowledge_refs: list[str] | None = None,
    faq_match: dict[str, Any] | None = None,
    model: str | None = None,
    provider: str | None = None,
    tools_used: list[str] | None = None,
    source: str | None = None,
    interaction_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a TRACE dict with only safe, customer-facing evidence fields."""
    safe_faq = None
    if isinstance(faq_match, dict) and faq_match:
        safe_faq = {
            "faq_id": faq_match.get("faq_id"),
            "qa_group_id": faq_match.get("qa_group_id"),
            "tier": _safe_str(faq_match.get("tier"), 40),
            "similarity": faq_match.get("similarity")
            if isinstance(faq_match.get("similarity"), (int, float))
            else None,
            "stored_language": _safe_str(faq_match.get("stored_language"), 16),
        }
    safe_cm = None
    if isinstance(cm_refs, dict) and cm_refs:
        safe_cm = {
            "content_version_id": _safe_str(cm_refs.get("content_version_id"), 120),
            "index_version_id": _safe_str(cm_refs.get("index_version_id"), 120),
            "section": _safe_str(cm_refs.get("section"), 64),
            "revision": cm_refs.get("revision"),
        }
    return {
        "trace_id": interaction_id or uuid.uuid4().hex,
        "tenant_id": (tenant_id or "").strip().lower(),
        "channel": _safe_str(channel, 40) or "unknown",
        "conversation_id": _safe_str(conversation_id, 120),
        "customer_message": _safe_str(customer_message, 500),
        "ai_response": _safe_str(ai_response, 1000),
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cm_refs": safe_cm,
        "retrieved_sections": [str(s)[:80] for s in (retrieved_sections or [])[:20]],
        "knowledge_refs": [str(k)[:120] for k in (knowledge_refs or [])[:20]],
        "faq_match": safe_faq,
        "model": _safe_str(model, 80),
        "provider": _safe_str(provider, 40),
        "tools_used": [str(t)[:80] for t in (tools_used or [])[:30]],
        "source": _safe_str(source, 40),
        "extra": {
            k: v
            for k, v in (extra or {}).items()
            if str(k).lower() not in _SECRET_KEYS and not str(k).lower().endswith("_prompt")
        }
        if extra
        else None,
    }


class CustomerResponseTraceStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "customer_response_traces")
        self._root.mkdir(parents=True, exist_ok=True)

    def _tenant_file(self, tenant_id: str) -> Path:
        d = self._root / (tenant_id or "unknown").strip().lower()
        d.mkdir(parents=True, exist_ok=True)
        return d / "traces.jsonl"

    def persist(self, trace: dict[str, Any]) -> dict[str, Any]:
        tid = str(trace.get("tenant_id") or "unknown")
        path = self._tenant_file(tid)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
        return trace

    def get(self, *, tenant_id: str, trace_id: str) -> dict[str, Any] | None:
        path = self._tenant_file(tenant_id)
        if not path.is_file():
            return None
        with self._lock:
            lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-2000:]):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("trace_id")) == trace_id and str(row.get("tenant_id") or "").lower() == tenant_id.lower():
                if isinstance(row, dict):
                    return row
        return None

    def list_recent(self, *, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        path = self._tenant_file(tenant_id)
        rows: list[dict[str, Any]] = []
        if path.is_file():
            with self._lock:
                lines = path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-500:]):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("tenant_id") or "").lower() == tenant_id.lower():
                    rows.append(row)
                if len(rows) >= limit:
                    break
        return rows


customer_response_trace_store = CustomerResponseTraceStore()


def persist_from_interaction_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Convert an activity_flow / log_interaction entry into a safe TRACE and persist."""
    tid = str(entry.get("tenant_id") or "").strip().lower()
    if not tid:
        return None
    cm = entry.get("cm_diagnostics") if isinstance(entry.get("cm_diagnostics"), dict) else None
    retrieved = []
    if cm:
        retrieved = list(cm.get("source_ids") or [])[:20]
        for src in cm.get("retrieved_sources") or []:
            if isinstance(src, dict) and src.get("source_id"):
                retrieved.append(str(src["source_id"]))
    trace = build_safe_trace(
        tenant_id=tid,
        channel=str(entry.get("channel") or "unknown"),
        conversation_id=entry.get("conversation_id"),
        customer_message=entry.get("user_message"),
        ai_response=entry.get("bot_to_user"),
        cm_refs={
            "content_version_id": (cm or {}).get("content_version_id"),
            "index_version_id": (cm or {}).get("index_version_id"),
        }
        if cm
        else None,
        retrieved_sections=retrieved,
        knowledge_refs=list((cm or {}).get("source_ids") or [])[:20] if cm else None,
        faq_match=entry.get("faq_match") if isinstance(entry.get("faq_match"), dict) else None,
        model=entry.get("model"),
        provider="openai" if entry.get("model") else None,
        tools_used=list(entry.get("tool_calls") or []) if isinstance(entry.get("tool_calls"), list) else None,
        source=str(entry.get("source") or entry.get("outcome") or ""),
        interaction_id=str(entry.get("message_id") or entry.get("trace_id") or uuid.uuid4().hex),
        extra={"handler_path": entry.get("handler_path"), "outcome": entry.get("outcome")},
    )
    return customer_response_trace_store.persist(trace)


def get_recent_customer_interactions(*, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Tenant-scoped recent interactions from TRACE store + activity flow fallback."""
    rows = customer_response_trace_store.list_recent(tenant_id=tenant_id, limit=limit)
    if len(rows) >= limit:
        return rows

    from services.interaction_flow_logger import get_recent_flows

    seen = {str(r.get("trace_id")) for r in rows}
    for entry in reversed(get_recent_flows(limit=max(limit * 3, 60))):
        if str(entry.get("tenant_id") or "").lower() != tenant_id.lower():
            continue
        mid = str(entry.get("message_id") or entry.get("timestamp") or "")
        if mid and mid in seen:
            continue
        compact = {
            "trace_id": mid or uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "channel": entry.get("channel"),
            "conversation_id": entry.get("conversation_id"),
            "customer_message": entry.get("user_message"),
            "ai_response": entry.get("bot_to_user"),
            "timestamp_iso": entry.get("timestamp"),
            "source": entry.get("source"),
            "faq_match": entry.get("faq_match"),
            "cm_refs": entry.get("cm_diagnostics"),
            "model": entry.get("model"),
            "tools_used": entry.get("tool_calls") or [],
        }
        rows.append(compact)
        if len(rows) >= limit:
            break
    return rows[:limit]


def get_interaction_trace(*, tenant_id: str, trace_id: str) -> dict[str, Any] | None:
    found = customer_response_trace_store.get(tenant_id=tenant_id, trace_id=trace_id)
    if found:
        return found
    # Fallback scan of recent activity flow
    from services.interaction_flow_logger import get_recent_flows

    for entry in reversed(get_recent_flows(limit=200)):
        if str(entry.get("tenant_id") or "").lower() != tenant_id.lower():
            continue
        mid = str(entry.get("message_id") or "")
        if mid == trace_id or str(entry.get("timestamp")) == trace_id:
            return persist_from_interaction_entry(entry)
    return None
