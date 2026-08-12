"""Smart messaging settings, schedules, campaigns, and service mappings (LOC split)."""

from __future__ import annotations

from typing import Any

from fastapi import Body

from modules.core import app
from services.chatted_no_crm_lead_campaign_service import chatted_no_crm_lead_campaign_service
from services.message_logs_service import message_logs_service
from services.missed_paused_campaign_service import missed_paused_campaign_service
from services.template_schedule_service import template_schedule_service


# ==========================================
# SMART MESSAGING SETTINGS & PREVIEW QUEUE
# ==========================================


@app.get("/api/smart-messaging/settings")
async def get_smart_messaging_settings() -> Any:
    """Get smart messaging settings including global enabled state"""
    try:
        from services.message_preview_service import message_preview_service

        settings = message_preview_service.get_settings()
        return {"success": True, "settings": settings}
    except Exception as e:
        print(f"Error getting smart messaging settings: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/template-header-status")
async def smart_messaging_template_header_status() -> Any:
    """
    Debug why template sends say "no header image URL": shows which sources are set on this server.
    Open in browser or curl while logged into the dashboard API.
    """
    try:
        from services.message_preview_service import message_preview_service

        diag = message_preview_service.diagnose_template_header_image_sources()
        return {"success": True, **diag}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/settings")
async def update_smart_messaging_settings(body: dict[str, Any] = Body(...)) -> Any:
    """Update smart messaging settings (JSON body merged into smartMessaging)."""
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.update_settings(body)
        return result
    except Exception as e:
        print(f"Error updating smart messaging settings: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/toggle")
