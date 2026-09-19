"""Terra POLICY notes for request continuity and HUMAN owner hints. Not customer copy."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.turn import CustomerTurn

REQUEST_NAG_POLICY = (
    "REQUEST_NAG_POLICY: If a draft is open and this inbound is a different question, answer "
    "that question first. Do not re-ask collected fields. Do not chase missing fields this turn. "
    "A light one-line reminder is optional only if it fits; otherwise stay silent on the draft. "
    "When the customer returns to the booking/order, resume the same pending draft: summarize "
    "collected vs remaining, never start a second draft of the same type, never re-ask filled keys."
)

REQUEST_DISTINCTION = (
    "REQUEST_DISTINCTION: new ORDER vs new APPOINTMENT vs resume active draft vs "
    "expired/completed past appointment — do not conflate them."
)

HUMAN_HINT_POLICY = (
    "HUMAN_HINT: Owner HUMAN notes are instructions for you, not a script to paste and not "
    "a canned system reply. Author natural customer-facing wording from the hint, then call "
    "escalate_to_human. Runtime executes Live Chat. Only claim a transfer if RECEIPTS include "
    "escalate_to_human success. If the receipt is failure or unknown, do not tell the customer "
    "they were connected. HUMAN never creates a Requests board card."
)

PROFILE_POLICY = (
    "PROFILE: Confirm stored required fields with the customer instead of blank re-collect. "
    "If the active request graph does not require a field, do not ask and do not store it."
)

_OPEN_DRAFT_NOTE = (
    "A request draft is open. Do not claim it was submitted. "
    "Do not re-ask collected fields. Do not nag missing fields on a different question."
)


def request_policy_notes(state: dict[str, Any]) -> list[str]:
    if not state.get("module_enabled"):
        return []
    notes = [REQUEST_NAG_POLICY, REQUEST_DISTINCTION, HUMAN_HINT_POLICY, PROFILE_POLICY]
    hints = [row for row in (state.get("human_hints") or []) if isinstance(row, dict)]
    if hints:
        packed = [
            {
                "id": row.get("id") or "",
                "name": row.get("name") or "",
                "hint": row.get("hint") or "",
            }
            for row in hints
            if str(row.get("hint") or "").strip()
        ]
        if packed:
            notes.append(f"HUMAN_OWNER_HINTS:{packed}")
    block = str(state.get("published_rules_block") or "").strip()
    if block:
        notes.append(block)
    compact = {
        "active_kind": state.get("active_kind") or "",
        "pending": state.get("pending_confirmation") or [],
        "active_drafts": [
            {
                "draft_id": row.get("draft_id"),
                "status": row.get("status"),
                "kind": row.get("kind"),
                "request_type": row.get("request_type"),
                "collected": row.get("collected") or row.get("values"),
                "missing_fields": row.get("missing_fields"),
            }
            for row in (state.get("active_drafts") or [])
            if isinstance(row, dict)
        ],
        "past": [{"status": row.get("status"), "kind": row.get("kind")} for row in (state.get("past_requests") or [])],
        "required_fields": state.get("required_fields") or [],
        "profile_confirm": state.get("profile_confirm") or {},
        "human_hints": state.get("human_hints") or [],
        "distinction": state.get("distinction"),
    }
    notes.append(f"REQUEST_STATE:{compact}")
    return notes


def policy_notes_for_turn(turn: CustomerTurn, *, fallback_tenant_notes: list[str] | None = None) -> list[str]:
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    state = extra.get("request_state")
    if isinstance(state, dict) and state.get("module_enabled"):
        notes = request_policy_notes(state)
    else:
        notes = list(fallback_tenant_notes or [])
    if extra.get("awaiting_confirmation") and not any("REQUEST_NAG_POLICY" in item for item in notes):
        notes.append(_OPEN_DRAFT_NOTE)
    return notes
