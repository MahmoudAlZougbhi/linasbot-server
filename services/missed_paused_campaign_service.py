"""
Campaign service for "Missed Paused Appointment".
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config
from services.api_integrations import get_paused_appointments_between_dates
from services.message_logs_service import message_logs_service
from services.smart_messaging import smart_messaging
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


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


def _normalize_phone(phone: Any) -> str:
    if phone is None:
        return ""
    return str(phone).replace("+", "").replace(" ", "").replace("-", "")


class MissedPausedCampaignService:
    """Build, preview, and execute paused-appointment campaigns."""

    TEMPLATE_ID = "missed_paused_appointment"

    async def _fetch_paused_rows(
        self,
        start_date: str,
        end_date: str,
        service_ids: List[int],
    ) -> List[Dict[str, Any]]:
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
        rows: List[Dict[str, Any]] = []
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

    def _resolve_date_range(self, filters: Dict[str, Any]) -> Dict[str, str]:
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

    def _recipient_from_row(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        customer = row.get("customer", {}) if isinstance(row.get("customer"), dict) else {}
        phone = customer.get("phone")
        if not phone:
            return None

        date_raw = row.get("date")
        apt_dt = _parse_api_datetime(date_raw)
        if apt_dt is None:
            return None

        return {
            "customer_id": customer.get("id") or _normalize_phone(phone),
            "customer_name": customer.get("name", "عميلنا العزيز"),
            "phone": str(phone),
            "service_name": row.get("service", "جلسة ليزر"),
            "appointment_id": row.get("appointment_id"),
            "appointment_date": apt_dt.strftime("%Y-%m-%d"),
            "appointment_time": apt_dt.strftime("%H:%M"),
            "branch_name": row.get("branch", "الفرع الرئيسي"),
            "machine_name": row.get("machine"),
            "user_code": customer.get("user_code"),
            "paused_only": True,
            "raw": row,
        }

    async def preview(self, filters: Dict[str, Any]) -> Dict[str, Any]:
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

        recipients: List[Dict[str, Any]] = []
        latest_by_phone: Dict[str, Dict[str, Any]] = {}

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
        filters: Dict[str, Any],
        send_mode: str = "send_now",
        schedule_time: Optional[str] = None,
        language: str = "ar",
    ) -> Dict[str, Any]:
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
        failed: List[Dict[str, Any]] = []

        adapter = WhatsAppFactory.get_adapter() if send_mode != "schedule" else None
        contact_phone = config.TRAINER_WHATSAPP_NUMBER or "+961 XX XXXXXX"

        for recipient in recipients:
            phone = recipient.get("phone")
            if not phone:
                continue

            placeholders = {
                "customer_name": recipient.get("customer_name", "عميلنا العزيز"),
                "appointment_date": recipient.get("appointment_date"),
                "appointment_time": recipient.get("appointment_time"),
                "branch_name": recipient.get("branch_name", "الفرع الرئيسي"),
                "service_name": recipient.get("service_name", "جلسة ليزر"),
                "phone_number": contact_phone,
                "next_appointment_date": "",
            }
            metadata = {
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
                    language=language,
                    service_id=None,
                    service_name=recipient.get("service_name"),
                    metadata=metadata,
                )
                if message_id:
                    queued_count += 1
                else:
                    failed.append({
                        "phone": phone,
                        "reason": "Failed to queue message",
                    })
                continue

            content = smart_messaging.get_message_content(
                message_type=self.TEMPLATE_ID,
                language=language,
                placeholders=placeholders,
            )
            if not content:
                failed.append({
                    "phone": phone,
                    "reason": "Template content is empty or missing",
                })
                continue

            try:
                result = await adapter.send_text_message(phone, content)
                if result.get("success"):
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
                    failed.append({
                        "phone": phone,
                        "reason": result.get("error", "Unknown send error"),
                    })
            except Exception as exc:
                failed.append({
                    "phone": phone,
                    "reason": str(exc),
                })

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

