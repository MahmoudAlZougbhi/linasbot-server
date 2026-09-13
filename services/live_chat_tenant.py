"""Live Chat tenant identity. Fail-closed when tenant_id cannot be proven."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

_SOCIAL_CHANNELS = frozenset({"instagram", "facebook", "messenger", "tiktok", "whatsapp", "web"})
# Unprefixed Meta/TikTok IDs are the historical linas compose_social_user_id contract.
# WhatsApp phone ids and web:visitor ids are used by every tenant — never infer linas for those.
_LINAS_UNPREFIXED_CHANNELS = frozenset({"instagram", "facebook", "messenger", "tiktok"})


def normalize_live_chat_tenant_id(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _payload_tenant(payload: dict[str, Any] | None) -> str:
    data: dict[str, Any] = payload or {}
    customer_value = data.get("customer_info")
    customer: dict[str, Any] = customer_value if isinstance(customer_value, dict) else {}
    metadata_value = data.get("metadata")
    meta: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
    for raw in (
        data.get("tenant_id"),
        data.get("tenantId"),
        customer.get("tenant_id"),
        customer.get("tenantId"),
        meta.get("tenant_id"),
        meta.get("tenantId"),
    ):
        tid = normalize_live_chat_tenant_id(raw)
        if tid:
            return tid
    return ""


def _tenant_from_user_id(user_id: Any) -> str:
    uid = str(user_id or "").strip()
    parts = [p.strip() for p in uid.split(":") if p.strip()]
    if len(parts) >= 4 and parts[1].lower() in _SOCIAL_CHANNELS:
        return normalize_live_chat_tenant_id(parts[0])
    if len(parts) >= 3 and parts[0].lower() in _LINAS_UNPREFIXED_CHANNELS and parts[1].lower() not in _SOCIAL_CHANNELS:
        return "linas"
    if len(parts) == 2 and parts[0].lower() in _LINAS_UNPREFIXED_CHANNELS:
        return "linas"
    return ""


def _tenant_from_conversation_id(conversation_id: Any) -> str:
    cid = str(conversation_id or "").strip()
    parts = [p.strip() for p in cid.split(":") if p.strip()]
    if len(parts) >= 3 and parts[0].lower() == "web":
        return normalize_live_chat_tenant_id(parts[1])
    if len(parts) >= 4 and parts[1].lower() in _SOCIAL_CHANNELS:
        return normalize_live_chat_tenant_id(parts[0])
    return ""


def resolve_live_chat_tenant_id(
    *,
    user_id: Any = None,
    conversation_id: Any = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Proven tenant only. Empty string means the row is unscoped — never return it."""
    explicit = _payload_tenant(payload)
    if explicit:
        return explicit
    from_id = _tenant_from_user_id(user_id)
    if from_id:
        return from_id
    if payload:
        from_id = _tenant_from_user_id(payload.get("user_id") or payload.get("userId"))
        if from_id:
            return from_id
    from_conv = _tenant_from_conversation_id(conversation_id or (payload or {}).get("conversation_id"))
    if from_conv:
        return from_conv
    return ""


def index_row_tenant_id(data: dict[str, Any] | None, *, conversation_id: Any = None) -> str:
    data = data or {}
    return resolve_live_chat_tenant_id(
        user_id=data.get("user_id"),
        conversation_id=conversation_id or data.get("conversation_id"),
        payload=data,
    )


def row_belongs_to_tenant(data: dict[str, Any] | None, tenant_id: Any) -> bool:
    wanted = normalize_live_chat_tenant_id(tenant_id)
    if not wanted:
        return False
    row_tenant = index_row_tenant_id(data, conversation_id=(data or {}).get("conversation_id"))
    return bool(row_tenant) and row_tenant == wanted


def require_workspace_tenant(session: Any) -> str:
    tid = normalize_live_chat_tenant_id(getattr(session, "tenant_id", None))
    if not tid:
        raise HTTPException(status_code=403, detail="Forbidden")
    return tid


def session_row_allowed(session: Any, row: dict[str, Any] | None) -> bool:
    return row_belongs_to_tenant(row, getattr(session, "tenant_id", None))


def conversation_tenant_fields(
    *,
    user_id: Any,
    conversation_id: Any = None,
    existing: dict[str, Any] | None = None,
    customer_info: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fields to persist on a conversation/index write. Empty when tenant cannot be proven."""
    merged: dict[str, Any] = dict(existing or {})
    if customer_info is not None:
        merged["customer_info"] = customer_info
    if metadata is not None:
        merged["metadata"] = metadata
    tid = resolve_live_chat_tenant_id(user_id=user_id, conversation_id=conversation_id, payload=merged)
    if not tid:
        return {}
    info = dict(customer_info or merged.get("customer_info") or {})
    info["tenant_id"] = tid
    return {"tenant_id": tid, "customer_info": info}
