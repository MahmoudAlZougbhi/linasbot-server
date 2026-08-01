"""
Campaign service for Missed This Month (BOC paused appointments; WhatsApp Meta: sent_for_pause).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import config
from services.api_integrations import get_paused_appointments_between_dates
from services.message_logs_service import message_logs_service
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.phone_utils import normalize_phone


def _parse_api_datetime(value: str | None) -> datetime | None:
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


def _normalize_phone(phone: Any) -> str:
    if phone is None:
        return ""
    return str(phone).replace("+", "").replace(" ", "").replace("-", "")


def _as_placeholder_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    s = str(value).strip()
    if not s or s.lower() in ("none", "null"):
        return default
    return s


def _format_body_areas(row: dict[str, Any]) -> str:
    raw = row.get("body_parts") or row.get("body_areas") or row.get("areas")
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, list):
        return _as_placeholder_str(raw)
    parts: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            label = (
                item.get("name")
                or item.get("body_part")
                or item.get("body_part_name")
                or item.get("area")
                or item.get("body_part_id")
            )
            parts.append(_as_placeholder_str(label))
        else:
            parts.append(_as_placeholder_str(item))
    return ", ".join(p for p in parts if p)


def _paused_campaign_placeholders(recipient: dict[str, Any], clinic_contact_phone: str) -> dict[str, str]:
    """All template placeholders for sent_for_pause / paused BOC campaign (recipient + raw BOC row)."""
    row_data = recipient.get("raw")
    row: dict[str, Any] = row_data if isinstance(row_data, dict) else {}
    customer_data = row.get("customer")
    customer: dict[str, Any] = customer_data if isinstance(customer_data, dict) else {}

    cust_phone = _as_placeholder_str(recipient.get("phone")) or _as_placeholder_str(customer.get("phone"))

    apt_id = recipient.get("appointment_id")
    if apt_id is None:
        apt_id = row.get("appointment_id") or row.get("id") or row.get("appointmentId")

    machine = _as_placeholder_str(recipient.get("machine_name")) or _as_placeholder_str(row.get("machine"))

    return {
        # Core (existing)
        "customer_name": _as_placeholder_str(recipient.get("customer_name")) or "عميلنا العزيز",
        "appointment_date": _as_placeholder_str(recipient.get("appointment_date")),
        "appointment_time": _as_placeholder_str(recipient.get("appointment_time")),
        "branch_name": _as_placeholder_str(recipient.get("branch_name")) or "الفرع الرئيسي",
        "service_name": _as_placeholder_str(recipient.get("service_name")) or "جلسة ليزر",
        "phone_number": clinic_contact_phone,
        "next_appointment_date": "",
        # Customer / contact
        "customer_phone": cust_phone,
        "customer_phone_digits": _normalize_phone(cust_phone),
        "customer_id": _as_placeholder_str(recipient.get("customer_id")) or _as_placeholder_str(customer.get("id")),
        "user_code": _as_placeholder_str(recipient.get("user_code")) or _as_placeholder_str(customer.get("user_code")),
        "customer_email": _as_placeholder_str(customer.get("email")),
        # Appointment row
        "appointment_id": _as_placeholder_str(apt_id),
        "machine_name": machine or "",
        "machine_id": _as_placeholder_str(row.get("machine_id")),
        "service_id": _as_placeholder_str(row.get("service_id")),
        "branch_id": _as_placeholder_str(row.get("branch_id")),
        "appointment_status": _as_placeholder_str(row.get("status"))
        or _as_placeholder_str(row.get("appointment_status")),
        "appointment_notes": _as_placeholder_str(row.get("notes")) or _as_placeholder_str(row.get("note")),
        "price": _as_placeholder_str(row.get("price"))
        or _as_placeholder_str(row.get("amount"))
        or _as_placeholder_str(row.get("total")),
        "currency": _as_placeholder_str(row.get("currency")),
        "body_areas": _format_body_areas(row),
        "appointment_date_raw": _as_placeholder_str(recipient.get("date_raw")) or _as_placeholder_str(row.get("date")),
        "session_number": _as_placeholder_str(row.get("session_number")) or _as_placeholder_str(row.get("session")),
        "duration_minutes": _as_placeholder_str(row.get("duration"))
        or _as_placeholder_str(row.get("duration_minutes")),
    }


class MissedPausedCampaignService:
    """Build, preview, and execute paused-appointment campaigns."""

    TEMPLATE_ID = "sent_for_pause"

    async def _fetch_paused_rows(
        self,
        start_date: str,
        end_date: str,
        service_ids: list[int],
    ) -> list[dict[str, Any]]:
        requests = []
        if service_ids:
            for service_id in service_ids:
                requests.append(
                    get_paused_appointments_between_dates(
                        start_date=start_date,
                        end_date=end_date,
                        service_id=service_id,
                    )
                )
        else:
            requests.append(
                get_paused_appointments_between_dates(
                    start_date=start_date,
                    end_date=end_date,
                    service_id=None,
                )
            )

        results = await asyncio.gather(*requests, return_exceptions=True)
        rows: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if not isinstance(result, dict) or not result.get("success"):
                continue

            data = result.get("data", {})
            if isinstance(data, dict):
                appointments = data.get("appointments", [])
            elif isinstance(data, list):
                appointments = data
            else:
                appointments = []

            if isinstance(appointments, list):
                rows.extend(appointments)

        return rows

    def _resolve_date_range(self, filters: dict[str, Any]) -> dict[str, str]:
        today = datetime.now().date()

        from_date = str(filters.get("from_date", "")).strip()
        to_date = str(filters.get("to_date", "")).strip()
        lookback_months = filters.get("lookback_months")

        if from_date and to_date:
            return {"from_date": from_date, "to_date": to_date}

        try:
            lookback = int(lookback_months) if lookback_months is not None else 3
            if lookback < 1:
                lookback = 1
            if lookback > 24:
                lookback = 24
        except (TypeError, ValueError):
            lookback = 3

        from_resolved = today - timedelta(days=lookback * 30)
        return {
            "from_date": from_resolved.strftime("%Y-%m-%d"),
            "to_date": today.strftime("%Y-%m-%d"),
        }

    def _recipient_from_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        customer = row.get("customer", {}) if isinstance(row.get("customer"), dict) else {}
        phone = customer.get("phone")
        if not phone:
            return None

        date_raw = row.get("date")
        apt_dt = _parse_api_datetime(date_raw)
        if apt_dt is None:
            return None

        apt_id = row.get("appointment_id") or row.get("id") or row.get("appointmentId")

        return {
            "customer_id": customer.get("id") or _normalize_phone(phone),
            "customer_name": customer.get("name", "عميلنا العزيز"),
            "phone": str(phone),
            "service_name": row.get("service", "جلسة ليزر"),
            "appointment_id": apt_id,
            "appointment_date": apt_dt.strftime("%Y-%m-%d"),
            "appointment_time": apt_dt.strftime("%H:%M"),
            "branch_name": row.get("branch", "الفرع الرئيسي"),
            "machine_name": row.get("machine"),
            "user_code": customer.get("user_code"),
            "date_raw": date_raw,
            "service_id": row.get("service_id"),
            "branch_id": row.get("branch_id"),
            "machine_id": row.get("machine_id"),
            "appointment_status": row.get("status") or row.get("appointment_status"),
            "body_areas_preview": _format_body_areas(row),
            "paused_only": True,
            "raw": row,
        }

    async def preview(self, filters: dict[str, Any]) -> dict[str, Any]:
        filters = dict(filters or {})
        service_ids = filters.get("service_ids") or []
        if not isinstance(service_ids, list):
            service_ids = []
        normalized_service_ids = []
        for value in service_ids:
            try:
                normalized_service_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        date_range = self._resolve_date_range(filters)
        rows = await self._fetch_paused_rows(
            start_date=date_range["from_date"],
            end_date=date_range["to_date"],
            service_ids=normalized_service_ids,
        )

        recipients: list[dict[str, Any]] = []
        latest_by_phone: dict[str, dict[str, Any]] = {}

        for row in rows:
            recipient = self._recipient_from_row(row)
            if not recipient:
                continue

            phone_key = _normalize_phone(recipient["phone"])
            existing = latest_by_phone.get(phone_key)
            if not existing:
                latest_by_phone[phone_key] = recipient
                continue

            if recipient["appointment_date"] > existing["appointment_date"]:
                latest_by_phone[phone_key] = recipient

        recipients = sorted(
            latest_by_phone.values(),
            key=lambda r: (r.get("appointment_date", ""), r.get("customer_name", "")),
            reverse=True,
        )

        return {
            "success": True,
            "template_id": self.TEMPLATE_ID,
            "paused_only": True,
            "placeholders_help": (
                "Optional placeholders: {customer_name} {customer_phone} {customer_phone_digits} "
                "{appointment_date} {appointment_time} {appointment_date_raw} {appointment_id} "
                "{service_name} {service_id} {branch_name} {branch_id} {machine_name} {machine_id} "
                "{user_code} {customer_id} {customer_email} {appointment_status} {appointment_notes} "
                "{price} {currency} {body_areas} {session_number} {duration_minutes} "
                "{phone_number} (clinic) {next_appointment_date}"
            ),
            "filters": {
                **filters,
                "service_ids": normalized_service_ids,
                "from_date": date_range["from_date"],
                "to_date": date_range["to_date"],
                "paused_only": True,
            },
            "count": len(recipients),
            "recipients": recipients,
        }

    async def send_or_schedule(
        self,
        filters: dict[str, Any],
        send_mode: str = "send_now",
        schedule_time: str | None = None,
        language: str = "ar",
    ) -> dict[str, Any]:
        preview_result = await self.preview(filters)
        if not preview_result.get("success"):
            return preview_result

        recipients = preview_result.get("recipients", [])
        effective_filters = preview_result.get("filters", {})
        send_mode = (send_mode or "send_now").strip().lower()
        schedule_dt = None
        if send_mode == "schedule":
            if not schedule_time:
                return {"success": False, "error": "schedule_time is required for scheduled campaigns"}
            try:
                schedule_dt = datetime.fromisoformat(str(schedule_time).replace("Z", "+00:00"))
                # keep naive for consistency with existing scheduler behavior
                if schedule_dt.tzinfo is not None:
                    schedule_dt = schedule_dt.replace(tzinfo=None)
            except ValueError:
                return {"success": False, "error": "Invalid schedule_time format"}

        campaign_entry = message_logs_service.create_campaign_log(
            template_type=self.TEMPLATE_ID,
            filters=effective_filters,
            scheduled_for=schedule_dt.isoformat() if schedule_dt else None,
        )
        campaign_id = campaign_entry["campaign_id"]

        sent_count = 0
        queued_count = 0
        failed: list[dict[str, Any]] = []

        adapter = WhatsAppFactory.get_adapter() if send_mode != "schedule" else None
        contact_phone = config.TRAINER_WHATSAPP_NUMBER or "+961 XX XXXXXX"
        fallback_lang = (language or "ar").strip().lower()
        if fallback_lang not in ("ar", "en", "fr"):
            fallback_lang = "ar"

        for recipient in recipients:
            phone = recipient.get("phone")
            if not phone:
                continue

            uid_guess = (normalize_phone(phone) or "").strip() or str(phone).strip()
            resolved_lang = await user_persistence.resolve_language_for_campaign_recipient(
                phone,
                firestore_user_id=uid_guess,
                fallback_language=fallback_lang,
            )

            placeholders = _paused_campaign_placeholders(recipient, contact_phone)
            metadata: dict[str, Any] = {
                "campaign_id": campaign_id,
                "customer_id": recipient.get("customer_id"),
                "appointment_id": recipient.get("appointment_id"),
                "reference_date": recipient.get("appointment_date"),
                "source": "missed_paused_campaign",
            }

            if send_mode == "schedule" and schedule_dt is not None:
                message_id = smart_messaging.schedule_message(
                    customer_phone=phone,
                    message_type=self.TEMPLATE_ID,
                    send_at=schedule_dt,
                    placeholders=placeholders,
                    language=resolved_lang,
                    service_id=None,
                    service_name=recipient.get("service_name"),
                    metadata=metadata,
                )
                if message_id:
                    queued_count += 1
                else:
                    failed.append(
                        {
                            "phone": phone,
                            "reason": "Failed to queue message",
                        }
                    )
                continue

            content = smart_messaging.get_message_content(
                message_type=self.TEMPLATE_ID,
                language=resolved_lang,
                placeholders=placeholders,
            )
            if not content:
                failed.append(
                    {
                        "phone": phone,
                        "reason": "Template content is empty or missing",
                    }
                )
                continue

            try:
                from services.smart_messaging import deliver_scheduled_smart_whatsapp

                result = await deliver_scheduled_smart_whatsapp(
                    adapter,
                    phone=phone,
                    template_id=self.TEMPLATE_ID,
                    language=resolved_lang,
                    placeholders=placeholders,
                    rendered_text=content,
                )
                if result.get("dry_run"):
                    failed.append(
                        {
                            "phone": phone,
                            "reason": "dry_run (not delivered)",
                        }
                    )
                elif result.get("success"):
                    sent_count += 1
                    message_logs_service.log_message(
                        customer_id=recipient.get("customer_id") or phone,
                        template_type=self.TEMPLATE_ID,
                        appointment_id=recipient.get("appointment_id"),
                        campaign_id=campaign_id,
                        reference_date=recipient.get("appointment_date"),
                        extra={
                            "phone": phone,
                            "customer_name": recipient.get("customer_name"),
                            "service_name": recipient.get("service_name"),
                        },
                    )
                else:
                    failed.append(
                        {
                            "phone": phone,
                            "reason": result.get("error", "Unknown send error"),
                        }
                    )
            except Exception as exc:
                failed.append(
                    {
                        "phone": phone,
                        "reason": str(exc),
                    }
                )

        final_status = "scheduled" if send_mode == "schedule" else "completed"
        message_logs_service.finalize_campaign_log(
            campaign_id=campaign_id,
            sent_count=sent_count + queued_count,
            preview_count=len(recipients),
            status=final_status,
        )

        return {
            "success": True,
            "campaign_id": campaign_id,
            "template_id": self.TEMPLATE_ID,
            "send_mode": send_mode,
            "scheduled_for": schedule_dt.isoformat() if schedule_dt else None,
            "preview_count": len(recipients),
            "sent_count": sent_count,
            "queued_count": queued_count,
            "failed_count": len(failed),
            "failed": failed[:100],
            "filters": effective_filters,
        }


missed_paused_campaign_service = MissedPausedCampaignService()
