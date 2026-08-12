"""
Daily fixed-time dispatcher for smart messaging templates.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import config
from services.daily_template_dispatcher_helpers import _normalize_phone
from services.daily_template_dispatcher_jobs import DailyTemplateDispatcherJobsMixin
from services.smart_messaging import smart_messaging
from services.smart_messaging_catalog import DAILY_TEMPLATE_IDS, normalize_template_id
from services.template_schedule_service import template_schedule_service


class DailyTemplateDispatcher(DailyTemplateDispatcherJobsMixin):
    """Runs template jobs once per local day at configured HH:MM."""

    def __init__(self) -> None:
        from storage.persistent_storage import (
            APP_SETTINGS_FILE,
            DAILY_TEMPLATE_DISPATCH_STATE_FILE,
            ensure_dirs,
        )

        ensure_dirs()
        self.state_file = DAILY_TEMPLATE_DISPATCH_STATE_FILE
        self.settings_file = APP_SETTINGS_FILE
        self._lock = threading.Lock()
        self.last_runs = self._load_state()

    def _load_state(self) -> dict[str, str]:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, encoding="utf-8") as f:
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
            with open(self.settings_file, encoding="utf-8") as f:
                settings = json.load(f)
            return cast(bool, settings.get("smartMessaging", {}).get("enabled", True))
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
        appointment_id: Any | None,
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
    ) -> dict[str, str]:
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
        placeholders: dict[str, str],
        language: str,
        service_id: int | None,
        service_name: str,
        customer_id: Any | None,
        appointment_id: Any | None,
        reference_date: str,
    ) -> bool:
        normalized_template = normalize_template_id(template_id)
        metadata: dict[str, Any] = {
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

    async def tick(self) -> dict[str, Any]:
        """
        Called on scheduler cadence (default 5 minutes).
        Runs templates whose configured HH:MM falls inside the current cadence window.
        """
        if not self._is_smart_messaging_enabled():
            return {
                "success": True,
                "jobs_run": [],
                "run_count": 0,
                "skipped": "smart_messaging_disabled",
            }

        schedules = template_schedule_service.get_all_schedules()
        cadence_minutes = max(1, int(os.getenv("SMART_DISPATCHER_INTERVAL_MINUTES", "5")))
        jobs_run = []
        due_jobs: list[dict[str, Any]] = []
        templates_checked = 0
        with self._lock:
            for template_id in DAILY_TEMPLATE_IDS:
                templates_checked += 1
                if template_id == "thank_you_message_sent_after_session":
                    # Feedback uses delay-after-appointment; handled after this loop every tick.
                    continue
                schedule = schedules.get(template_id, {})
                if not schedule.get("enabled", True):
                    continue

                send_time = str(schedule.get("sendTime", ""))
                timezone = str(schedule.get("timezone", "Asia/Beirut"))
                local_now = self._now_in_timezone(timezone)
                try:
                    send_hour, send_minute = [int(p) for p in send_time.split(":", 1)]
                    send_dt = local_now.replace(
                        hour=send_hour,
                        minute=send_minute,
                        second=0,
                        microsecond=0,
                    )
                except Exception:
                    continue

                window_start = local_now - timedelta(minutes=cadence_minutes)
                if send_dt > local_now or send_dt < window_start:
                    continue

                day_key = local_now.date().isoformat()
                if self.last_runs.get(template_id) == day_key:
                    continue

                due_jobs.append(
                    {
                        "template_id": template_id,
                        "run_date": day_key,
                        "timezone": timezone,
                        "send_time": send_time,
                        "run_day": local_now.date(),
                    }
                )

        for job in due_jobs:
            result = await self.run_template(job["template_id"], job["run_day"])
            jobs_run.append(
                {
                    "template_id": job["template_id"],
                    "run_date": job["run_date"],
                    "timezone": job["timezone"],
                    "send_time": job["send_time"],
                    "result": result,
                }
            )

        thank_you_after_session_result = None
        if self._is_smart_messaging_enabled():
            fb_cfg = schedules.get("thank_you_message_sent_after_session", {})
            if fb_cfg.get("enabled", True):
                tz_fb = str(fb_cfg.get("timezone", "Asia/Beirut"))
                thank_you_after_session_result = await self.run_post_session_feedback_delayed(
                    self._now_in_timezone(tz_fb),
                    fb_cfg,
                )

        if jobs_run:
            with self._lock:
                for job in jobs_run:
                    self.last_runs[job["template_id"]] = job["run_date"]
                self._save_state()

        fb_scheduled = (thank_you_after_session_result or {}).get("scheduled_count", 0)
        print(
            f"[daily_template_dispatcher] tick cadence={cadence_minutes}m checked={templates_checked} "
            f"due={len(due_jobs)} ran={len(jobs_run)} feedback_scheduled={fb_scheduled}"
        )

        return {
            "success": True,
            "jobs_run": jobs_run,
            "run_count": len(jobs_run),
            "thank_you_message_sent_after_session": thank_you_after_session_result,
        }


daily_template_dispatcher = DailyTemplateDispatcher()
