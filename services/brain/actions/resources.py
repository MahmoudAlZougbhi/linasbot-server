"""send_resource by authorized ID. Invented URLs never resolve."""

from __future__ import annotations

from typing import Any

from services.ai_setup.setup_resources import resolve_published_resource
from services.brain.contracts.actions import ActionProposal, ActionReceipt
from services.brain.visual import visual_path_for_resource


def looks_like_invented_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://") or "://" in text


def resolve_authorized_resource(
    *,
    tenant_id: str,
    resource_ref: str,
    allowed_source_ids: list[str] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    ref = str(resource_ref or "").strip()
    if not ref:
        return {"ok": False, "error": "resource_ref_required"}
    if looks_like_invented_url(ref):
        return {"ok": False, "error": "invented_url"}
    published = resolve_published_resource(
        tenant_id=tenant_id,
        resource_ref=ref,
        allowed_source_ids=allowed_source_ids,
    )
    if published.get("ok"):
        record = dict(published.get("resource") or {})
        record["visual_path"] = visual_path_for_resource(has_authorized_id=True)
        return {"ok": True, "resource": record, "kind": "published"}
    product = _resolve_product_media(
        session=session,
        tenant_id=tenant_id,
        media_id=ref,
        allowed_source_ids=allowed_source_ids,
    )
    if product is not None:
        return {"ok": True, "resource": product, "kind": "product_media"}
    return {"ok": False, "error": published.get("error") or "resource_not_found"}


def _unique_refs(*values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, list):
            parts = raw
        else:
            parts = [raw]
        for item in parts:
            ref = str(item or "").strip()
            if not ref or ref in seen:
                continue
            seen.add(ref)
            out.append(ref)
    return out


def _proposal_refs(proposal: ActionProposal) -> list[str]:
    fields = proposal.fields or {}
    return _unique_refs(
        proposal.target_id,
        fields.get("resource_ref"),
        fields.get("resource_id"),
        fields.get("resource_ids"),
        fields.get("ids"),
    )


def _wanted_kind(proposal: ActionProposal) -> str:
    return (
        str((proposal.fields or {}).get("kind") or (proposal.fields or {}).get("resource_type") or "").strip().lower()
    )


def _allowed_source_ids(proposal: ActionProposal) -> list[str] | None:
    allowed = (proposal.fields or {}).get("allowed_source_ids")
    if not isinstance(allowed, list):
        return None
    return [str(item) for item in allowed if str(item).strip()]


def _refs_for_kind(tenant_id: str, kind: str, allowed_ids: list[str] | None) -> list[str]:
    if not kind or not allowed_ids:
        return []
    from services.ai_setup.setup_resources import index_published_resources

    try:
        index = index_published_resources(tenant_id)
    except Exception:
        return []
    wanted = set(allowed_ids)
    refs: list[str] = []
    for ref, record in index.items():
        if str(record.get("resource_type") or "") != kind:
            continue
        sid = str(record.get("source_item_id") or "")
        if sid in wanted or any(sid.endswith(f":{item}") or item in sid for item in wanted):
            refs.append(ref)
    return refs


def send_resource(
    *,
    tenant_id: str,
    proposal: ActionProposal,
    session: Any | None = None,
) -> ActionReceipt:
    refs = _proposal_refs(proposal)
    kind = _wanted_kind(proposal)
    allowed_ids = _allowed_source_ids(proposal)
    if any(looks_like_invented_url(ref) for ref in refs):
        return ActionReceipt(
            action_id=f"resource:{proposal.task_id}",
            action_type="send_resource",
            state="rejected",
            reason="invented_url",
        )
    if not refs and kind:
        refs = _refs_for_kind(tenant_id, kind, allowed_ids)
    if not refs:
        return ActionReceipt(
            action_id=f"resource:{proposal.task_id}",
            action_type="send_resource",
            state="rejected",
            reason="resource_ref_required",
        )
    accepted: list[str] = []
    last_error = "resource_not_found"
    for ref in refs:
        resolved = resolve_authorized_resource(
            tenant_id=tenant_id,
            resource_ref=ref,
            allowed_source_ids=allowed_ids,
            session=session,
        )
        if not resolved.get("ok"):
            last_error = str(resolved.get("error") or last_error)
            continue
        resource = dict(resolved.get("resource") or {})
        got_kind = str(resource.get("resource_type") or "")
        if kind and got_kind and got_kind != kind:
            last_error = "kind_mismatch"
            continue
        accepted.append(str(resource.get("resource_ref") or ref))
    if not accepted:
        return ActionReceipt(
            action_id=f"resource:{proposal.task_id}",
            action_type="send_resource",
            state="rejected",
            reason=last_error,
        )
    joined = ",".join(accepted)
    return ActionReceipt(
        action_id=f"resource:{proposal.task_id}",
        action_type="send_resource",
        state="pending",
        backend_id=joined,
        reason="queued_for_channel",
        idempotency_key=str(proposal.fields.get("idempotency_key") or f"{tenant_id}:{joined}:{proposal.task_id}"),
    )


def _resolve_product_media(
    *,
    session: Any | None,
    tenant_id: str,
    media_id: str,
    allowed_source_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    from services.products.authorized_media import resolve_customer_product_resource

    record = resolve_customer_product_resource(
        tenant_id=tenant_id,
        resource_ref=media_id,
        allowed_source_ids=allowed_source_ids,
        session=session,
    )
    if record is None:
        return None
    record["visual_path"] = visual_path_for_resource(has_authorized_id=True)
    return record
