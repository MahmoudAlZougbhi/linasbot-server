"""Smart messaging status, counts, customers, and queue log routes (LOC split)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from modules.core import app
from services.smart_messaging_catalog import DEPRECATED_TEMPLATE_IDS, normalize_template_id


@app.get("/api/smart-messaging/status")
async def get_scheduler_status() -> Any:
    """Get the current status of the Smart Messaging Scheduler"""
    try:
        from modules.core import app as fastapi_app
        from services.smart_messaging import smart_messaging

        # Check if scheduler is running
        scheduler_running = False
        scheduled_jobs = []

        if hasattr(fastapi_app.state, "scheduler"):
            scheduler = fastapi_app.state.scheduler
            scheduler_running = scheduler.running

            # Get all scheduled jobs
            for job in scheduler.get_jobs():
                scheduled_jobs.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                        "trigger": str(job.trigger),
                    }
                )

        # Get statistics from smart_messaging service
        statistics: dict[str, Any] = {
            "total_scheduled": len(smart_messaging.scheduled_messages),
            "total_sent": len(smart_messaging.sent_messages_log),
            "by_type": {},
        }

        # Count by message type
        for _msg_id, msg_data in smart_messaging.scheduled_messages.items():
            msg_type = normalize_template_id(msg_data.get("message_type", "unknown"))
            if msg_type in DEPRECATED_TEMPLATE_IDS:
                continue
            if msg_type not in statistics["by_type"]:
                statistics["by_type"][msg_type] = {"scheduled": 0, "sent": 0}

            if msg_data.get("status") in ["scheduled", "pending_approval", "sending"]:
                statistics["by_type"][msg_type]["scheduled"] += 1
            elif msg_data.get("status") in ("sent", "would_send"):
                statistics["by_type"][msg_type]["sent"] += 1

        # Add sent messages statistics
        for sent_msg in smart_messaging.sent_messages_log:
            msg_type = normalize_template_id(sent_msg.get("type", "unknown"))
            if msg_type in DEPRECATED_TEMPLATE_IDS:
                continue
            if msg_type not in statistics["by_type"]:
                statistics["by_type"][msg_type] = {"scheduled": 0, "sent": 0}
            statistics["by_type"][msg_type]["sent"] += 1

        return {
            "success": True,
            "scheduler_running": scheduler_running,
            "scheduled_jobs": scheduled_jobs,
            "statistics": statistics,
            "last_check": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"❌ Error getting scheduler status: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _apply_count_date_filter(
    msg_type: str,
    send_date_str: Any,
    apt_date: Any,
    send_at: Any,
    now: Any,
    today_str: Any,
    yesterday_str: Any,
    start_of_month_str: Any,
    start_of_next_month_str: Any,
    past_24h: Any,
    next_24h: Any,
) -> bool:
    """Apply same date filtering as frontend for a message."""
    if msg_type == "reminder_24h":
        if send_at:
            return bool(past_24h <= send_at <= next_24h)
        return True
    if msg_type == "thank_you_message_sent_after_session":
        return (send_date_str or "") == today_str or not send_date_str
    if msg_type == "session_feedback":
        return (send_date_str or "") == today_str or not send_date_str
    if msg_type == "missed_yesterday":
        return cast(bool, apt_date == yesterday_str or send_date_str == yesterday_str)
    if msg_type == "sent_17_days_after_last_session_new":
        if send_date_str:
            return bool(start_of_month_str <= send_date_str < start_of_next_month_str)
        return False
    if msg_type in ("sent_for_pause", "whatsapp_lead_no_booking"):
        return True
    return True


@app.get("/api/smart-messaging/counts")
async def get_message_counts() -> Any:
    """
    Get counts for each message type. Source of truth: API-only (smart_messaging_customers_service).
    Counts = number of customers in each category; never negative. If API fails, fallback to 0.
    """
    try:
        from services.smart_messaging_customers_service import get_all_counts_and_customers

        data = await get_all_counts_and_customers()
        counts = data.get("counts", {})
        # Ensure no negative and all keys present
        for key in (
            "reminder_24h",
            "thank_you_message_sent_after_session",
            "session_feedback",
            "sent_17_days_after_last_session_new",
            "missed_yesterday",
            "sent_for_pause",
            "whatsapp_lead_no_booking",
        ):
            if key not in counts:
                counts[key] = 0
            counts[key] = max(0, int(counts[key]))
        total = max(0, sum(counts.values()))
        return {"success": True, "counts": counts, "total": total}
    except Exception as e:
        print(f"Error getting message counts: {e}")
        import traceback

        traceback.print_exc()
        fallback_counts: dict[str, Any] = {
            "reminder_24h": 0,
            "thank_you_message_sent_after_session": 0,
            "session_feedback": 0,
            "sent_17_days_after_last_session_new": 0,
            "missed_yesterday": 0,
            "sent_for_pause": 0,
            "whatsapp_lead_no_booking": 0,
        }
        return {"success": True, "counts": fallback_counts, "total": 0}


@app.get("/api/smart-messaging/customers-by-category")
async def get_customers_by_category(category: str) -> Any:
    """
    Get the list of customers for a given category (source of truth from APIs).
    Returns: { success, category, count, customers: [ { customer_name, phone, appointment_id, status, type, reason, date, time, details, action_state } ] }
    If count > 0 the list will not be empty; if list is empty count is 0.
    """
    try:
        from services.smart_messaging_customers_service import get_customers_by_category as fetch_customers

        canonical = normalize_template_id(category) if category else ""
        if not canonical or canonical in ("sent_for_pause", "whatsapp_lead_no_booking"):
            return {"success": True, "category": canonical or category, "count": 0, "customers": []}
        customers = await fetch_customers(canonical)
        customers = list(customers) if customers else []
        count = max(0, len(customers))
        return {"success": True, "category": canonical, "count": count, "customers": customers}
    except Exception as e:
        print(f"Error getting customers by category: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e), "category": category or "", "count": 0, "customers": []}


@app.get("/api/smart-messaging/messages")
async def get_messages_detail(status: str = "all", message_type: str | None = None) -> Any:
    """
    Get detailed message information from in-memory scheduled messages.

    Args:
        status: "sent", "scheduled", or "all"
        message_type: Filter by specific message type (e.g., "sent_17_days_after_last_session_new")

    Returns:
        List of scheduled/sent messages with customer info and content preview
    """
    try:
        from datetime import datetime as dt

        from services.smart_messaging import smart_messaging

        messages = []
        seen_message_ids = set()  # Track message IDs to avoid duplicates

        # Mapping of message types to friendly names and reasons
        message_type_names = {
            "reminder_24h": "24-Hour Appointment Reminder",
            "thank_you_message_sent_after_session": "thank_you_message_sent_after_session",
            "session_feedback": "session_feedback",
            "sent_17_days_after_last_session_new": "sent_17_days_after_last_session_new",
            "missed_yesterday": "Missed Yesterday Follow-up",
            "sent_for_pause": "sent_for_pause",
            "whatsapp_lead_no_booking": "WhatsApp Lead (No CRM) Campaign",
        }

        # Get messages from in-memory scheduled_messages dict
        # Shows both scheduled and sent messages with their actual status
        for message_id, msg_data in smart_messaging.scheduled_messages.items():
            msg_status = msg_data.get("status", "unknown")

            # Filter by status parameter
            if status == "scheduled" and msg_status not in ["scheduled", "pending_approval", "sending"]:
                continue
            if status == "sent" and msg_status not in ("sent", "would_send"):
                continue
            # status == "all" shows everything

            # Extract customer name from placeholders
            customer_name = msg_data.get("placeholders", {}).get("customer_name", "Unknown")
            msg_type = normalize_template_id(msg_data.get("message_type", "unknown"))
            if msg_type in DEPRECATED_TEMPLATE_IDS:
                continue

            # Filter by message_type if specified
            if message_type and msg_type != normalize_template_id(message_type):
                continue

            language = msg_data.get("language", "ar")
            placeholders = msg_data.get("placeholders", {})

            # Use edited content if present, otherwise render from template
            content_preview = msg_data.get("content")
            if not content_preview:
                content_preview = smart_messaging.get_message_content(msg_type, language, placeholders) or ""

                send_at_val = msg_data.get("send_at")
                sent_at_val = msg_data.get("sent_at")
                created_at_val = msg_data.get("created_at")
                message_entry = {
                    "message_id": message_id,
                    "customer_phone": msg_data.get("customer_phone", ""),
                    "customer_name": customer_name,
                    "message_type": msg_type,
                    "language": language,
                    "status": msg_status,  # Use actual status (scheduled/sent/pending_approval)
                    "reason": message_type_names.get(msg_type, msg_type),
                    "scheduled_for": send_at_val.isoformat() if send_at_val is not None else None,
                    "send_at": send_at_val.isoformat() if send_at_val is not None else None,
                    "sent_at": sent_at_val.isoformat() if sent_at_val is not None else None,
                    "created_at": created_at_val.isoformat() if created_at_val is not None else None,
                    "template_data": placeholders,
                    "content_preview": content_preview[:100] + "..." if len(content_preview) > 100 else content_preview,
                    "full_content": content_preview,
                    "time_until_send": str(send_at_val - dt.now())
                    if send_at_val is not None and msg_status == "scheduled"
                    else None,
                }

            messages.append(message_entry)
            seen_message_ids.add(message_id)

        # Note: Sent messages are now included from scheduled_messages dict
        # (status changes from "scheduled" to "sent" when message is sent)
        # No need for separate sent_messages_log lookup

        # Sort by date (newest first)
        messages.sort(key=lambda x: x.get("sent_at") or x.get("send_at") or "9999", reverse=True)

        return {"success": True, "status_filter": status, "total_messages": len(messages), "messages": messages}

    except Exception as e:
        print(f"❌ Error getting messages detail: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/collect-scheduled")
async def collect_scheduled_messages() -> Any:
    """
    Collect all future appointments and generate to-be-sent messages log.
    This scans all customers and their appointments to identify which messages
    should be sent in the future (24h reminders, next-day check-ins, etc.)

    Returns: List of messages to be sent with send times
    """
    try:
        from services.scheduled_messages_collector import scheduled_messages_collector

        # Collect all scheduled messages
        messages_to_send = await scheduled_messages_collector.collect_all_scheduled_messages()

        return {
            "success": True,
            "message": f"Collected {len(messages_to_send)} messages to be sent",
            "total_messages": len(messages_to_send),
            "messages_to_send": messages_to_send,
        }

    except Exception as e:
        print(f"❌ Error collecting scheduled messages: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/scheduled-log")
async def get_scheduled_messages_log() -> Any:
    """
    Get the to-be-sent messages log from file.
    Contains all future appointments that will have messages sent.

    Query params:
    - status: "pending" | "sent" | "failed" | "all" (default: "all")
    """
    try:
        from services.scheduled_messages_collector import scheduled_messages_collector

        # Get query parameter
        status = "all"  # Default

        messages = scheduled_messages_collector.load_or_create_log()

        # Filter by status if specified
        if status != "all":
            messages = [m for m in messages if m.get("status") == status]

        # Count by status
        pending_count = len([m for m in messages if m.get("status") == "pending"])
        sent_count = len([m for m in messages if m.get("status") == "sent"])
        failed_count = len([m for m in messages if m.get("status") == "failed"])

        return {
            "success": True,
            "total_messages": len(messages),
            "statistics": {"pending": pending_count, "sent": sent_count, "failed": failed_count},
            "messages": messages,
        }

    except Exception as e:
        print(f"❌ Error getting scheduled messages log: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/pending-messages")
async def get_pending_messages() -> Any:
    """
    Get all messages that are pending and should be sent NOW or soon.
    These are messages with:
    - status = "pending"
    - send_datetime <= current_time (ready to send immediately)

    Returns: List of messages ready to be sent
    """
    try:
        from services.scheduled_messages_collector import scheduled_messages_collector

        messages = scheduled_messages_collector.get_pending_messages()

        return {"success": True, "pending_count": len(messages), "messages": messages}

    except Exception as e:
        print(f"❌ Error getting pending messages: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}

