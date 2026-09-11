"""Shared daily-edit reservation for write APIs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.responses import JSONResponse

from services.membership.daily_edits import (
    DailyEditLimitError,
    commit_edit,
    decision_payload,
    operation_id,
    payload_hash,
    release_edit,
    reserve_edit,
)

LIMIT_MESSAGE_EN = "You've reached today's AI Setup update limit. Try again tomorrow."
LIMIT_MESSAGE_AR = "وصلت للحدّ اليومي لتعديلات إعدادات الذكاء الاصطناعي. جرّب مجدداً بكرا."
SAFETY_EDIT_KINDS = frozenset(
    {
        "cm:unpublish",
        "faq:archive",
        "cm:emergency-disable",
        "privacy:delete",
        "safety:handoff",
        "safety:opt-out",
        "safety:disconnect",
    }
)


def limit_response(exc: DailyEditLimitError) -> JSONResponse:
    body = decision_payload(exc.decision)
    reset_at = str(body.get("reset_at") or "")
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": body["code"],
            "message": f"{LIMIT_MESSAGE_EN} Resets at {reset_at}." if reset_at else LIMIT_MESSAGE_EN,
            "message_ar": f"{LIMIT_MESSAGE_AR} يعاد الضبط عند {reset_at}." if reset_at else LIMIT_MESSAGE_AR,
            **body,
        },
        headers={"Retry-After": "3600"},
    )


@contextmanager
def guarded_cm_write(*, tenant_id: str, section: str, current: object, payload: object) -> Iterator[str | None]:
    from services.membership.daily_edits import reserve_cm_section

    if payloads_equivalent(current, payload):
        yield None
        return
    op = reserve_cm_section(tenant_id=tenant_id, section=section, payload=payload)
    if not op:
        yield None
        return
    committed = False
    try:
        yield op
        commit_edit(tenant_id=tenant_id, operation_id=op)
        committed = True
    finally:
        if not committed:
            release_edit(tenant_id=tenant_id, operation_id=op)


def is_safety_edit(kind: str, *, safety: bool = False) -> bool:
    text = str(kind or "").strip()
    return safety or text in SAFETY_EDIT_KINDS or text.startswith("safety:")


@contextmanager
def guarded_edit(*, tenant_id: str, kind: str, payload: object, safety: bool = False) -> Iterator[str]:
    if is_safety_edit(kind, safety=safety):
        yield f"safety:{kind}"
        return
    op = operation_id(tenant_id=tenant_id, kind=kind, payload_hash=payload_hash(payload))
    reserve_edit(tenant_id=tenant_id, operation_id=op)
    committed = False
    try:
        yield op
        commit_edit(tenant_id=tenant_id, operation_id=op)
        committed = True
    finally:
        if not committed:
            release_edit(tenant_id=tenant_id, operation_id=op)


def payloads_equivalent(left: Any, right: Any) -> bool:
    return payload_hash(left) == payload_hash(right)
