"""Persist the CM request-rule draft beside the compiled graph.

Save/delete from AI Setup is one tenant edit: draft + graph share one daily-edit slot.
"""

from __future__ import annotations

from typing import Any

from services.cm.storage import put_draft
from services.request_graphs.service import delete_graph, publish_graph

SECTION = "requests_appointments"


class DraftMatchRequired(ValueError):
    code = "if_match_required"


def write_request_draft(
    *,
    tenant_id: str,
    payload: dict[str, Any],
    if_match: str,
    updated_by: str,
) -> dict[str, Any]:
    envelope = put_draft(
        SECTION,
        payload=payload,
        if_match=if_match,
        tenant_id=tenant_id,
        updated_by=updated_by or "unknown",
    )
    return {
        "etag": envelope.etag,
        "revision": envelope.revision,
        "payload": dict(envelope.payload or {}),
    }


def _optional_draft(tenant_id: str, body: dict[str, Any], updated_by: str) -> dict[str, Any] | None:
    payload = body.get("draft_payload")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("draft_payload must be an object")
    if_match = str(body.get("if_match") or "").strip()
    if not if_match:
        raise DraftMatchRequired("If-Match is required when saving the request-rule draft")
    return write_request_draft(
        tenant_id=tenant_id,
        payload=payload,
        if_match=if_match,
        updated_by=updated_by,
    )


def publish_with_optional_draft(
    db: Any,
    *,
    tenant_id: str,
    body: dict[str, Any],
    updated_by: str,
) -> dict[str, Any]:
    draft = _optional_draft(tenant_id, body, updated_by)
    graph = publish_graph(
        db,
        tenant_id=tenant_id,
        source_item_id=str(body.get("source_item_id") or "").strip(),
        title=str(body.get("title") or ""),
        source_text=str(body.get("source_text") or ""),
        destination=str(body.get("destination") or "appointment"),
        linked_entities=list(body.get("linked_entities") or []),
        confirm=bool(body.get("confirm")),
    )
    return {"graph": graph, "draft": draft}


def delete_with_optional_draft(
    db: Any,
    *,
    tenant_id: str,
    body: dict[str, Any],
    updated_by: str,
) -> dict[str, Any]:
    draft = _optional_draft(tenant_id, body, updated_by)
    graph = delete_graph(db, tenant_id=tenant_id, definition_id=str(body.get("definition_id") or "").strip())
    return {**graph, "draft": draft}
