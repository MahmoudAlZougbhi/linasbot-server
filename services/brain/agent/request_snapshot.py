"""Request snapshot for Terra: collected vs remaining, new vs resume vs expired."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.turn import CustomerTurn
from services.brain.profile.store import confirm_candidates, recall_profile
from services.requests.config_loader import requests_capture_active

_CLOSED = {"cancelled", "submitted", "replaced", "definition_deleted", "expired", "completed"}
_OPEN = {"collecting", "paused", "ready", "awaiting_confirmation"}


def _pending_rows(turn: CustomerTurn) -> list[dict[str, Any]]:
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    rows: list[dict[str, Any]] = []
    for row in list(extra.get("pending_actions") or []):
        if isinstance(row, dict):
            rows.append(row)
        elif hasattr(row, "model_dump"):
            rows.append(row.model_dump())
    return rows


def _rule_rows(tenant_id: str) -> tuple[list[dict[str, Any]], str]:
    if not (tenant_id or "").strip():
        return [], ""
    try:
        from services.ai_setup.request_rules import format_request_rules_for_ai
        from services.requests.config_loader import load_published_requests_config
    except Exception:
        return [], ""
    payload = load_published_requests_config(tenant_id) or {}
    if not isinstance(payload, dict):
        return [], ""
    block = format_request_rules_for_ai(payload)
    rules: list[dict[str, Any]] = []
    for raw in payload.get("rules") or []:
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        rules.append(
            {
                "id": str(raw.get("id") or ""),
                "type": str(raw.get("type") or "").upper(),
                "name": str(raw.get("name") or ""),
                "required_fields": [str(x).strip() for x in (raw.get("required_fields") or []) if str(x).strip()],
            }
        )
    return rules, block


def required_fields_for_type(tenant_id: str, request_type: str, rules: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    want = (request_type or "").strip().upper()
    for rule in rules:
        if want and str(rule.get("type") or "").upper() != want:
            continue
        keys.extend(str(item) for item in (rule.get("required_fields") or []) if str(item).strip())
    try:
        from services.brain.actions.request_fields import published_request_fields

        published = published_request_fields(tenant_id, want)
        keys.extend(str(k) for k in (published.get("collected_fields") or {}) if str(k).strip())
    except Exception:
        pass
    return list(dict.fromkeys(keys))


def _draft_buckets(turn: CustomerTurn) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    past: list[dict[str, Any]] = []
    try:
        from db.session import whatsapp_session
        from services.requests.request_drafts.engine import serialize_draft
        from services.requests.request_drafts.repository import DraftRepository

        with whatsapp_session(require=False) as session:
            if session is None:
                return active, past
            repo = DraftRepository(session)
            for row in repo.list_open(tenant_id=turn.tenant_id, customer_id=turn.customer_id or ""):
                active.append(serialize_draft(row))
    except Exception:
        return active, past
    return active, past


def _pending_view(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        raw_fields = row.get("fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        raw_collected = fields.get("collected_fields")
        collected = raw_collected if isinstance(raw_collected, dict) else {}
        filled = {k: v for k, v in collected.items() if str(v or "").strip()}
        missing = [k for k, v in collected.items() if not str(v or "").strip()]
        kind = str(fields.get("request_type") or "").upper()
        out.append(
            {
                "status": "awaiting_confirmation",
                "request_type": kind,
                "title": str(fields.get("title") or ""),
                "collected": filled,
                "missing_fields": missing,
                "kind": "resume_active" if filled or missing else f"new_{kind or 'REQUEST'}",
            }
        )
    return out


def build_request_snapshot(turn: CustomerTurn) -> dict[str, Any]:
    enabled = requests_capture_active(turn.tenant_id)
    rules, rules_block = _rule_rows(turn.tenant_id)
    pending = _pending_view(_pending_rows(turn))
    active, past = _draft_buckets(turn)
    active_kind = ""
    required: list[str] = []
    for row in pending:
        active_kind = str(row.get("request_type") or active_kind)
        required = required_fields_for_type(turn.tenant_id, active_kind, rules)
        row["kind"] = "resume_active"
    for row in active:
        dest = str(row.get("destination") or "")
        mapped = {"appointment": "APPOINTMENT", "order": "ORDER", "live_chat": "HUMAN"}.get(dest, "OTHER")
        active_kind = mapped or active_kind
        required = required_fields_for_type(turn.tenant_id, mapped, rules) or required
        status = str(row.get("status") or "")
        row["request_type"] = mapped
        row["kind"] = "resume_active" if status in _OPEN else ("expired_or_completed" if status in _CLOSED else status)
    for row in past:
        row["kind"] = "expired_or_completed"
    profile = recall_profile(turn.tenant_id, turn.customer_id or "", conversation_id=turn.conversation_id)
    confirm = confirm_candidates(profile, set(required))
    return {
        "module_enabled": bool(enabled),
        "published_rules": rules,
        "published_rules_block": rules_block,
        "pending_confirmation": pending,
        "active_drafts": active,
        "past_requests": past,
        "active_kind": active_kind,
        "required_fields": required,
        "profile_confirm": confirm,
        "nag_policy": "answer_other_topics_first",
        "distinction": "new_ORDER vs new_APPOINTMENT vs resume_active vs expired_or_completed",
    }


def request_policy_notes(state: dict[str, Any]) -> list[str]:
    if not state.get("module_enabled"):
        return []
    notes = [
        "REQUEST_NAG_POLICY: If a draft is open and this inbound is a different question, answer "
        "that question first. Do not re-ask missing fields this turn. When the customer returns to "
        "the booking/order topic, summarize collected vs remaining and allow corrections.",
        "REQUEST_DISTINCTION: new ORDER vs new APPOINTMENT vs resume active draft vs "
        "expired/completed past appointment — do not conflate them.",
        "HUMAN: You may speak the owner-configured hint, then call escalate_to_human. "
        "Do not paste a canned protocol. HUMAN never creates a Requests board card.",
        "PROFILE: Confirm stored required fields with the customer instead of blank re-collect. "
        "If the active request graph does not require a field, do not ask and do not store it.",
    ]
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
        "distinction": state.get("distinction"),
    }
    notes.append(f"REQUEST_STATE:{compact}")
    return notes
