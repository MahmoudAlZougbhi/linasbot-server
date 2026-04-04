# -*- coding: utf-8 -*-
"""
Structured validation contract for BOC / booking flows.
AI supplies structured fields; backend validates and returns machine-readable errors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.booking.schemas import validation_error_response

BOOKING_ERROR_STATUS = "validation_error"

# Codes returned to the model for self-repair (align with prompt + tools).
CODE_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
CODE_INVALID_BODY_PART_IDS = "INVALID_BODY_PART_IDS"
CODE_MISSING_BODY_PART_IDS = "MISSING_BODY_PART_IDS"
CODE_INVALID_SERVICE_ID = "INVALID_SERVICE_ID"
CODE_INVALID_BRANCH_ID = "INVALID_BRANCH_ID"
CODE_INVALID_MACHINE_ID = "INVALID_MACHINE_ID"
CODE_SERVICE_BRANCH_MISMATCH = "SERVICE_BRANCH_MISMATCH"
CODE_BODY_PART_SERVICE_MISMATCH = "BODY_PART_SERVICE_MISMATCH"
CODE_INVALID_DATE = "INVALID_DATE"
CODE_INVALID_TIME = "INVALID_TIME"
CODE_TIME_SLOT_UNAVAILABLE = "TIME_SLOT_UNAVAILABLE"
CODE_CUSTOMER_DATA_INCOMPLETE = "CUSTOMER_DATA_INCOMPLETE"
CODE_TOOL_DATA_REQUIRED = "TOOL_DATA_REQUIRED"
CODE_AMBIGUOUS_BOOKING_REQUEST = "AMBIGUOUS_BOOKING_REQUEST"
CODE_MAX_REPAIR_ATTEMPTS_EXCEEDED = "MAX_REPAIR_ATTEMPTS_EXCEEDED"


def booking_validation_error(
    *,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    missing_fields: Optional[List[str]] = None,
    invalid_fields: Optional[Dict[str, Any]] = None,
    conflicting_fields: Optional[Dict[str, Any]] = None,
    allowed_values: Optional[Dict[str, Any]] = None,
    normalized_values: Optional[Dict[str, Any]] = None,
    slot_validation: Optional[Dict[str, Any]] = None,
    human_readable_reason: str = "",
    handover_to_human: bool = False,
    handover_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Standard booking validation payload for tool output + logs."""
    base = validation_error_response(
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
        conflicting_fields=conflicting_fields,
        allowed_values=allowed_values,
        normalized_values=normalized_values or {},
        human_readable_reason=human_readable_reason or message,
        slot_validation=slot_validation,
    )
    base["status"] = BOOKING_ERROR_STATUS
    base["code"] = code
    base["message"] = message
    base["details"] = dict(details or {})
    if handover_to_human:
        base["handover_to_human"] = True
    if handover_reason:
        base["handover_reason"] = handover_reason
    return base
