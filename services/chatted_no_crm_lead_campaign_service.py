"""
Manual campaign: WhatsApp users who chatted (Firestore) but have no CRM customer file
and no appointments in BOC. Optional filter: last chat activity in date range; optional
service filter via chat text mentioning mapped service names.
"""

import asyncio
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import config
from services.api_integrations import get_customer_by_phone, get_customer_appointments
from services.chat_response_service import _extract_customer_appointments_list
from services.live_chat_service import live_chat_service
from services.message_logs_service import message_logs_service
from services.service_template_mapping_service import service_template_mapping_service
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.phone_utils import normalize_phone


def _normalize_phone_key(phone: Any) -> str:
    if phone is None:
        return ""
    return str(phone).replace("+", "").replace(" ", "").replace("-", "")


def _phone_for_api(row: Dict[str, Any]) -> str:
    return str(row.get("phone_full") or row.get("phone_clean") or "").strip()


def _parse_iso_date_only(iso_ts: str) -> Optional[date]:
    if not iso_ts:
        return None
    s = str(iso_ts).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


class ChattedNoCrmLeadCampaignService:
    """Build, preview, and send 'WhatsApp lead — no CRM file / no booking' campaigns."""

    TEMPLATE_ID = "whatsapp_lead_no_booking"

    def _resolve_date_range(self, filters: Dict[str, Any]) -> Dict[str, str]:
        today = datetime.now().date()
        from_date = str(filters.get("from_date", "")).strip()
        to_date = str(filters.get("to_date", "")).strip()
        if from_date and to_date:
            return {"from_date": from_date, "to_date": to_date}
        from_resolved = today.replace(day=1)
        return {
            "from_date": from_resolved.strftime("%Y-%m-%d"),
            "to_date": today.strftime("%Y-%m-%d"),
        }

    async def _has_crm_customer(self, phone: str) -> bool:
        if not phone:
            return False
        resp = await get_customer_by_phone(phone=phone)
        return bool(resp.get("success") and resp.get("data"))

    async def _qualifies_lead(self, phone: str, sem: asyncio.Semaphore) -> bool:
        async with sem:
            if await self._has_crm_customer(phone):
                return False
            resp = await get_customer_appointments(phone=phone)
            if not resp.get("success"):
                # No CRM row; if appointments API fails, still count as lead (cannot verify bookings).
                return True
            rows = _extract_customer_appointments_list(resp)
            return len(rows) == 0

    def _service_names_for_ids(self, service_ids: List[int]) -> List[str]:
        if not service_ids:
            return []
        by_id = {
            int(s["service_id"]): str(s.get("service_name") or "")
            for s in service_template_mapping_service.get_available_services()
        }
        out: List[str] = []
        for sid in service_ids:
            name = by_id.get(int(sid))
            if name:
                out.append(name)
        return out

    async def preview(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        filters = dict(filters or {})
        service_ids = filters.get("service_ids") or []
        if not isinstance(service_ids, list):
            service_ids = []
        normalized_service_ids: List[int] = []
        for value in service_ids:
            try:
                normalized_service_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        date_range = self._resolve_date_range(filters)
        d_from = date.fromisoformat(date_range["from_date"])
        d_to = date.fromisoformat(date_range["to_date"])

        rows = await live_chat_service._collect_history_customer_rows()
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            ts = row.get("last_message_time")
            d_msg = _parse_iso_date_only(ts)
            if d_msg is None or d_msg < d_from or d_msg > d_to:
                continue
            phone = _phone_for_api(row)
            if not phone or phone == "Unknown":
                continue
            candidates.append(row)

        # Dedupe by phone (keep latest last_message_time)
        by_phone: Dict[str, Dict[str, Any]] = {}
        for row in candidates:
            key = _normalize_phone_key(_phone_for_api(row))
            if not key:
                continue
            prev = by_phone.get(key)
            if not prev or str(row.get("last_message_time", "")) > str(prev.get("last_message_time", "")):
                by_phone[key] = row

        unique_rows = list(by_phone.values())
        sem = asyncio.Semaphore(10)
        checks = await asyncio.gather(
            *[self._qualifies_lead(_phone_for_api(r), sem) for r in unique_rows],
            return_exceptions=True,
        )

        qualified: List[Dict[str, Any]] = []
        for row, ok in zip(unique_rows, checks):
            if isinstance(ok, Exception):
                continue
            if ok:
                qualified.append(row)

        service_names = self._service_names_for_ids(normalized_service_ids)
        if normalized_service_ids and not service_names:
            return {
                "success": False,
                "error": "Selected service IDs are not in Service Mappings; add mappings or clear the service filter.",
            }

        recipients: List[Dict[str, Any]] = []
        if normalized_service_ids:
            sem2 = asyncio.Semaphore(12)
            async def mention_ok(r: Dict[str, Any]) -> bool:
                uid = r.get("user_id")
                if not uid:
                    return False
                async with sem2:
                    return await live_chat_service.user_chats_mention_any_service_name(
                        str(uid), service_names
                    )
            mention_flags = await asyncio.gather(
                *[mention_ok(r) for r in qualified],
                return_exceptions=True,
            )
            for row, m in zip(qualified, mention_flags):
                if m is True:
                    recipients.append(self._recipient_from_row(row))
        else:
            for row in qualified:
                recipients.append(self._recipient_from_row(row))

        recipients.sort(
            key=lambda r: (r.get("last_chat_date", ""), r.get("customer_name", "")),
            reverse=True,
        )

        return {
            "success": True,
            "template_id": self.TEMPLATE_ID,
            "filters": {
                **filters,
                "service_ids": normalized_service_ids,
                "from_date": date_range["from_date"],
                "to_date": date_range["to_date"],
            },
            "count": len(recipients),
            "recipients": recipients,
        }

    def _recipient_from_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        phone = _phone_for_api(row)
        d_msg = _parse_iso_date_only(row.get("last_message_time") or "")
        return {
            "customer_id": row.get("user_id") or _normalize_phone_key(phone),
            "customer_name": row.get("user_name") or "عميلنا العزيز",
            "phone": phone,
            "user_id": row.get("user_id"),
            "last_chat_date": d_msg.isoformat() if d_msg else "",
            "last_message_preview": (row.get("last_message") or "")[:120],
            "message_count": row.get("message_count", 0),
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

        recipients: List[Dict[str, Any]] = preview_result.get("recipients", [])
        effective_filters = preview_result.get("filters", {})
        send_mode = (send_mode or "send_now").strip().lower()
        schedule_dt = None
        if send_mode == "schedule":
            if not schedule_time:
                return {"success": False, "error": "schedule_time is required for scheduled campaigns"}
            try:
                schedule_dt = datetime.fromisoformat(str(schedule_time).replace("Z", "+00:00"))
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
        fallback_lang = (language or "ar").strip().lower()
        if fallback_lang not in ("ar", "en", "fr"):
            fallback_lang = "ar"

        for recipient in recipients:
            phone = recipient.get("phone")
            if not phone:
                continue

            uid = recipient.get("user_id")
            uid_fs = (str(uid).strip() if uid else "") or ((normalize_phone(phone) or "").strip() or str(phone).strip())
            resolved_lang = await user_persistence.resolve_language_for_campaign_recipient(
                phone,
                firestore_user_id=uid_fs,
                fallback_language=fallback_lang,
            )

            placeholders = {
                "customer_name": recipient.get("customer_name", "عميلنا العزيز"),
                "phone_number": contact_phone,
                "appointment_date": "",
                "appointment_time": "",
                "branch_name": "",
                "service_name": "",
                "next_appointment_date": "",
            }
            metadata = {
                "campaign_id": campaign_id,
                "customer_id": recipient.get("customer_id"),
                "reference_date": recipient.get("last_chat_date"),
                "source": "chatted_no_crm_lead_campaign",
                "user_id": recipient.get("user_id"),
            }

            if send_mode == "schedule" and schedule_dt is not None:
                message_id = smart_messaging.schedule_message(
                    customer_phone=phone,
                    message_type=self.TEMPLATE_ID,
                    send_at=schedule_dt,
                    placeholders=placeholders,
                    language=resolved_lang,
                    service_id=None,
                    service_name=None,
                    metadata=metadata,
                )
                if message_id:
                    queued_count += 1
                else:
                    failed.append({"phone": phone, "reason": "Failed to queue message"})
                continue

            content = smart_messaging.get_message_content(
                message_type=self.TEMPLATE_ID,
                language=resolved_lang,
                placeholders=placeholders,
            )
            if not content:
                failed.append({
                    "phone": phone,
                    "reason": "Template content is empty or missing",
                })
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
                    failed.append({
                        "phone": phone,
                        "reason": "dry_run (not delivered)",
                    })
                elif result.get("success"):
                    sent_count += 1
                    message_logs_service.log_message(
                        customer_id=recipient.get("customer_id") or phone,
                        template_type=self.TEMPLATE_ID,
                        appointment_id=None,
                        campaign_id=campaign_id,
                        reference_date=recipient.get("last_chat_date"),
                        extra={
                            "phone": phone,
                            "customer_name": recipient.get("customer_name"),
                            "user_id": recipient.get("user_id"),
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


chatted_no_crm_lead_campaign_service = ChattedNoCrmLeadCampaignService()
