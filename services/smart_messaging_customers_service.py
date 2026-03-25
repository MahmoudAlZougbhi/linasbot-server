"""
Single source of truth for Smart Messaging dashboard: customer lists and counts.
All data comes from external/calendar APIs only. Uses timezone Asia/Beirut (+02:00).
Counts = len(customers) so count and list can never be out of sync; no negative counts.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from services.api_integrations import send_appointment_reminders
from services.smart_messaging_catalog import (
    TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS,
    normalize_template_id,
)
from services.template_schedule_service import template_schedule_service
from utils.phone_utils import normalize_phone

# Lebanon timezone for all date logic
BEIRUT_TZ = "Asia/Beirut"


def _now_beirut() -> datetime:
    if ZoneInfo:
        return datetime.now(ZoneInfo(BEIRUT_TZ))
    return datetime.now()


def _parse_api_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    formats = (
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s[:19] if len(s) > 19 else s, fmt)
        except ValueError:
            continue
    return None


def _extract_appointments(result: Dict[str, Any]) -> List[Dict]:
    if not isinstance(result, dict) or not result.get("success"):
        return []
    data = result.get("data", {})
    if isinstance(data, dict):
        return data.get("appointments", []) or []
    if isinstance(data, list):
        return data
    return []


def _apt_to_customer_row(
    apt: Dict,
    category: str,
    reason: str,
    appointment_id: Any = None,
    apt_date: str = "",
    apt_time: str = "",
    details: str = "",
    action_state: str = "pending",
) -> Dict[str, Any]:
    """Build one customer row for dashboard: status, customer, reason, type, date, time, details, action."""
    apt_details = apt.get("appointment_details") or {}
    if isinstance(apt_details, dict):
        apt_id = apt_details.get("id") or apt.get("appointment_id") or appointment_id
        date_str = apt_details.get("date")
        if date_str:
            dt = _parse_api_datetime(date_str)
            if dt:
                apt_date = apt_date or dt.strftime("%Y-%m-%d")
                apt_time = apt_time or dt.strftime("%H:%M")
        service_name = apt_details.get("service", "جلسة ليزر")
        branch_name = apt_details.get("branch", "الفرع الرئيسي")
        details = details or f"{service_name} @ {branch_name}"
    else:
        apt_id = apt.get("id") or apt.get("appointment_id") or appointment_id
        service_name = apt.get("service", "جلسة ليزر")
        branch_name = apt.get("branch", "الفرع الرئيسي")
        details = details or f"{service_name} @ {branch_name}"

    phone_raw = apt.get("phone", "")
    phone = normalize_phone(phone_raw) if phone_raw else ""
    if not phone and phone_raw:
        phone = str(phone_raw).strip()

    return {
        "customer_name": apt.get("name") or "Unknown",
        "phone": phone,
        "appointment_id": str(apt_id) if apt_id is not None else None,
        "status": apt.get("status", ""),
        "type": category,
        "reason": reason,
        "date": apt_date,
        "time": apt_time,
        "details": details,
        "action_state": action_state,
    }


async def _resolve_customer_name(phone: str, fallback_name: str) -> str:
    """Resolve customer name from external system if available."""
    if not phone or fallback_name and fallback_name != "Unknown":
        return fallback_name or "Unknown"
    try:
        from services.customer_identity_service import resolve_customer_from_external
        normalized = normalize_phone(phone)
        if not normalized:
            return fallback_name or "Unknown"
        result = await resolve_customer_from_external(normalized)
        if result.get("name"):
            return result["name"]
    except Exception:
        pass
    return fallback_name or "Unknown"


async def get_reminder_24h_customers() -> List[Dict[str, Any]]:
    """
    Reminders (Daily = for TOMORROW).
    Include appointments scheduled for tomorrow, status = AVAILABLE (or equivalent).
    """
    now = _now_beirut()
    tomorrow = (now.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    result = await send_appointment_reminders(date=tomorrow, status="Available")
    if not result.get("success"):
        result = await send_appointment_reminders(date=tomorrow)
    appointments = _extract_appointments(result)
    rows = []
    for apt in appointments:
        status_raw = str(apt.get("status", "")).strip()
        if status_raw and status_raw.lower() not in ("available", "confirmed", "scheduled", ""):
            continue
        apt_details = apt.get("appointment_details") or {}
        date_str = apt_details.get("date") if isinstance(apt_details, dict) else apt.get("date")
        apt_dt = _parse_api_datetime(date_str)
        apt_date = apt_dt.strftime("%Y-%m-%d") if apt_dt else tomorrow
        apt_time = apt_dt.strftime("%H:%M") if apt_dt else ""
        if apt_date != tomorrow:
            continue
        row = _apt_to_customer_row(
            apt, "reminder_24h", "24-Hour Reminder",
            apt_date=apt_date, apt_time=apt_time, action_state="pending",
        )
        if row.get("phone"):
            row["customer_name"] = await _resolve_customer_name(row["phone"], row["customer_name"])
            rows.append(row)
    return rows


async def get_post_session_feedback_customers() -> List[Dict[str, Any]]:
    """
    Post-session feedback: today's appointments with status Done, where now >= slot + delayHours
    (same rule as daily_template_dispatcher.run_post_session_feedback_delayed).
    """
    now = _now_beirut()
    schedules = template_schedule_service.get_all_schedules()
    cfg = schedules.get("thank_you_message_sent_after_session", {})
    try:
        delay_h = float(cfg.get("delayHours", 3))
    except (TypeError, ValueError):
        delay_h = 3.0
    delay_h = max(0.5, min(72.0, delay_h))

    today_d = now.date()
    today_str = today_d.strftime("%Y-%m-%d")
    yesterday_str = (today_d - timedelta(days=1)).strftime("%Y-%m-%d")
    merged: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for day_str in (today_str, yesterday_str):
        result = await send_appointment_reminders(date=day_str, status="Done")
        if not result.get("success"):
            result = await send_appointment_reminders(date=day_str)
        for apt in _extract_appointments(result):
            apt_details = apt.get("appointment_details") or {}
            aid = apt_details.get("id") if isinstance(apt_details, dict) else None
            ph = apt.get("phone")
            key = (str(aid or ""), str(ph or ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(apt)
    appointments = merged
    rows = []
    for apt in appointments:
        status_raw = str(apt.get("status", "")).strip().lower()
        if status_raw and status_raw not in ("done", "completed"):
            continue
        apt_details = apt.get("appointment_details") or {}
        date_str = apt_details.get("date") if isinstance(apt_details, dict) else apt.get("date")
        apt_dt = _parse_api_datetime(date_str)
        if not apt_dt:
            continue
        if now.tzinfo:
            if apt_dt.tzinfo is None:
                apt_dt = apt_dt.replace(tzinfo=now.tzinfo)
            else:
                apt_dt = apt_dt.astimezone(now.tzinfo)
        elif apt_dt.tzinfo is not None:
            apt_dt = apt_dt.replace(tzinfo=None)
        if apt_dt.date() < now.date() - timedelta(days=1):
            continue
        if now < apt_dt + timedelta(hours=delay_h):
            continue
        apt_date = apt_dt.strftime("%Y-%m-%d")
        apt_time = apt_dt.strftime("%H:%M")
        row = _apt_to_customer_row(
            apt, "thank_you_message_sent_after_session", "thank_you_message_sent_after_session",
            apt_date=apt_date, apt_time=apt_time, action_state="pending",
        )
        if row.get("phone"):
            row["customer_name"] = await _resolve_customer_name(row["phone"], row["customer_name"])
            rows.append(row)
    return rows


async def get_session_feedback_customers() -> List[Dict[str, Any]]:
    """
    Meta template session_feedback (1 var: customer_name): appointments YESTERDAY, status = DONE.
    Sent once per day at the configured schedule time (not delay-based).
    """
    now = _now_beirut()
    yesterday = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = await send_appointment_reminders(date=yesterday, status="Done")
    if not result.get("success"):
        result = await send_appointment_reminders(date=yesterday)
    appointments = _extract_appointments(result)
    rows = []
    for apt in appointments:
        status_raw = str(apt.get("status", "")).strip().lower()
        if status_raw and status_raw not in ("done", "completed"):
            continue
        apt_details = apt.get("appointment_details") or {}
        date_str = apt_details.get("date") if isinstance(apt_details, dict) else apt.get("date")
        apt_dt = _parse_api_datetime(date_str)
        apt_date = apt_dt.strftime("%Y-%m-%d") if apt_dt else yesterday
        apt_time = apt_dt.strftime("%H:%M") if apt_dt else ""
        row = _apt_to_customer_row(
            apt, "session_feedback", "session_feedback",
            apt_date=apt_date, apt_time=apt_time, action_state="pending",
        )
        if row.get("phone"):
            row["customer_name"] = await _resolve_customer_name(row["phone"], row["customer_name"])
            rows.append(row)
    return rows


async def get_missed_yesterday_customers() -> List[Dict[str, Any]]:
    """
    Missed Yesterday: appointment_date = YESTERDAY, status = Available (NOT Done).
    Customers who had an appointment yesterday but it was not completed.
    """
    now = _now_beirut()
    yesterday = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = await send_appointment_reminders(date=yesterday, status="Available")
    if not result.get("success"):
        result = await send_appointment_reminders(date=yesterday)
    appointments = _extract_appointments(result)
    rows = []
    for apt in appointments:
        status_raw = str(apt.get("status", "")).strip().lower()
        if status_raw and status_raw not in ("available", "confirmed", "scheduled"):
            continue
        apt_details = apt.get("appointment_details") or {}
        date_str = apt_details.get("date") if isinstance(apt_details, dict) else apt.get("date")
        apt_dt = _parse_api_datetime(date_str)
        apt_date = apt_dt.strftime("%Y-%m-%d") if apt_dt else yesterday
        apt_time = apt_dt.strftime("%H:%M") if apt_dt else ""
        if apt_date != yesterday:
            continue
        row = _apt_to_customer_row(
            apt, "missed_yesterday", "Missed Yesterday",
            apt_date=apt_date, apt_time=apt_time, action_state="pending",
        )
        if row.get("phone"):
            row["customer_name"] = await _resolve_customer_name(row["phone"], row["customer_name"])
            rows.append(row)
    return rows


async def get_twenty_day_followup_customers() -> List[Dict[str, Any]]:
    """
    One Month Follow Up (Meta: sent_17_days_after_last_session_new, 3 vars): appointment_date = TODAY - 17 days, status = Done.
    Include all such customers; do NOT exclude those with future appointments.
    """
    now = _now_beirut()
    target_day = (now.date() - timedelta(days=TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    result = await send_appointment_reminders(date=target_day, status="Done")
    if not result.get("success"):
        result = await send_appointment_reminders(date=target_day)
    appointments = _extract_appointments(result)
    rows = []
    seen_phones = set()
    for apt in appointments:
        status_raw = str(apt.get("status", "")).strip().lower()
        if status_raw and status_raw not in ("done", "completed"):
            continue
        phone_raw = apt.get("phone", "")
        phone = normalize_phone(phone_raw) if phone_raw else ""
        if not phone and phone_raw:
            phone = str(phone_raw).strip()
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)
        row = _apt_to_customer_row(
            apt, "sent_17_days_after_last_session_new", "sent_17_days_after_last_session_new",
            apt_date=target_day, apt_time="", action_state="pending",
        )
        row["phone"] = phone
        row["customer_name"] = await _resolve_customer_name(phone, row["customer_name"])
        rows.append(row)
    return rows


_CATEGORY_FETCHERS = {
    "reminder_24h": get_reminder_24h_customers,
    "thank_you_message_sent_after_session": get_post_session_feedback_customers,
    "session_feedback": get_session_feedback_customers,
    "missed_yesterday": get_missed_yesterday_customers,
    "sent_17_days_after_last_session_new": get_twenty_day_followup_customers,
}


async def get_customers_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Returns list of customers for a given category (source of truth from APIs).
    category: reminder_24h | thank_you_message_sent_after_session | session_feedback | missed_yesterday | sent_17_days_after_last_session_new
    """
    canonical = normalize_template_id(category)
    fetcher = _CATEGORY_FETCHERS.get(canonical)
    if not fetcher:
        return []
    return await fetcher()


async def get_all_counts_and_customers() -> Dict[str, Any]:
    """
    Single source of truth: fetch all categories in parallel and return counts + lists.
    counts[key] = len(customers[key]); never negative.
    """
    categories = list(_CATEGORY_FETCHERS.keys())
    results = await asyncio.gather(*[_CATEGORY_FETCHERS[c]() for c in categories])
    counts = {}
    customers_by_category = {}
    for cat, customers in zip(categories, results):
        customers = customers or []
        counts[cat] = max(0, len(customers))
        customers_by_category[cat] = customers
    counts["sent_for_pause"] = 0
    counts["whatsapp_lead_no_booking"] = 0
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "customers_by_category": customers_by_category,
    }
