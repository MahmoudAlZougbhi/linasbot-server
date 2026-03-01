"""
Daily fixed-time dispatcher for smart messaging templates.
"""

import json
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from services.api_integrations import get_customer_appointments, send_appointment_reminders
from services.message_logs_service import message_logs_service
from services.smart_messaging import smart_messaging
from services.smart_messaging_catalog import DAILY_TEMPLATE_IDS, normalize_template_id
from services.template_schedule_service import template_schedule_service
from services.user_persistence_service import user_persistence

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None


def _normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("+", "").replace(" ", "").replace("-", "")


def _parse_api_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

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
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _extract_appointments(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict) or not result.get("success"):
        return []
    data = result.get("data", {})
    if isinstance(data, dict):
        appointments = data.get("appointments", [])
    elif isinstance(data, list):
        appointments = data
    else:
        appointments = []
    return appointments if isinstance(appointments, list) else []


class DailyTemplateDispatcher:
    """Runs template jobs once per local day at configured HH:MM."""

    def __init__(self):
        from storage.persistent_storage import (
            DAILY_TEMPLATE_DISPATCH_STATE_FILE,
            APP_SETTINGS_FILE,
            ensure_dirs,
        )
        ensure_dirs()
        self.state_file = DAILY_TEMPLATE_DISPATCH_STATE_FILE
        self.settings_file = APP_SETTINGS_FILE
        self._lock = threading.Lock()
        self.last_runs = self._load_state()

    def _load_state(self) -> Dict[str, str]:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
            return {}
        except Exception:
            return {}

    def _save_state(self) -> None:
        try:
            os.makedirs(self.state_file.parent, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.last_runs, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"⚠️ Failed to save dispatch state: {exc}")

    def _is_smart_messaging_enabled(self) -> bool:
        if not self.settings_file.exists():
            return True
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            return settings.get("smartMessaging", {}).get("enabled", True)
        except Exception:
            return True

    def _now_in_timezone(self, tz_name: str) -> datetime:
        if ZoneInfo is None:
            return datetime.now()
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            return datetime.now(ZoneInfo("Asia/Beirut"))

    def _has_existing_message(
        self,
        customer_phone: str,
        template_id: str,
        reference_date: str,
        appointment_id: Optional[Any],
    ) -> bool:
        target_phone = _normalize_phone(customer_phone)
        target_template = normalize_template_id(template_id)
        target_appointment = str(appointment_id) if appointment_id is not None else None

        for message_data in smart_messaging.scheduled_messages.values():
            msg_template = normalize_template_id(message_data.get("message_type", ""))
            if msg_template != target_template:
                continue

            msg_phone = _normalize_phone(message_data.get("customer_phone"))
            if msg_phone != target_phone:
                continue

            metadata = message_data.get("metadata", {})
            msg_reference = (
                metadata.get("reference_date")
                or message_data.get("placeholders", {}).get("reference_date")
                or message_data.get("placeholders", {}).get("appointment_date")
            )
            if reference_date and str(msg_reference) != str(reference_date):
                continue

            if target_appointment is not None:
                msg_appointment = metadata.get("appointment_id")
                if msg_appointment is not None and str(msg_appointment) != target_appointment:
                    continue

            status = message_data.get("status")
            if status in {"scheduled", "pending_approval", "sending", "sent"}:
                return True

        return False

    def _build_placeholders(
        self,
        customer_name: str,
        apt_datetime: datetime,
        branch_name: str,
        service_name: str,
        next_appointment_date: str = "",
    ) -> Dict[str, str]:
        return {
            "customer_name": customer_name or "عميلنا العزيز",
            "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
            "appointment_time": apt_datetime.strftime("%H:%M"),
            "branch_name": branch_name or "الفرع الرئيسي",
            "service_name": service_name or "جلسة ليزر",
            "phone_number": config.TRAINER_WHATSAPP_NUMBER or "+961 XX XXXXXX",
            "next_appointment_date": next_appointment_date or "",
            "reference_date": apt_datetime.strftime("%Y-%m-%d"),
        }

    def _enqueue_message(
        self,
        customer_phone: str,
        template_id: str,
        placeholders: Dict[str, str],
        language: str,
        service_id: Optional[int],
        service_name: str,
        customer_id: Optional[Any],
        appointment_id: Optional[Any],
        reference_date: str,
    ) -> bool:
        normalized_template = normalize_template_id(template_id)
        metadata = {
            "customer_id": customer_id,
            "appointment_id": appointment_id,
            "reference_date": reference_date,
            "source": "daily_template_dispatcher",
        }
        message_id = smart_messaging.schedule_message(
            customer_phone=customer_phone,
            message_type=normalized_template,
            send_at=datetime.now(),
            placeholders=placeholders,
            language=language or "ar",
            service_id=service_id,
            service_name=service_name,
            metadata=metadata,
        )
        return bool(message_id)

    async def _schedule_from_reminders(
        self,
        *,
        template_id: str,
        reminders_date: date,
        status: Optional[str],
        reference_date: str,
    ) -> Dict[str, Any]:
        result = await send_appointment_reminders(
            date=reminders_date.strftime("%Y-%m-%d"),
            status=status,
        )
        appointments = _extract_appointments(result)

        scheduled_count = 0
        skipped_duplicates = 0
        skipped_invalid = 0

        for apt in appointments:
            customer_phone = apt.get("phone")
            customer_name = apt.get("name", "عميلنا العزيز")
            customer_id = apt.get("user_id") or apt.get("customer_id")
            apt_details = apt.get("appointment_details", {}) if isinstance(apt.get("appointment_details"), dict) else {}
            apt_datetime_str = apt_details.get("date")
            apt_datetime = _parse_api_datetime(apt_datetime_str)
            service_name = apt_details.get("service", "جلسة ليزر")
            service_id = apt_details.get("service_id")
            branch_name = apt_details.get("branch", "الفرع الرئيسي")
            appointment_id = apt_details.get("id") or apt.get("appointment_id")

            if not customer_phone or not apt_datetime:
                skipped_invalid += 1
                continue

            canonical_template = normalize_template_id(template_id)
            if message_logs_service.was_message_sent(
                customer_id=customer_id or customer_phone,
                template_type=canonical_template,
                reference_date=reference_date,
                appointment_id=appointment_id,
            ):
                skipped_duplicates += 1
                continue

            if self._has_existing_message(
                customer_phone=customer_phone,
                template_id=canonical_template,
                reference_date=reference_date,
                appointment_id=appointment_id,
            ):
                skipped_duplicates += 1
                continue

            placeholders = self._build_placeholders(
                customer_name=customer_name,
                apt_datetime=apt_datetime,
                branch_name=branch_name,
                service_name=service_name,
            )
            language = user_persistence.get_user_language(customer_phone)
            if self._enqueue_message(
                customer_phone=customer_phone,
                template_id=canonical_template,
                placeholders=placeholders,
                language=language,
                service_id=service_id,
                service_name=service_name,
                customer_id=customer_id,
                appointment_id=appointment_id,
                reference_date=reference_date,
            ):
                scheduled_count += 1

        return {
            "template_id": normalize_template_id(template_id),
            "scheduled_count": scheduled_count,
            "total_candidates": len(appointments),
            "skipped_duplicates": skipped_duplicates,
            "skipped_invalid": skipped_invalid,
            "reference_date": reference_date,
        }

    async def _has_last_done_session_on(self, phone: str, target_day: date) -> bool:
        """
        Ensure 20-day follow-up is based on the customer's latest done session.
        """
        appointments_result = await get_customer_appointments(phone)
        if not appointments_result.get("success"):
            # If lookup fails, avoid blocking the workflow entirely.
            return True

        appointments = appointments_result.get("data", [])
        if not isinstance(appointments, list):
            return True

        latest_done: Optional[datetime] = None
        for apt in appointments:
            status = str(apt.get("status", "")).strip().lower()
            if status not in {"done", "completed"}:
                continue

            apt_date = apt.get("date")
            apt_time = apt.get("time")
            apt_dt = _parse_api_datetime(apt_date)
            if apt_dt is None and apt_date and apt_time:
                apt_dt = _parse_api_datetime(f"{apt_date} {apt_time}")
            if apt_dt is None:
                continue

            if latest_done is None or apt_dt > latest_done:
                latest_done = apt_dt

        if latest_done is None:
            return False
        return latest_done.date() == target_day

    async def _run_twenty_day_followup(self, run_day: date) -> Dict[str, Any]:
        target_day = run_day - timedelta(days=20)
        target_str = target_day.strftime("%Y-%m-%d")
        result = await send_appointment_reminders(date=target_str, status="Done")
        appointments = _extract_appointments(result)

        # Keep latest appointment per phone for target day.
        latest_by_phone: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
        for apt in appointments:
            phone = apt.get("phone")
            apt_details = apt.get("appointment_details", {}) if isinstance(apt.get("appointment_details"), dict) else {}
            apt_datetime = _parse_api_datetime(apt_details.get("date"))
            if not phone or not apt_datetime:
                continue

            key = _normalize_phone(phone)
            current = latest_by_phone.get(key)
            if current is None or apt_datetime > current[0]:
                latest_by_phone[key] = (apt_datetime, apt)

        scheduled_count = 0
        skipped_duplicates = 0
        skipped_not_latest = 0

        for _, (apt_datetime, apt) in latest_by_phone.items():
            customer_phone = apt.get("phone")
            customer_name = apt.get("name", "عميلنا العزيز")
            customer_id = apt.get("user_id") or apt.get("customer_id")
            apt_details = apt.get("appointment_details", {}) if isinstance(apt.get("appointment_details"), dict) else {}
            service_name = apt_details.get("service", "جلسة ليزر")
            service_id = apt_details.get("service_id")
            branch_name = apt_details.get("branch", "الفرع الرئيسي")
            appointment_id = apt_details.get("id") or apt.get("appointment_id")

            if not await self._has_last_done_session_on(customer_phone, target_day):
                skipped_not_latest += 1
                continue

            if message_logs_service.was_message_sent(
                customer_id=customer_id or customer_phone,
                template_type="twenty_day_followup",
                reference_date=target_str,
                appointment_id=appointment_id,
            ):
                skipped_duplicates += 1
                continue

            if self._has_existing_message(
                customer_phone=customer_phone,
                template_id="twenty_day_followup",
                reference_date=target_str,
                appointment_id=appointment_id,
            ):
                skipped_duplicates += 1
                continue

            placeholders = self._build_placeholders(
                customer_name=customer_name,
                apt_datetime=apt_datetime,
                branch_name=branch_name,
                service_name=service_name,
            )
            language = user_persistence.get_user_language(customer_phone)
            if self._enqueue_message(
                customer_phone=customer_phone,
                template_id="twenty_day_followup",
                placeholders=placeholders,
                language=language,
                service_id=service_id,
                service_name=service_name,
                customer_id=customer_id,
                appointment_id=appointment_id,
                reference_date=target_str,
            ):
                scheduled_count += 1

        return {
            "template_id": "twenty_day_followup",
            "scheduled_count": scheduled_count,
            "total_candidates": len(latest_by_phone),
            "skipped_duplicates": skipped_duplicates,
            "skipped_not_latest": skipped_not_latest,
            "reference_date": target_str,
        }

    async def run_template(self, template_id: str, run_day: date) -> Dict[str, Any]:
        template_id = normalize_template_id(template_id)
        if template_id == "reminder_24h":
            target_day = run_day + timedelta(days=1)
            return await self._schedule_from_reminders(
                template_id=template_id,
                reminders_date=target_day,
                status="Available",
                reference_date=target_day.strftime("%Y-%m-%d"),
            )

        if template_id == "post_session_feedback":
            # Feedback for appointments that happened YESTERDAY (status DONE), sent at end-of-day today
            target_day = run_day - timedelta(days=1)
            return await self._schedule_from_reminders(
                template_id=template_id,
                reminders_date=target_day,
                status="Done",
                reference_date=target_day.strftime("%Y-%m-%d"),
            )

        if template_id == "missed_yesterday":
            # Yesterday, status = Available (not Done) = had appointment but not completed
            target_day = run_day - timedelta(days=1)
            return await self._schedule_from_reminders(
                template_id=template_id,
                reminders_date=target_day,
                status="Available",
                reference_date=target_day.strftime("%Y-%m-%d"),
            )

        if template_id == "twenty_day_followup":
            return await self._run_twenty_day_followup(run_day)

        return {
            "template_id": template_id,
            "scheduled_count": 0,
            "total_candidates": 0,
            "skipped_invalid": 0,
            "error": "Unsupported template for daily dispatcher",
        }

    async def tick(self) -> Dict[str, Any]:
        """
        Called frequently (e.g., every minute). Runs templates whose local HH:MM matches now.
        """
        if not self._is_smart_messaging_enabled():
            return {
                "success": True,
                "jobs_run": [],
                "run_count": 0,
                "skipped": "smart_messaging_disabled",
            }

        schedules = template_schedule_service.get_all_schedules()
        jobs_run = []
        due_jobs: List[Dict[str, Any]] = []
        with self._lock:
            for template_id in DAILY_TEMPLATE_IDS:
                schedule = schedules.get(template_id, {})
                if not schedule.get("enabled", True):
                    continue

                send_time = str(schedule.get("sendTime", ""))
                timezone = str(schedule.get("timezone", "Asia/Beirut"))
                local_now = self._now_in_timezone(timezone)
                if local_now.strftime("%H:%M") != send_time:
                    continue

                day_key = local_now.date().isoformat()
                if self.last_runs.get(template_id) == day_key:
                    continue

                due_jobs.append({
                    "template_id": template_id,
                    "run_date": day_key,
                    "timezone": timezone,
                    "send_time": send_time,
                    "run_day": local_now.date(),
                })

        for job in due_jobs:
            result = await self.run_template(job["template_id"], job["run_day"])
            jobs_run.append({
                "template_id": job["template_id"],
                "run_date": job["run_date"],
                "timezone": job["timezone"],
                "send_time": job["send_time"],
                "result": result,
            })

        if jobs_run:
            with self._lock:
                for job in jobs_run:
                    self.last_runs[job["template_id"]] = job["run_date"]
                self._save_state()

        return {
            "success": True,
            "jobs_run": jobs_run,
            "run_count": len(jobs_run),
        }


daily_template_dispatcher = DailyTemplateDispatcher()

