"""Publish, preview, edit, and delete request definition graphs."""

from __future__ import annotations

import uuid
from typing import Any

from services.request_graphs.compiler import GraphCompileResult, compile_request_graph, destination_from_type
from services.request_graphs.repository import RequestGraphRepository


def _metering(compiled: GraphCompileResult, *, operation: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "provider": "openai" if compiled.used_llm else "none",
        "requested_reasoning_effort": compiled.requested_reasoning_effort,
        "effective_reasoning_effort": compiled.effective_reasoning_effort,
        "is_ai": compiled.used_llm,
        "success": True,
    }


def _graph_payload(
    compiled: GraphCompileResult, *, source_item_id: str, definition_id: str, revision: int
) -> dict[str, Any]:
    return {
        "definition_id": definition_id,
        "source_item_id": source_item_id,
        "revision": revision,
        "source_text_hash": compiled.source_text_hash,
        "title": compiled.title,
        "status": "draft",
        "destination": compiled.destination,
        "linked_entities": compiled.linked_entities,
        "required_information": compiled.required_information,
        "optional_information": compiled.optional_information,
        "confirmation_required": compiled.confirmation_required,
        "needs_owner_clarification": compiled.needs_owner_clarification,
        "warnings": compiled.warnings,
        "metering": _metering(compiled, operation="graph_compile"),
    }


def preview_graph(
    *,
    title: str,
    source_text: str,
    destination: str = "appointment",
    linked_entities: list[dict[str, str]] | None = None,
    llm_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compiled = compile_request_graph(
        title=title,
        source_text=source_text,
        destination=destination,
        linked_entities=linked_entities,
        llm_result=llm_result,
    )
    return _graph_payload(compiled, source_item_id="", definition_id="", revision=0) | {
        "used_llm": compiled.used_llm,
    }


def publish_graph(
    session: Any,
    *,
    tenant_id: str,
    source_item_id: str,
    title: str,
    source_text: str,
    destination: str = "appointment",
    linked_entities: list[dict[str, str]] | None = None,
    llm_result: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    compiled = compile_request_graph(
        title=title,
        source_text=source_text,
        destination=destination,
        linked_entities=linked_entities,
        llm_result=llm_result,
    )
    repo = RequestGraphRepository(session)
    existing = repo.get_active_by_source(tenant_id=tenant_id, source_item_id=source_item_id)
    definition_id = existing.definition_id if existing else f"reqdef_{uuid.uuid4().hex[:12]}"
    revision = (existing.revision + 1) if existing else 1
    if existing and existing.source_text_hash == compiled.source_text_hash and existing.status == "active":
        payload = dict(existing.graph_json or {})
        payload["definition_id"] = existing.definition_id
        payload["revision"] = existing.revision
        payload["unchanged"] = True
        payload["duplicate"] = False
        payload["metering"] = _metering(compiled, operation="graph_compile")
        return payload
    if compiled.needs_owner_clarification:
        payload = _graph_payload(
            compiled, source_item_id=source_item_id, definition_id=definition_id, revision=revision
        )
        payload["status"] = "draft"
        return payload
    if not confirm:
        payload = _graph_payload(
            compiled, source_item_id=source_item_id, definition_id=definition_id, revision=revision
        )
        payload["status"] = "preview"
        return payload
    repo.deactivate_source(tenant_id=tenant_id, source_item_id=source_item_id)
    graph_json = _graph_payload(compiled, source_item_id=source_item_id, definition_id=definition_id, revision=revision)
    graph_json["status"] = "active"
    graph_json["metering"] = _metering(compiled, operation="graph_update" if existing else "graph_compile")
    row = repo.insert(
        tenant_id=tenant_id,
        definition_id=definition_id,
        source_item_id=source_item_id,
        revision=revision,
        payload={
            "source_text_hash": compiled.source_text_hash,
            "title": compiled.title,
            "status": "active",
            "destination": compiled.destination,
            "graph_json": graph_json,
            "confirmation_required": compiled.confirmation_required,
            "needs_owner_clarification": compiled.needs_owner_clarification,
        },
        links=compiled.linked_entities,
    )
    session.flush()
    return {**graph_json, "id": row.id, "duplicate": False, "unchanged": False}


def delete_graph(session: Any, *, tenant_id: str, definition_id: str) -> dict[str, Any]:
    repo = RequestGraphRepository(session)
    count = repo.mark_deleted(tenant_id=tenant_id, definition_id=definition_id)
    session.flush()
    from services.request_drafts.engine import mark_definition_deleted

    mark_definition_deleted(session, tenant_id=tenant_id, definition_id=definition_id)
    return {"ok": True, "deleted": count, "definition_id": definition_id, "is_ai": False}


def list_active_graphs(session: Any, *, tenant_id: str) -> list[dict[str, Any]]:
    repo = RequestGraphRepository(session)
    out: list[dict[str, Any]] = []
    for row in repo.list_active(tenant_id=tenant_id):
        payload = dict(row.graph_json or {})
        payload["definition_id"] = row.definition_id
        payload["revision"] = row.revision
        payload["title"] = row.title
        payload["destination"] = row.destination
        payload["status"] = row.status
        payload["source_item_id"] = row.source_item_id
        out.append(payload)
    return out


def get_active_graph(
    session: Any,
    *,
    tenant_id: str,
    definition_id: str = "",
    source_item_id: str = "",
) -> dict[str, Any] | None:
    repo = RequestGraphRepository(session)
    row = None
    if definition_id:
        row = repo.get_active_by_definition(tenant_id=tenant_id, definition_id=definition_id)
    elif source_item_id:
        row = repo.get_active_by_source(tenant_id=tenant_id, source_item_id=source_item_id)
    if row is None:
        return None
    payload = dict(row.graph_json or {})
    payload["definition_id"] = row.definition_id
    payload["revision"] = row.revision
    payload["title"] = row.title
    payload["destination"] = row.destination
    payload["status"] = row.status
    payload["source_item_id"] = row.source_item_id
    return payload


def sync_graphs_from_request_rules(
    session: Any,
    *,
    tenant_id: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for raw in rules:
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        source_item_id = str(raw.get("id") or "").strip()
        if not source_item_id:
            continue
        seen.add(source_item_id)
        title = str(raw.get("name") or raw.get("title") or source_item_id)
        notes = str(raw.get("notes") or "")
        results.append(
            publish_graph(
                session,
                tenant_id=tenant_id,
                source_item_id=source_item_id,
                title=title,
                source_text=f"{title}\n{notes}".strip(),
                destination=destination_from_type(str(raw.get("type") or "")),
                confirm=True,
            )
        )
    repo = RequestGraphRepository(session)
    for row in repo.list_active(tenant_id=tenant_id):
        if row.source_item_id not in seen:
            repo.mark_deleted(tenant_id=tenant_id, definition_id=row.definition_id)
    session.flush()
    return results
