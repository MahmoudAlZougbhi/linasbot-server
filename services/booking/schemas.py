"""Structured shapes for AI extraction and backend validation responses."""

from __future__ import annotations

from typing import Any

from services.booking.constants import BOOKING_TIMEZONE_LABEL


def empty_booking_intent_template() -> dict[str, Any]:
    return {
        "intent": "create_appointment",
        "service_name": None,
        "service_id": None,
        "body_part": None,
        "body_part_ids": None,
        "body_parts_with_sessions": None,
        "machine_name": None,
        "machine_id": None,
        "branch_name": None,
        "branch_id": None,
        "gender": None,
        "customer_name": None,
        "raw_user_date_text": None,
        "raw_user_time_text": None,
        "normalized_date": None,
        "normalized_time": None,
        "time": None,
        "timezone": BOOKING_TIMEZONE_LABEL,
        "calendar_day_intent": None,
        "date_components": None,
        "date": None,
        "missing_fields": [],
        "ambiguities": [],
        "needs_clarification": False,
        "confidence_notes": [],
        "execute_booking": True,
        "phone": None,
        "user_code": None,
    }


def validation_error_response(
    *,
    missing_fields: list[str] | None = None,
    invalid_fields: dict[str, Any] | None = None,
    conflicting_fields: dict[str, Any] | None = None,
    allowed_values: dict[str, Any] | None = None,
    normalized_values: dict[str, Any] | None = None,
    suggested_slots: list[Any] | None = None,
    human_readable_reason: str = "",
    slot_validation: dict[str, Any] | None = None,
    activity_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "success": False,
        "error_type": "validation_error",
        "missing_fields": list(missing_fields or []),
        "invalid_fields": dict(invalid_fields or {}),
        "conflicting_fields": dict(conflicting_fields or {}),
        "allowed_values": dict(allowed_values or {}),
        "normalized_values": dict(normalized_values or {}),
        "suggested_slots": list(suggested_slots or []),
        "human_readable_reason": human_readable_reason,
    }
    if slot_validation:
        out["slot_validation"] = slot_validation
    if activity_trace:
        out["activity_trace"] = activity_trace
    return out


def success_validation_shell(
    *,
    normalized_values: dict[str, Any],
    booking_flow_state: str,
) -> dict[str, Any]:
    return {
        "success": True,
        "error_type": None,
        "booking_flow_state": booking_flow_state,
        "normalized_values": normalized_values,
    }
