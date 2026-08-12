"""Daily template job runners (reminders, feedback, follow-up) as a mixin."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from services.api_integrations import get_customer_appointments, send_appointment_reminders
from services.daily_template_dispatcher_helpers import (
    _extract_appointments,
    _normalize_phone,
    _parse_api_datetime,
)
from services.message_logs_service import message_logs_service
from services.smart_messaging_catalog import TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS, normalize_template_id
from services.template_schedule_service import template_schedule_service
from services.user_persistence_service import user_persistence


class DailyTemplateDispatcherJobsMixin:
    """Schedule/enqueue jobs used by DailyTemplateDispatcher."""

    async def _schedule_from_reminders(
        self,
        *,
        template_id: str,
        reminders_date: date,
        status: str | None,
        reference_date: str,
    ) -> dict[str, Any]:
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

    async def run_post_session_feedback_delayed(
        self, local_now: datetime, schedule_cfg: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Post-session feedback: same calendar day as the appointment, N hours after slot time.
        Checked on every dispatcher tick (not once daily at sendTime).
        """
        try:
            delay_h = float(schedule_cfg.get("delayHours", 3))
        except (TypeError, ValueError):
            delay_h = 3.0
        delay_h = max(0.5, min(72.0, delay_h))

        today_date = local_now.date()
        today_str = today_date.strftime("%Y-%m-%d")
        yesterday_str = (today_date - timedelta(days=1)).strftime("%Y-%m-%d")

        merged: list[dict[str, Any]] = []
        seen_keys: set = set()
        for day_str in (today_str, yesterday_str):
            part = await send_appointment_reminders(date=day_str, status="Done")
            for apt in _extract_appointments(part):
                apt_details = (
                    apt.get("appointment_details", {}) if isinstance(apt.get("appointment_details"), dict) else {}
                )
                aid = apt_details.get("id") or apt.get("appointment_id")
                ph = apt.get("phone")
                key = (str(aid or ""), str(ph or ""))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(apt)
        appointments = merged

        scheduled_count = 0
        skipped_duplicates = 0
        skipped_invalid = 0
        skipped_not_due = 0

        template_id = "thank_you_message_sent_after_session"
        canonical_template = normalize_template_id(template_id)

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

            status_raw = str(apt.get("status", "")).strip().lower()
            if status_raw and status_raw not in ("done", "completed"):
                skipped_invalid += 1
                continue

            if local_now.tzinfo is not None:
                if apt_datetime.tzinfo is None:
                    apt_dt = apt_datetime.replace(tzinfo=local_now.tzinfo)
                else:
                    apt_dt = apt_datetime.astimezone(local_now.tzinfo)
            else:
                apt_dt = apt_datetime.replace(tzinfo=None) if apt_datetime.tzinfo else apt_datetime

            # Allow appointment on today or yesterday (late slot + delay can cross midnight)
            if apt_dt.date() < today_date - timedelta(days=1):
                skipped_invalid += 1
                continue

            eligible_at = apt_dt + timedelta(hours=delay_h)
            if local_now < eligible_at:
                skipped_not_due += 1
                continue

            reference_date = apt_dt.strftime("%Y-%m-%d")

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
                apt_datetime=apt_dt,
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
            "template_id": canonical_template,
            "scheduled_count": scheduled_count,
            "total_candidates": len(appointments),
            "skipped_duplicates": skipped_duplicates,
            "skipped_invalid": skipped_invalid,
            "skipped_not_due": skipped_not_due,
            "reference_date": today_str,
            "delay_hours": delay_h,
        }

    async def _has_last_done_session_on(self, phone: str, target_day: date) -> bool:
        """
        Ensure One Month Follow Up (17-day rule) is based on the customer's latest done session.
        """
        appointments_result = await get_customer_appointments(phone)
        if not appointments_result.get("success"):
            # If lookup fails, avoid blocking the workflow entirely.
            return True

        appointments = appointments_result.get("data", [])
        if not isinstance(appointments, list):
            return True

        latest_done: datetime | None = None
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

    async def _run_twenty_day_followup(self, run_day: date) -> dict[str, Any]:
        target_day = run_day - timedelta(days=TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS)
        target_str = target_day.strftime("%Y-%m-%d")
        result = await send_appointment_reminders(date=target_str, status="Done")
        appointments = _extract_appointments(result)

        # Keep latest appointment per phone for target day.
        latest_by_phone: dict[str, tuple[datetime, dict[str, Any]]] = {}
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
            customer_phone = str(apt.get("phone") or "")
            if not customer_phone:
                continue
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
                template_type="sent_17_days_after_last_session_new",
                reference_date=target_str,
                appointment_id=appointment_id,
            ):
                skipped_duplicates += 1
                continue

            if self._has_existing_message(
                customer_phone=customer_phone,
                template_id="sent_17_days_after_last_session_new",
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
                template_id="sent_17_days_after_last_session_new",
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
            "template_id": "sent_17_days_after_last_session_new",
            "scheduled_count": scheduled_count,
            "total_candidates": len(latest_by_phone),
            "skipped_duplicates": skipped_duplicates,
            "skipped_not_latest": skipped_not_latest,
            "reference_date": target_str,
        }

    async def run_template(self, template_id: str, run_day: date) -> dict[str, Any]:
        template_id = normalize_template_id(template_id)
        if template_id == "reminder_24h":
            target_day = run_day + timedelta(days=1)
            return await self._schedule_from_reminders(
                template_id=template_id,
                reminders_date=target_day,
                status="Available",
                reference_date=target_day.strftime("%Y-%m-%d"),
            )

        if template_id == "thank_you_message_sent_after_session":
            cfg = template_schedule_service.get_schedule("thank_you_message_sent_after_session")
            tz = str(cfg.get("timezone", "Asia/Beirut"))
            return await self.run_post_session_feedback_delayed(
                self._now_in_timezone(tz),
                cfg,
            )

        if template_id == "session_feedback":
            # Next-day Meta session_feedback: yesterday + Done; idempotency via message logs
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

        if template_id == "sent_17_days_after_last_session_new":
            return await self._run_twenty_day_followup(run_day)

        return {
            "template_id": template_id,
            "scheduled_count": 0,
            "total_candidates": 0,
            "skipped_invalid": 0,
            "error": "Unsupported template for daily dispatcher",
        }
