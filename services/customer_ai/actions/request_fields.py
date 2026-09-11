"""Attach published request-graph field keys to a proposal. Never invent values."""

from __future__ import annotations

from typing import Any

_DEST = {"APPOINTMENT": "appointment", "ORDER": "order", "OTHER": "other"}


def published_request_fields(tenant_id: str, request_type: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    dest = _DEST.get((request_type or "").upper())
    if not tid or not dest:
        return {}
    try:
        from db.session import whatsapp_session
        from services.request_graphs.service import list_active_graphs

        with whatsapp_session(require=False) as session:
            if session is None:
                return {}
            rows = list_active_graphs(session, tenant_id=tid)
    except Exception:
        return {}
    for row in rows:
        if str(row.get("destination") or "") != dest:
            continue
        keys = [
            str(item.get("key") or "").strip()
            for item in (row.get("required_information") or [])
            if isinstance(item, dict)
        ]
        fields = {key: "" for key in keys if key}
        if not fields:
            continue
        return {
            "collected_fields": fields,
            "graph_id": str(row.get("definition_id") or ""),
        }
    return {}


def collected_from_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    raw = (fields or {}).get("collected_fields")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).strip()}


def prior_collected_fields(pending: list[Any], request_type: str) -> dict[str, Any]:
    """Keep non-empty answers already staged for this request type. Do not invent keys."""
    want = (request_type or "").strip().upper()
    out: dict[str, Any] = {}
    for item in pending:
        if not isinstance(item, dict):
            continue
        raw_fields = item.get("fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        kind = str(fields.get("request_type") or "").strip().upper()
        if want and kind and kind != want:
            continue
        for key, value in collected_from_fields(fields).items():
            if str(value or "").strip():
                out[key] = value
    return out


def merge_proposal_fields_with_prior(
    fields: dict[str, Any] | None,
    pending: list[Any],
) -> dict[str, Any]:
    """Incoming non-empty values win; empty published keys keep prior answers."""
    current = dict(fields or {})
    incoming = collected_from_fields(current)
    prior = prior_collected_fields(pending, str(current.get("request_type") or ""))
    merged = dict(incoming)
    for key, value in prior.items():
        if not str(merged.get(key) or "").strip():
            merged[key] = value
    if merged or incoming:
        current["collected_fields"] = merged
    return current


def merge_fields_for_persist(
    tenant_id: str,
    request_type: str,
    collected: dict[str, Any] | None,
) -> dict[str, Any]:
    """Re-attach published graph keys at confirm. Incoming values win; never invent values."""
    published = dict(published_request_fields(tenant_id, request_type).get("collected_fields") or {})
    incoming = dict(collected or {})
    return {**published, **incoming}
