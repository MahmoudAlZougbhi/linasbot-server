"""Deliver scheduled smart WhatsApp via approved templates (LOC split)."""

from __future__ import annotations

from typing import Any, cast

from services.smart_messaging_catalog import normalize_template_id


async def deliver_scheduled_smart_whatsapp(
    adapter: Any,
    *,
    phone: str,
    template_id: str,
    language: str,
    placeholders: dict[str, Any] | None,
    rendered_text: str,
) -> dict[str, Any]:
    """
    Proactive smart messages must use WhatsApp-approved templates outside the 24h session window.
    When the template exists in montymobile_templates.json, send via Monty template API;
    otherwise fall back to session text (only works if the user messaged recently).
    """
    from services.montymobile_template_service import montymobile_template_service
    from services.whatsapp_adapters.safe_send_adapter import _log_dry_run, _should_dry_run

    if _should_dry_run(phone):
        _log_dry_run(
            phone,
            "scheduled_smart",
            {"template_id": template_id, "mode": "template_or_session"},
        )
        return {"success": True, "dry_run": True}

    canonical = normalize_template_id(template_id)
    tpl_meta = montymobile_template_service.get_template_info(canonical)
    if tpl_meta:
        params: dict[str, str] = {}
        for k, v in (placeholders or {}).items():
            if v is None:
                continue
            params[str(k)] = str(v)
        lang = (language or "ar").strip()[:8] or "ar"
        return await montymobile_template_service.send_template_message(
            template_id=canonical,
            phone_number=phone,
            language=lang,
            parameters=cast(dict[str, str | None], params),
        )
    return {
        "success": False,
        "error": (
            f"Approved WhatsApp template is required for {canonical!r}; "
            "freeform session text is not allowed for scheduled/campaign sends."
        ),
        "template_required": True,
        "template_id": canonical,
    }


# Mapping of message types to friendly names
message_type_names = {
    "reminder_24h": "24-Hour Appointment Reminder",
    "thank_you_message_sent_after_session": "thank_you_message_sent_after_session",
    "sent_17_days_after_last_session_new": "sent_17_days_after_last_session_new",
    "missed_yesterday": "Missed Yesterday Follow-up",
    "sent_for_pause": "sent_for_pause",
    "whatsapp_lead_no_booking": "WhatsApp Lead (No CRM) Campaign",
    "session_feedback": "session_feedback",
}