async def toggle_smart_messaging(request_data: dict[str, Any]) -> Any:
    """Toggle smart messaging on/off globally"""
    try:
        from services.message_preview_service import message_preview_service

        enabled = request_data.get("enabled", True)
        result = message_preview_service.toggle_smart_messaging(enabled)

        if result.get("success"):
            status_text = "enabled" if enabled else "disabled"
            print(f"Smart Messaging {status_text} via API")

        return result
    except Exception as e:
        print(f"Error toggling smart messaging: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# TEMPLATE SCHEDULE SETTINGS
# ==========================================


@app.get("/api/smart-messaging/post-session-feedback-ratings")
async def get_post_session_feedback_ratings_api(limit: int = 200) -> Any:
    """Logged 1–5 star replies after Post Session Feedback template (analytics JSONL)."""
    from services.analytics_events import analytics

    rows = analytics.get_post_session_feedback_ratings(limit)
    return {"success": True, "ratings": rows}


@app.get("/api/smart-messaging/template-schedules")
async def get_template_schedules() -> Any:
    """Get per-template daily schedule settings."""
    try:
        schedules = template_schedule_service.get_all_schedules()
        enriched = {}
        for template_id, cfg in schedules.items():
            meta = TEMPLATE_METADATA.get(template_id, {})
            enriched[template_id] = {
                **cfg,
                "name": meta.get("name", template_id),
                "description": meta.get("description", ""),
            }

        return {
            "success": True,
            "timezone_default": "Asia/Beirut",
            "schedules": enriched,
        }
    except Exception as e:
        print(f"Error getting template schedules: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/template-schedules/{template_id}")
async def update_template_schedule(template_id: str, request_data: dict[str, Any]) -> Any:
    """Update enable/time/timezone for a template's daily schedule."""
    try:
        canonical_id = normalize_template_id(template_id)
        updated = template_schedule_service.update_schedule(canonical_id, request_data or {})
        return {
            "success": True,
            "template_id": canonical_id,
            "schedule": updated,
        }
    except Exception as e:
        print(f"Error updating template schedule: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# CAMPAIGN BUILDER (MISSED PAUSED APPOINTMENT)
# ==========================================


@app.post("/api/smart-messaging/campaigns/missed-paused/preview")
async def preview_missed_paused_campaign(
    request_data: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Preview recipients for Missed This Month campaign (BOC paused appointments; Meta template sent_for_pause)."""
    try:
        result = await missed_paused_campaign_service.preview(request_data or {})
        if result.get("success") and isinstance(result.get("recipients"), list):
            slim = []
            for r in result["recipients"]:
                if isinstance(r, dict):
                    slim.append({k: v for k, v in r.items() if k != "raw"})
                else:
                    slim.append(r)
            result = {**result, "recipients": slim}
        return result
    except Exception as e:
        print(f"Error previewing missed paused campaign: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/campaigns/missed-paused/send")
async def send_missed_paused_campaign(request_data: dict[str, Any]) -> Any:
    """Send Missed This Month (paused BOC) campaign; WhatsApp uses Meta template sent_for_pause (per-recipient language)."""
    try:
        filters = request_data.get("filters", {}) if isinstance(request_data, dict) else {}
        send_mode = request_data.get("send_mode", "send_now")
        schedule_time = request_data.get("schedule_time")
        # Fallback when no saved language is found for a recipient (default ar).
        language = request_data.get("language", "ar")
        result = await missed_paused_campaign_service.send_or_schedule(
            filters=filters,
            send_mode=send_mode,
            schedule_time=schedule_time,
            language=language,
        )
        return result
    except Exception as e:
        print(f"Error sending missed paused campaign: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/campaigns/whatsapp-leads-no-crm/preview")
async def preview_whatsapp_leads_no_crm_campaign(
    request_data: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Preview: Firestore-chatted users with no BOC customer file and no appointments (optional chat text service filter)."""
    try:
        result = await chatted_no_crm_lead_campaign_service.preview(request_data or {})
        return result
    except Exception as e:
        print(f"Error previewing whatsapp leads no-crm campaign: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/campaigns/whatsapp-leads-no-crm/send")
async def send_whatsapp_leads_no_crm_campaign(
    request_data: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Send or schedule WhatsApp lead campaign — manual only; per-recipient language from saved prefs / Firestore."""
    try:
        filters = request_data.get("filters", {}) if isinstance(request_data, dict) else {}
        send_mode = request_data.get("send_mode", "send_now")
        schedule_time = request_data.get("schedule_time")
        language = request_data.get("language", "ar")
        result = await chatted_no_crm_lead_campaign_service.send_or_schedule(
            filters=filters,
            send_mode=send_mode,
            schedule_time=schedule_time,
            language=language,
        )
        return result
    except Exception as e:
        print(f"Error sending whatsapp leads no-crm campaign: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/campaign-logs")
async def get_campaign_logs(limit: int = 50) -> Any:
    """Get recent campaign logs."""
    try:
        logs = message_logs_service.get_campaign_logs(limit=limit)
        return {
            "success": True,
            "total": len(logs),
            "campaign_logs": logs,
        }
    except Exception as e:
        print(f"Error fetching campaign logs: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# SERVICE-TEMPLATE MAPPING ENDPOINTS
# ==========================================


@app.get("/api/smart-messaging/service-mappings")
async def get_service_template_mappings() -> Any:
    """Get all service-to-template mappings"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        result = service_template_mapping_service.get_all_mappings()
        return result
    except Exception as e:
        print(f"Error getting service mappings: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/service-mappings/{service_id}")
async def update_service_template_mapping(service_id: int, mapping_data: dict[str, Any]) -> Any:
    """Update template mapping for a specific service"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        templates = mapping_data.get("templates", {})
        service_name = mapping_data.get("service_name")

        result = service_template_mapping_service.update_mapping(
            service_id=service_id, templates=templates, service_name=service_name
        )
        return result
    except Exception as e:
        print(f"Error updating service mapping: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/services")
async def get_available_services() -> Any:
    """Get list of all clinic services for mapping UI"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        services = service_template_mapping_service.get_available_services()
        templates = service_template_mapping_service.get_available_templates()

        return {"success": True, "services": services, "templates": templates}
    except Exception as e:
        print(f"Error getting services: {e}")
        return {"success": False, "error": str(e)}
