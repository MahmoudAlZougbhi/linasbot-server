"""Draft update/cancel. Material field changes invalidate confirmation."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.confirm import material_fields_changed, next_draft_revision
from services.customer_ai.contracts.actions import ActionProposal, ActionReceipt
from services.requests.service import CustomerRequestsError, CustomerRequestsService


def apply_draft_update(
    *,
    proposal: ActionProposal,
    current_revision: str,
    previous_fields: dict[str, Any] | None = None,
    session: Any | None = None,
    tenant_id: str = "",
    actor_user_id: str = "customer_ai",
) -> ActionReceipt:
    if proposal.expected_revision and proposal.expected_revision != (current_revision or ""):
        return ActionReceipt(
            action_id=f"draft:{proposal.task_id}",
            action_type="update_draft",
            state="rejected",
            reason="version_conflict",
        )
    incoming = dict(proposal.fields.get("collected_fields") or proposal.fields)
    incoming.pop("previous_fields", None)
    incoming.pop("collected_fields", None)
    prior = dict(previous_fields or proposal.fields.get("previous_fields") or {})
    changed = material_fields_changed(prior, incoming)
    new_revision = next_draft_revision(current_revision)
    request_id = str(proposal.target_id or "").strip()
    if request_id and session is not None:
        persisted = _persist_collected(
            session=session,
            tenant_id=tenant_id,
            request_id=request_id,
            expected_revision=proposal.expected_revision or current_revision,
            collected_fields={**prior, **incoming},
            actor_user_id=actor_user_id,
        )
        if persisted is not None:
            return persisted
    return ActionReceipt(
        action_id=f"draft:{proposal.task_id}",
        action_type="update_draft",
        state="success",
        backend_id=request_id,
        revision=new_revision,
        reason="confirmation_invalidated" if changed else "draft_updated",
    )


def cancel_request_or_draft(
    *,
    proposal: ActionProposal,
    session: Any | None = None,
    tenant_id: str = "",
    actor_user_id: str = "customer_ai",
) -> ActionReceipt:
    request_id = str(proposal.target_id or proposal.fields.get("request_id") or "").strip()
    if not request_id:
        return ActionReceipt(
            action_id=f"cancel:{proposal.task_id}",
            action_type="cancel_request",
            state="success",
            reason="draft_cancelled",
            revision=next_draft_revision(proposal.expected_revision),
        )
    if session is None:
        return ActionReceipt(
            action_id=f"cancel:{proposal.task_id}",
            action_type="cancel_request",
            state="failure",
            reason="requests_db_unavailable",
        )
    try:
        version = int(proposal.expected_revision or proposal.fields.get("row_version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version <= 0:
        return ActionReceipt(
            action_id=f"cancel:{proposal.task_id}",
            action_type="cancel_request",
            state="rejected",
            reason="version_conflict",
        )
    try:
        updated = CustomerRequestsService(session).transition_status(
            tenant_id=tenant_id,
            request_id=request_id,
            actor_user_id=actor_user_id or "customer_ai",
            to_status="CANCELLED",
            row_version=version,
            cancellation_reason=str(proposal.fields.get("reason") or "customer_cancelled"),
        )
    except CustomerRequestsError as exc:
        return ActionReceipt(
            action_id=f"cancel:{proposal.task_id}",
            action_type="cancel_request",
            state="failure" if exc.code != "VERSION_CONFLICT" else "rejected",
            reason=exc.code.lower(),
            backend_id=request_id,
        )
    return ActionReceipt(
        action_id=f"cancel:{proposal.task_id}",
        action_type="cancel_request",
        state="success",
        backend_id=str(updated.get("id") or request_id),
        revision=str(updated.get("row_version") or ""),
        reason="cancelled",
    )


def _persist_collected(
    *,
    session: Any,
    tenant_id: str,
    request_id: str,
    expected_revision: str,
    collected_fields: dict[str, Any],
    actor_user_id: str,
) -> ActionReceipt | None:
    try:
        version = int(expected_revision or 0)
    except (TypeError, ValueError):
        return ActionReceipt(
            action_id=f"draft:{request_id}",
            action_type="update_draft",
            state="rejected",
            reason="version_conflict",
            backend_id=request_id,
        )
    if version <= 0:
        return None
    try:
        service = CustomerRequestsService(session)
        row = service._lock_version(tenant_id, request_id, version)
        row.collected_fields = collected_fields
        row.row_version += 1
        service.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="draft_update",
            actor_kind="ai",
            actor_user_id=actor_user_id,
            payload={"fields": sorted(collected_fields)},
        )
        session.flush()
        return ActionReceipt(
            action_id=f"draft:{request_id}",
            action_type="update_draft",
            state="success",
            backend_id=request_id,
            revision=str(row.row_version),
            reason="draft_updated",
        )
    except CustomerRequestsError as exc:
        return ActionReceipt(
            action_id=f"draft:{request_id}",
            action_type="update_draft",
            state="rejected" if exc.code == "VERSION_CONFLICT" else "failure",
            reason=exc.code.lower(),
            backend_id=request_id,
        )
    except Exception:
        return None
