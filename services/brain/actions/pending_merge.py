"""Merge collected_fields into the stored pending draft. Does not start a new request."""

from __future__ import annotations

from typing import Any

from services.brain.actions.pending import attach_confirmation
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import load_conversation

_SKIP = frozenset({"request_type", "title", "draft_id", "request_id", "previous_fields", "task_id"})


def pending_rows(turn: CustomerTurn) -> list[dict[str, Any]]:
    stored = load_conversation(turn.tenant_id, turn.conversation_id) or {}
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    rows = list(stored.get("pending") or extra.get("pending_actions") or [])
    return [row for row in rows if isinstance(row, dict)]


def _incoming_collected(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("collected_fields")
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if str(v or "").strip()}
    return {str(k): v for k, v in fields.items() if k not in _SKIP and str(v or "").strip()}


def _kind(row: dict[str, Any]) -> str:
    raw = row.get("fields")
    fields = raw if isinstance(raw, dict) else {}
    return str(fields.get("request_type") or "").upper()


def apply_pending_field_update(turn: CustomerTurn, fields: dict[str, Any]) -> ActionProposalSet | None:
    """Fill/correct collected_fields on the matching pending draft. None if no match."""
    rows = pending_rows(turn)
    if not rows:
        return None
    want = str(fields.get("request_type") or "").upper()
    incoming = _incoming_collected(fields)
    proposals: list[ActionProposal] = []
    for row in rows:
        kind = _kind(row)
        if want and kind and kind != want:
            continue
        raw = dict(row.get("fields") or {})
        payload = {
            **row,
            "fields": {**raw, "request_type": kind or want, "collected_fields": incoming},
        }
        try:
            proposals.append(ActionProposal.model_validate(payload))
        except Exception:
            continue
    if not proposals:
        return None
    return attach_confirmation(turn, ActionProposalSet(actions=proposals))


def keep_existing_pending(turn: CustomerTurn) -> ActionProposalSet | None:
    """Return the stored pending set without replacing it. None if empty/invalid."""
    proposals: list[ActionProposal] = []
    for row in pending_rows(turn):
        try:
            proposals.append(ActionProposal.model_validate(row))
        except Exception:
            continue
    if not proposals:
        return None
    return ActionProposalSet(actions=proposals)


def resume_pending_or_keep(turn: CustomerTurn, fields: dict[str, Any]) -> ActionProposalSet | None:
    """Same-type start/update resumes collected_fields. Other-type start does not wipe pending."""
    rows = pending_rows(turn)
    if not rows:
        return None
    want = str(fields.get("request_type") or "").upper()
    if any(not want or _kind(row) == want for row in rows):
        updated = apply_pending_field_update(turn, fields)
        if updated is not None:
            return updated
    return keep_existing_pending(turn)
