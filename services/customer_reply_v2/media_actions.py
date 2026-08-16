"""System-side product media_actions: validate stored media, never ask Tera to send files."""

from __future__ import annotations

import hashlib
from typing import Any

from services.products.availability import is_customer_searchable
from services.products.media import load_media_meta
from services.products.repository import ProductsRepository

ALLOWED_MEDIA_TYPES = {"images", "videos", "image", "video"}


def parse_media_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or "").strip()
        media_type = str(item.get("media_type") or "images").strip().lower()
        if not product_id or media_type not in ALLOWED_MEDIA_TYPES:
            continue
        try:
            max_items = max(1, min(int(item.get("max_items") or 5), 8))
        except (TypeError, ValueError):
            max_items = 5
        out.append(
            {
                "product_id": product_id,
                "media_type": "videos" if media_type in {"video", "videos"} else "images",
                "max_items": max_items,
                "order": str(item.get("order") or "configured_order"),
            }
        )
    return out


def _is_video_media(tenant_id: str, media_id: str) -> bool:
    meta = load_media_meta(tenant_id=tenant_id, media_id=media_id) or {}
    return str(meta.get("mime") or "").lower().startswith("video/")


def resolve_media_actions(
    *,
    tenant_id: str,
    actions: list[dict[str, Any]],
    channel_capabilities: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    caps = dict(channel_capabilities or {})
    max_channel = int(caps.get("max_media_items") or 0)
    if not actions:
        return {"ok": True, "items": [], "ai_charged": False, "idempotency_key": idempotency_key}
    if max_channel <= 0:
        return {
            "ok": False,
            "error": "channel_cannot_send_media",
            "items": [],
            "ai_charged": False,
            "owner_diagnostic": "Channel cannot send product media for this surface.",
        }

    from db.session import whatsapp_session

    delivered: list[dict[str, Any]] = []
    with whatsapp_session(require=True) as session:
        repo = ProductsRepository(session)
        for action in actions:
            row = repo.get_product(tenant_id=tenant_id, product_id=action["product_id"])
            if row is None:
                return {
                    "ok": False,
                    "error": "product_not_found",
                    "product_id": action["product_id"],
                    "items": delivered,
                    "ai_charged": False,
                }
            if str(getattr(row, "tenant_id", "") or "") != tenant_id:
                return {"ok": False, "error": "tenant_isolation", "items": delivered, "ai_charged": False}
            if not is_customer_searchable(row.availability):
                return {
                    "ok": False,
                    "error": "product_not_customer_facing",
                    "product_id": action["product_id"],
                    "items": delivered,
                    "ai_charged": False,
                }
            media_rows = sorted(list(getattr(row, "images", None) or []), key=lambda img: int(img.sort_order or 0))
            want_video = action["media_type"] == "videos"
            selected = []
            for img in media_rows:
                media_id = str(getattr(img, "media_id", "") or "")
                if not media_id:
                    continue
                is_video = _is_video_media(tenant_id, media_id)
                if want_video != is_video:
                    continue
                selected.append(img)
            limit = min(action["max_items"], max_channel)
            for img in selected[:limit]:
                delivered.append(
                    {
                        "product_id": row.id,
                        "media_id": str(img.media_id),
                        "media_type": action["media_type"],
                        "sort_order": int(img.sort_order or 0),
                    }
                )
    digest = hashlib.sha256(
        f"{tenant_id}:{idempotency_key}:{','.join(i['media_id'] for i in delivered)}".encode()
    ).hexdigest()[:16]
    return {
        "ok": True,
        "items": delivered,
        "ai_charged": False,
        "idempotency_key": idempotency_key or digest,
        "delivery_fingerprint": digest,
        "delivery_result": "resolved_pending_channel_send",
        "extra_tera_call": False,
    }


def plan_media_for_turn(
    *,
    tenant_id: str,
    answer: Any,
    channel_metadata: dict[str, Any] | None,
    meter: Any | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled
    from services.customer_reply_v2.invocation_meter import InvocationRecord

    if not customer_ai_v10_runtime_enabled():
        return {}
    raw = getattr(answer, "media_actions", None)
    if raw is None:
        raw = (getattr(answer, "raw_structured", None) or {}).get("media_actions")
    actions = parse_media_actions(raw)
    if not actions:
        return {"media_actions": [], "media_delivery": {"ok": True, "items": [], "ai_charged": False}}
    caps = dict((channel_metadata or {}).get("channel_capabilities") or {})
    plan = resolve_media_actions(
        tenant_id=tenant_id,
        actions=actions,
        channel_capabilities=caps,
        idempotency_key=idempotency_key,
    )
    if meter is not None:
        meter.record(
            InvocationRecord(
                operation="media_delivery",
                is_ai=False,
                success=bool(plan.get("ok")),
                failure_stage=None if plan.get("ok") else str(plan.get("error") or "media_delivery"),
            )
        )
    return {"media_actions": actions, "media_delivery": plan}
