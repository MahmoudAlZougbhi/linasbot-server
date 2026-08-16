"""Validate and apply Tera draft_actions. The system never infers fields from raw text."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from services.request_drafts.repository import DraftRepository
from services.request_graphs.service import get_active_graph

MUTABLE_STATUSES = {"collecting", "paused", "ready"}
DEST_TO_TYPE = {"appointment": "APPOINTMENT", "order": "ORDER", "general": "OTHER"}


def _now() -> datetime:
    return datetime.now(UTC)


def _new_draft_id() -> str:
    return f"draft_{uuid.uuid4().hex[:16]}"


def serialize_draft(row: Any) -> dict[str, Any]:
    values = dict(row.values_json or {})
    missing = list(row.missing_json or [])
    collected = [key for key, value in values.items() if value not in (None, "", [], {})]
    return {
        "draft_id": row.draft_id,
        "tenant_id": row.tenant_id,
        "customer_id": row.customer_id,
        "definition_id": row.definition_id,
        "definition_revision": row.definition_revision,
        "destination": row.destination,
        "values": values,
        "missing_fields": missing,
        "items": list(row.items_json or []),
        "linked_entities": list(row.linked_entities_json or []),
        "status": row.status,
        "collected": collected,
        "ready_to_submit": row.status == "ready" and not missing,
        "submitted_request_id": row.submitted_request_id,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
    }


def luna_draft_summary(row: Any) -> dict[str, Any]:
    payload = serialize_draft(row)
    payload.pop("values", None)
    return payload


def _field_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for bucket in ("required_information", "optional_information"):
        for raw in graph.get(bucket) or []:
            if isinstance(raw, dict) and str(raw.get("key") or "").strip():
                out[str(raw["key"])] = raw
    return out


def _required_keys(graph: dict[str, Any]) -> list[str]:
    return [
        str(raw.get("key"))
        for raw in (graph.get("required_information") or [])
        if isinstance(raw, dict) and str(raw.get("key") or "").strip()
    ]


def _missing(graph: dict[str, Any], values: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in _required_keys(graph):
        if values.get(key) in (None, "", [], {}):
            missing.append(key)
    return missing


def _status_for(values: dict[str, Any], graph: dict[str, Any], current: str) -> str:
    if current in {"cancelled", "submitted", "replaced", "definition_deleted", "expired"}:
        return current
    if current == "paused":
        return "paused"
    return "ready" if not _missing(graph, values) else "collecting"


def _coerce(value: Any, value_type: str) -> tuple[Any, str | None]:
    if value in (None, ""):
        return None, None
    if value_type == "integer":
        if isinstance(value, bool):
            return None, "invalid_integer"
        if isinstance(value, int):
            return value, None
        text = str(value).strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text), None
        return None, "invalid_integer"
    return str(value), None


def _fingerprint(action: dict[str, Any]) -> str:
    blob = json.dumps(action, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _trusted_facts(repo: DraftRepository, *, tenant_id: str, customer_id: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    conflicts: set[str] = set()
    for row in repo.list_open(tenant_id=tenant_id, customer_id=customer_id):
        for key, value in dict(row.values_json or {}).items():
            if value in (None, "", [], {}) or key in conflicts:
                continue
            if key in facts and facts[key] != value:
                conflicts.add(key)
                facts.pop(key, None)
                continue
            facts[key] = value
    return facts


def _load_graph(session: Any, *, tenant_id: str, definition_id: str) -> dict[str, Any] | None:
    return get_active_graph(session, tenant_id=tenant_id, definition_id=definition_id)


def _migrate_if_needed(session: Any, row: Any) -> str | None:
    graph = _load_graph(session, tenant_id=row.tenant_id, definition_id=row.definition_id)
    if graph is None:
        if row.status in MUTABLE_STATUSES:
            row.status = "definition_deleted"
            row.updated_at = _now()
        return "definition_deleted"
    new_rev = int(graph.get("revision") or 1)
    if new_rev == int(row.definition_revision):
        return None
    allowed = _field_map(graph)
    values = {key: value for key, value in dict(row.values_json or {}).items() if key in allowed}
    row.values_json = values
    row.missing_json = _missing(graph, values)
    row.definition_revision = new_rev
    row.destination = str(graph.get("destination") or row.destination)
    row.linked_entities_json = list(graph.get("linked_entities") or row.linked_entities_json or [])
    if row.status in {"collecting", "ready"}:
        row.status = _status_for(values, graph, "collecting")
    row.updated_at = _now()
    return "graph_revision_migrated"


def mark_definition_deleted(session: Any, *, tenant_id: str, definition_id: str) -> int:
    repo = DraftRepository(session)
    count = 0
    for row in repo.list_for_definition(tenant_id=tenant_id, definition_id=definition_id):
        if row.status in MUTABLE_STATUSES:
            row.status = "definition_deleted"
            row.updated_at = _now()
            count += 1
    session.flush()
    return count


def apply_draft_action(
    session: Any,
    *,
    tenant_id: str,
    customer_id: str,
    conversation_id: str = "",
    action: dict[str, Any],
    create_request_fn: Any | None = None,
) -> dict[str, Any]:
    name = str(action.get("action") or "").strip()
    repo = DraftRepository(session)
    if name == "create_draft":
        return _create(
            session, repo, tenant_id=tenant_id, customer_id=customer_id, conversation_id=conversation_id, action=action
        )
    draft_id = str(action.get("draft_id") or "").strip()
    if not draft_id:
        return {"ok": False, "error": "draft_id_required"}
    row = repo.get(tenant_id=tenant_id, draft_id=draft_id)
    if row is None or row.customer_id != customer_id:
        return {"ok": False, "error": "draft_not_found"}
    migrated = _migrate_if_needed(session, row)
    fingerprint = _fingerprint(action)
    if row.last_idempotency == fingerprint:
        payload = serialize_draft(row)
        payload["ok"] = True
        payload["unchanged"] = True
        return payload
    if row.status == "definition_deleted" and name != "cancel":
        return {"ok": False, "error": "definition_deleted", "status": row.status}
    if name == "update_fields":
        result = _update_fields(session, row, action)
    elif name == "add_item":
        result = _mutate_item(row, action, mode="add")
    elif name == "remove_item":
        result = _mutate_item(row, action, mode="remove")
    elif name == "replace_item":
        result = _mutate_item(row, action, mode="replace")
    elif name == "pause":
        result = _set_status(row, "paused")
    elif name == "resume":
        result = _resume(session, row)
    elif name == "cancel":
        result = _set_status(row, "cancelled")
    elif name == "submit":
        result = _submit(session, row, action, create_request_fn=create_request_fn)
    else:
        return {"ok": False, "error": "unknown_draft_action"}
    if result.get("ok"):
        row.last_idempotency = fingerprint
        row.updated_at = _now()
        session.flush()
        if migrated:
            result["warning"] = migrated
    return result


def apply_draft_actions(
    session: Any,
    *,
    tenant_id: str,
    customer_id: str,
    conversation_id: str = "",
    actions: list[dict[str, Any]],
    create_request_fn: Any | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for raw in actions[:8]:
        if not isinstance(raw, dict):
            results.append({"ok": False, "error": "invalid_action"})
            continue
        results.append(
            apply_draft_action(
                session,
                tenant_id=tenant_id,
                customer_id=customer_id,
                conversation_id=conversation_id,
                action=raw,
                create_request_fn=create_request_fn,
            )
        )
    session.flush()
    return {"ok": all(item.get("ok") for item in results) if results else True, "results": results, "is_ai": False}


def _create(
    session: Any,
    repo: DraftRepository,
    *,
    tenant_id: str,
    customer_id: str,
    conversation_id: str,
    action: dict[str, Any],
) -> dict[str, Any]:
    definition_id = str(action.get("definition_id") or "").strip()
    graph = _load_graph(session, tenant_id=tenant_id, definition_id=definition_id) if definition_id else None
    if graph is None:
        return {"ok": False, "error": "definition_not_found"}
    values = _trusted_facts(repo, tenant_id=tenant_id, customer_id=customer_id)
    allowed = _field_map(graph)
    values = {key: value for key, value in values.items() if key in allowed}
    missing = _missing(graph, values)
    row = repo.insert(
        tenant_id=tenant_id,
        draft_id=_new_draft_id(),
        customer_id=customer_id,
        conversation_id=conversation_id or None,
        definition_id=definition_id,
        definition_revision=int(graph.get("revision") or 1),
        destination=str(graph.get("destination") or "general"),
        status="ready" if not missing else "collecting",
        values_json=values,
        missing_json=missing,
        items_json=list(action.get("items") or []),
        linked_entities_json=list(graph.get("linked_entities") or []),
    )
    payload = serialize_draft(row)
    payload["ok"] = True
    return payload


def _update_fields(session: Any, row: Any, action: dict[str, Any]) -> dict[str, Any]:
    if row.status not in MUTABLE_STATUSES:
        return {"ok": False, "error": f"draft_{row.status}", "status": row.status}
    graph = _load_graph(session, tenant_id=row.tenant_id, definition_id=row.definition_id)
    if graph is None:
        row.status = "definition_deleted"
        return {"ok": False, "error": "definition_deleted", "status": "definition_deleted"}
    allowed = _field_map(graph)
    raw_updates = action.get("field_updates")
    updates: dict[str, Any] = dict(raw_updates) if isinstance(raw_updates, dict) else {}
    values = dict(row.values_json or {})
    rejected: list[dict[str, str]] = []
    for key, raw_value in updates.items():
        spec = allowed.get(str(key))
        if spec is None:
            rejected.append({"key": str(key), "reason": "unknown_field"})
            continue
        coerced, error = _coerce(raw_value, str(spec.get("value_type") or "string"))
        if error:
            rejected.append({"key": str(key), "reason": error})
            continue
        values[str(key)] = coerced
    row.values_json = values
    row.missing_json = _missing(graph, values)
    row.status = _status_for(values, graph, "collecting")
    payload = serialize_draft(row)
    payload["ok"] = True
    payload["rejected_fields"] = rejected
    return payload


def _item_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("type") or ""), str(item.get("id") or ""))


def _mutate_item(row: Any, action: dict[str, Any], *, mode: str) -> dict[str, Any]:
    if row.status not in MUTABLE_STATUSES:
        return {"ok": False, "error": f"draft_{row.status}", "status": row.status}
    items = [dict(item) for item in list(row.items_json or []) if isinstance(item, dict)]
    if mode == "add":
        item = dict(action.get("item") or {})
        if not _item_key(item)[1]:
            return {"ok": False, "error": "item_id_required"}
        if _item_key(item) not in {_item_key(existing) for existing in items}:
            items.append(item)
    elif mode == "remove":
        target = _item_key(dict(action.get("item") or {"id": action.get("item_id"), "type": action.get("item_type")}))
        items = [item for item in items if _item_key(item) != target]
    else:
        old = _item_key(dict(action.get("from_item") or {"id": action.get("from_id"), "type": action.get("item_type")}))
        new_item = dict(action.get("to_item") or {"id": action.get("to_id"), "type": action.get("item_type")})
        items = [item for item in items if _item_key(item) != old]
        if _item_key(new_item)[1]:
            items.append(new_item)
    row.items_json = items
    payload = serialize_draft(row)
    payload["ok"] = True
    return payload


def _set_status(row: Any, status: str) -> dict[str, Any]:
    if status == "cancelled" and row.status in {"submitted", "definition_deleted"}:
        return {"ok": False, "error": f"draft_{row.status}", "status": row.status}
    if status == "paused" and row.status not in MUTABLE_STATUSES:
        return {"ok": False, "error": f"draft_{row.status}", "status": row.status}
    row.status = status
    payload = serialize_draft(row)
    payload["ok"] = True
    return payload


def _resume(session: Any, row: Any) -> dict[str, Any]:
    if row.status == "definition_deleted":
        return {"ok": False, "error": "definition_deleted", "status": row.status}
    if row.status not in {"paused", "collecting", "ready"}:
        return {"ok": False, "error": f"draft_{row.status}", "status": row.status}
    graph = _load_graph(session, tenant_id=row.tenant_id, definition_id=row.definition_id)
    if graph is None:
        row.status = "definition_deleted"
        return {"ok": False, "error": "definition_deleted"}
    row.status = _status_for(dict(row.values_json or {}), graph, "collecting")
    row.missing_json = _missing(graph, dict(row.values_json or {}))
    payload = serialize_draft(row)
    payload["ok"] = True
    return payload


def _submit(session: Any, row: Any, action: dict[str, Any], create_request_fn: Any | None) -> dict[str, Any]:
    if row.status == "submitted":
        payload = serialize_draft(row)
        payload["ok"] = True
        payload["unchanged"] = True
        return payload
    if row.status == "definition_deleted":
        return {"ok": False, "error": "definition_deleted"}
    graph = _load_graph(session, tenant_id=row.tenant_id, definition_id=row.definition_id)
    if graph is None:
        row.status = "definition_deleted"
        return {"ok": False, "error": "definition_deleted"}
    missing = _missing(graph, dict(row.values_json or {}))
    row.missing_json = missing
    if missing:
        row.status = "collecting"
        return {"ok": False, "error": "incomplete_submission", "missing_fields": missing, "status": "collecting"}
    if bool(graph.get("confirmation_required", True)) and not bool(action.get("confirmed")):
        row.status = "ready"
        return {"ok": False, "error": "confirmation_required", "status": "ready", "ready_to_submit": True}
    snapshot = serialize_draft(row)
    request_id = None
    if create_request_fn is not None:
        created = create_request_fn(snapshot)
        if not created or not created.get("ok"):
            return {"ok": False, "error": str((created or {}).get("error") or "submit_failed"), "draft": snapshot}
        request_id = created.get("request_id")
    row.status = "submitted"
    row.submitted_request_id = str(request_id or "") or None
    payload = serialize_draft(row)
    payload["ok"] = True
    payload["request_type"] = DEST_TO_TYPE.get(str(row.destination), "OTHER")
    if row.destination == "appointment":
        payload["pending_confirmation"] = True
        payload["customer_message_hint"] = "تم إرسال طلب الموعد. الموعد غير مؤكد بعد."
    return payload
