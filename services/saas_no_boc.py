"""BOC / LinasLaser Agent CRM is not part of the SaaS product.

Callers that historically talked to boc-lb.com must fail closed here.
No HTTP, no env gate, no hidden clinic fallback.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any

_log = logging.getLogger(__name__)

REPORT_LOG_FILE = "data/reports_log.jsonl"
BOC_NOT_IN_SAAS = "boc_not_in_saas"


def _disabled(operation: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": BOC_NOT_IN_SAAS,
        "message": f"BOC is not in SaaS. No network call was made for {operation}.",
    }


def log_report_event(event_type: str, user_id: str, user_gender: str, details: dict | None = None) -> None:
    """Local ops log only. Does not call BOC."""
    import config

    event_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "user_id": user_id,
        "user_name": config.user_names.get(user_id, "N/A"),
        "user_gender": user_gender,
        "details": details if details else {},
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open(REPORT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
            f.flush()
    except Exception as exc:
        _log.warning("ops report log failed: %s", type(exc).__name__)


async def get_customer_by_phone(**_kwargs: Any) -> dict[str, Any]:
    return _disabled("get_customer_by_phone")


async def check_customer_gender(**_kwargs: Any) -> dict[str, Any]:
    return _disabled("check_customer_gender")


async def create_customer(**_kwargs: Any) -> dict[str, Any]:
    return _disabled("create_customer")


async def send_appointment_reminders(**_kwargs: Any) -> dict[str, Any]:
    out = _disabled("send_appointment_reminders")
    out["data"] = {}
    return out


async def get_customer_appointments(**_kwargs: Any) -> dict[str, Any]:
    out = _disabled("get_customer_appointments")
    out["data"] = []
    return out


async def get_paused_appointments_between_dates(**_kwargs: Any) -> dict[str, Any]:
    out = _disabled("get_paused_appointments_between_dates")
    out["data"] = []
    return out


async def get_missed_appointments(**_kwargs: Any) -> dict[str, Any]:
    out = _disabled("get_missed_appointments")
    out["data"] = []
    return out


async def check_next_appointment(**_kwargs: Any) -> dict[str, Any]:
    return _disabled("check_next_appointment")


async def generate_daily_report_command(**_kwargs: Any) -> None:
    return None
