"""Queue authorized send_resource items for the DM channel adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from services.brain.actions.resources import resolve_authorized_resource
from services.brain.contracts.actions import ActionReceipt
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.turn import CustomerTurn

_PENDING_KEY = "_pending_setup_resources"
_PRODUCT_PENDING = "_pending_product_media"


def empty_delivery() -> dict[str, Any]:
    return {"ok": False, "items": [], "sent": [], "failed": []}


def _record_item(record: dict[str, Any]) -> dict[str, Any]:
    ref = str(record.get("resource_ref") or record.get("id") or "")
    kind = str(record.get("resource_type") or record.get("kind") or "file")
    source_type = str(record.get("source_type") or "ai_setup_item")
    source_item_id = str(record.get("source_item_id") or "")
    product_id = str(record.get("product_id") or "")
    if source_type == "product_media" and not product_id and source_item_id.startswith("products:"):
        product_id = source_item_id.split(":", 1)[1]
    media_id = str(record.get("media_id") or "")
    if source_type == "product_media" and kind != "link" and not media_id:
        media_id = ref
    return {
        "resource_ref": ref,
        "resource_type": kind,
        "title": str(record.get("title") or ref),
        "source_item_id": source_item_id,
        "source_type": source_type,
        "id": ref,
        "kind": kind,
        "media_id": media_id,
        "product_id": product_id,
        "external_url": str(record.get("external_url") or record.get("url") or ""),
    }


def payload_from_records(
    records: list[dict[str, Any]],
    *,
    failed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = [_record_item(row) for row in records if str(row.get("resource_ref") or row.get("id") or "").strip()]
    sent = [{"id": row["id"], "kind": row["kind"]} for row in items]
    return {
        "ok": bool(items),
        "items": items,
        "sent": sent,
        "failed": list(failed or []),
    }


def payload_from_receipt(
    *,
    tenant_id: str,
    receipt: ActionReceipt,
    session: Any | None = None,
    allowed_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    if receipt.action_type != "send_resource" or receipt.state not in {"pending", "success"}:
        rejected = [{"id": receipt.backend_id, "error": receipt.reason or receipt.state}]
        return {**empty_delivery(), "failed": rejected}
    failed: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for raw in str(receipt.backend_id or "").split(","):
        ref = raw.strip()
        if not ref:
            continue
        resolved = resolve_authorized_resource(
            tenant_id=tenant_id,
            resource_ref=ref,
            allowed_source_ids=allowed_source_ids,
            session=session,
        )
        if not resolved.get("ok"):
            failed.append({"id": ref, "error": str(resolved.get("error") or "resource_not_found")})
            continue
        records.append(dict(resolved.get("resource") or {}))
    return payload_from_records(records, failed=failed)


def attach_send_to_turn(turn: CustomerTurn, receipt: ActionReceipt, *, session: Any | None = None) -> dict[str, Any]:
    payload = payload_from_receipt(tenant_id=turn.tenant_id, receipt=receipt, session=session)
    extra = dict(turn.extra or {})
    extra["resource_delivery"] = payload
    object.__setattr__(turn, "extra", extra)
    dumped = receipt.model_dump()
    dumped.update({"sent": payload.get("sent") or [], "failed": payload.get("failed") or [], "queued": payload["ok"]})
    return dumped


def apply_resource_tool_side_effects(
    turn: CustomerTurn,
    bundle: EvidenceBundle,
    extra: dict[str, Any],
    *,
    evidence_preview: Callable[[EvidenceBundle], Any],
) -> tuple[EvidenceBundle, dict[str, Any], Any, list[dict[str, Any]]]:
    from services.brain.tools.resource_inventory import attach_inventory_evidence

    extra = dict(extra)
    extra["evidence_source_ids"] = [item.source_id for item in bundle.items] + [
        item.evidence_id for item in bundle.items
    ]
    turn.extra["evidence_source_ids"] = extra["evidence_source_ids"]
    inv = turn.extra.get("last_resource_inventory")
    evidence = evidence_preview(bundle)
    if isinstance(inv, dict):
        bundle = attach_inventory_evidence(bundle, inv)
        extra["resource_inventory"] = inv
        evidence = evidence_preview(bundle)
    delivery = turn.extra.get("resource_delivery") if isinstance(turn.extra, dict) else None
    resource_receipts = receipts_from_delivery(delivery) if isinstance(delivery, dict) else []
    if resource_receipts:
        extra["resource_delivery"] = delivery
        extra["receipts"] = resource_receipts
    return bundle, extra, evidence, resource_receipts


def receipts_from_delivery(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in delivery.get("items") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("resource_ref") or item.get("id") or "")
        rows.append(
            {
                "action_type": "send_resource",
                "state": "pending",
                "backend_id": ref,
                "reason": "queued_for_channel",
            }
        )
    return rows


def has_queued_setup_resources(user_data: dict[str, Any] | None) -> bool:
    pending = (user_data or {}).get(_PENDING_KEY)
    return isinstance(pending, dict) and bool(pending.get("ok")) and bool(pending.get("items"))


def has_queued_product_media(user_data: dict[str, Any] | None) -> bool:
    pending = (user_data or {}).get(_PRODUCT_PENDING)
    return isinstance(pending, dict) and bool(pending.get("ok")) and bool(pending.get("items"))


def has_queued_channel_resources(user_data: dict[str, Any] | None) -> bool:
    return has_queued_setup_resources(user_data) or has_queued_product_media(user_data)


def queue_channel_delivery(user_data: dict[str, Any], delivery: dict[str, Any]) -> None:
    """Split Terra send_resource items onto the setup vs product channel queues."""
    if not isinstance(delivery, dict) or not delivery.get("ok"):
        return
    items = [row for row in (delivery.get("items") or []) if isinstance(row, dict)]
    product_items = [row for row in items if str(row.get("source_type") or "") == "product_media"]
    setup_items = [row for row in items if str(row.get("source_type") or "") != "product_media"]
    if product_items:
        user_data[_PRODUCT_PENDING] = {"ok": True, "items": product_items}
    if setup_items:
        user_data[_PENDING_KEY] = {**delivery, "ok": True, "items": setup_items}
