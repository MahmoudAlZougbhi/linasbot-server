"""Pending high-impact confirmations (CM draft approve, etc.).

Confirm via the Approve UI button and/or an explicit `confirm_tool` call — never
via ok/موافق keyword auto-confirm.
"""

from __future__ import annotations

import time
from typing import Any

_PENDING_MAX_AGE_SEC = 6 * 3600


def _token_from_tool_call(tc: dict[str, Any]) -> str | None:
    if not isinstance(tc, dict):
        return None
    raw = tc.get("confirmation_token")
    if not raw and isinstance(tc.get("data"), dict):
        raw = tc["data"].get("confirmation_token")
    token = str(raw or "").strip()
    if not token:
        return None
    if token.startswith("approve_") or token == "publish_cm":
        return token
    return None


def pending_confirm_from_messages(messages: list[dict[str, Any]] | None) -> str | None:
    """Walk recent assistant tool_calls for the latest confirmation_token."""
    for m in reversed(list(messages or [])):
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tc in reversed(tool_calls):
            if not isinstance(tc, dict):
                continue
            if tc.get("requires_confirmation") is False:
                continue
            token = _token_from_tool_call(tc)
            if token:
                return token
    return None


def _latest_cm_token(*, tenant_id: str, user_id: str, now: float) -> tuple[float, str] | None:
    from services.owner_copilot.cm_approval import cm_patch_proposal_store

    prop = cm_patch_proposal_store.latest_pending(tenant_id=tenant_id, user_id=user_id)
    if prop is None:
        return None
    if now - float(prop.created_at or 0) > _PENDING_MAX_AGE_SEC:
        return None
    return (float(prop.created_at or 0), f"approve_cm_patch:{prop.id}")


def _latest_diagnosis_token(*, tenant_id: str, user_id: str, now: float) -> tuple[float, str] | None:
    from services.owner_copilot.diagnosis import diagnosis_proposal_store

    prop = diagnosis_proposal_store.latest_pending(tenant_id=tenant_id, user_id=user_id)
    if prop is None:
        return None
    if now - float(prop.created_at or 0) > _PENDING_MAX_AGE_SEC:
        return None
    return (float(prop.created_at or 0), f"approve_diagnosis_fix:{prop.id}")


def _latest_smart_answer_token(*, tenant_id: str, user_id: str, now: float) -> tuple[float, str] | None:
    from services.owner_copilot.tools_faq import smart_answer_proposal_store

    prop = smart_answer_proposal_store.latest_pending(tenant_id=tenant_id, user_id=user_id)
    if prop is None:
        return None
    if now - float(prop.created_at or 0) > _PENDING_MAX_AGE_SEC:
        return None
    return (float(prop.created_at or 0), f"approve_smart_answer:{prop.id}")


def pending_confirm_from_stores(*, tenant_id: str, user_id: str) -> str | None:
    """Most recent pending proposal across CM / diagnosis / Smart Answer stores."""
    now = time.time()
    candidates: list[tuple[float, str]] = []
    for finder in (_latest_cm_token, _latest_diagnosis_token, _latest_smart_answer_token):
        hit = finder(tenant_id=tenant_id, user_id=user_id, now=now)
        if hit:
            candidates.append(hit)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def resolve_pending_confirm_token(
    *,
    tenant_id: str,
    user_id: str,
    messages: list[dict[str, Any]] | None = None,
) -> str | None:
    """Prefer token from conversation tool_calls; else latest pending proposal store."""
    from_msgs = pending_confirm_from_messages(messages)
    if from_msgs:
        return from_msgs
    return pending_confirm_from_stores(tenant_id=tenant_id, user_id=user_id)
