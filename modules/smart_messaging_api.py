"""
Smart Messaging API Module
Handles message templates endpoints for the dashboard
"""

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from modules.core import app
from utils.utils import save_conversation_message_to_firestore
from services.message_logs_service import message_logs_service
from services.missed_paused_campaign_service import missed_paused_campaign_service
from services.smart_messaging_catalog import (
    CAMPAIGN_TEMPLATE_IDS,
    DAILY_TEMPLATE_IDS,
    DEPRECATED_TEMPLATE_IDS,
    TEMPLATE_METADATA,
    normalize_template_id,
)
from services.template_schedule_service import template_schedule_service

try:
    import fcntl
except ImportError:
    fcntl = None


_BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE_DIR / "data"
_TEMPLATE_FILE = _DATA_DIR / "message_templates.json"
_TEMPLATE_LOCK_FILE = _DATA_DIR / ".message_templates.lock"
_PROCESS_TEMPLATE_LOCK = threading.Lock()


@contextmanager
def _template_store_lock():
    """Lock template read/write across threads and (on Unix) processes."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with _PROCESS_TEMPLATE_LOCK:
        with open(_TEMPLATE_LOCK_FILE, "a+", encoding="utf-8") as lock_handle:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _load_templates_from_disk() -> Dict[str, Any]:
    if not _TEMPLATE_FILE.exists():
        return {}

    with open(_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        templates = json.load(f)

    if not isinstance(templates, dict):
        raise ValueError("Invalid templates file format: expected JSON object")

    return templates


def _save_templates_to_disk(templates: Dict[str, Any]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(_DATA_DIR),
        prefix="message_templates_",
        suffix=".json"
    )

    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
            json.dump(templates, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, _TEMPLATE_FILE)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _default_template_ids() -> List[str]:
    return list(DAILY_TEMPLATE_IDS) + list(CAMPAIGN_TEMPLATE_IDS)


def _build_template_record(template_id: str, source: Dict[str, Any] = None) -> Dict[str, Any]:
    source = source or {}
    meta = TEMPLATE_METADATA.get(template_id, {})
    record = {
        "name": str(source.get("name") or meta.get("name") or template_id),
        "description": str(source.get("description") or meta.get("description") or ""),
        "ar": str(source.get("ar", "")),
        "en": str(source.get("en", "")),
        "fr": str(source.get("fr", "")),
    }
    if source.get("isCustom"):
        record["isCustom"] = True
    if source.get("createdAt"):
        record["createdAt"] = source["createdAt"]
    if source.get("updatedAt"):
        record["updatedAt"] = source["updatedAt"]
    return record


def _migrate_templates(templates: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """
    Canonicalize legacy template IDs and hide deprecated defaults.
    """
    changed = False
    migrated: Dict[str, Any] = {}

    for template_id, template_data in (templates or {}).items():
        if not isinstance(template_data, dict):
            continue
        canonical_id = normalize_template_id(template_id)
        if canonical_id in DEPRECATED_TEMPLATE_IDS:
            changed = True
            continue

        existing = migrated.get(canonical_id, {})
        merged_source = dict(existing)
        merged_source.update(template_data)
        migrated[canonical_id] = _build_template_record(canonical_id, merged_source)

        if canonical_id != template_id:
            changed = True

    for template_id in _default_template_ids():
        if template_id not in migrated:
            migrated[template_id] = _build_template_record(template_id, {})
            changed = True

    return migrated, changed


@app.get("/api/smart-messaging/templates")
async def get_message_templates():
    """Get all message templates from JSON file"""
    try:
        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, changed = _migrate_templates(templates)
            if changed:
                _save_templates_to_disk(templates)

        return {
            "success": True,
            "templates": templates
        }
    except Exception as e:
        print(f"❌ Error getting templates: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/smart-messaging/templates/{template_id}")
async def update_message_template(template_id: str, template_data: Dict[str, Any]):
    """Update or create a message template"""
    try:
        template_id = normalize_template_id(template_id)
        if template_id in DEPRECATED_TEMPLATE_IDS:
            return {
                "success": False,
                "error": f"Template '{template_id}' is deprecated and cannot be updated"
            }

        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, _ = _migrate_templates(templates)

            is_new = bool(template_data.get('isNew', False)) or template_id not in templates
            now_iso = datetime.now().isoformat()

            # Check if creating a new template
            if is_new:
                base_template = _build_template_record(
                    template_id,
                    {
                        "name": template_data.get("name", template_id),
                        "description": template_data.get("description", ""),
                        "ar": template_data.get("ar", ""),
                        "en": template_data.get("en", ""),
                        "fr": template_data.get("fr", ""),
                    },
                )
                base_template["isCustom"] = bool(template_data.get("isCustom", template_id not in _default_template_ids()))
                base_template["createdAt"] = now_iso
                templates[template_id] = base_template
                action = "created"
            else:
                # Merge updates so partial payloads never wipe other languages/fields
                for field in ('ar', 'en', 'fr', 'name', 'description'):
                    if field in template_data:
                        value = template_data[field]
                        templates[template_id][field] = '' if value is None else str(value)

                templates[template_id]['updatedAt'] = now_iso
                action = "updated"

            _save_templates_to_disk(templates)
            saved_template = templates[template_id]

        # Reload templates in smart_messaging service if available
        try:
            from services.smart_messaging import smart_messaging
            smart_messaging.message_templates[template_id] = {
                'ar': saved_template.get('ar', ''),
                'en': saved_template.get('en', ''),
                'fr': saved_template.get('fr', '')
            }
        except ImportError:
            # Service may not be available in all deployments
            pass

        return {
            "success": True,
            "message": f"Template {action} successfully",
            "template_id": template_id,
            "template": saved_template
        }
    except Exception as e:
        print(f"❌ Error updating template: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.delete("/api/smart-messaging/templates/{template_id}")
async def delete_message_template(template_id: str):
    """Delete a custom message template"""
    try:
        template_id = normalize_template_id(template_id)
        # Default templates that cannot be deleted
        default_templates = _default_template_ids()

        if template_id in default_templates:
            return {
                "success": False,
                "error": "Cannot delete default templates"
            }

        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, _ = _migrate_templates(templates)

            if template_id not in templates:
                return {
                    "success": False,
                    "error": "Template not found"
                }

            # Delete the template
            del templates[template_id]
            _save_templates_to_disk(templates)

        # Remove from smart_messaging service if available
        try:
            from services.smart_messaging import smart_messaging
            if template_id in smart_messaging.message_templates:
                del smart_messaging.message_templates[template_id]
        except ImportError:
            pass

        return {
            "success": True,
            "message": "Template deleted successfully",
            "template_id": template_id
        }
    except Exception as e:
        print(f"❌ Error deleting template: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/smart-messaging/send-test-template")
async def send_test_template_message(request_data: Dict[str, Any]):
    """Send a test message using MontyMobile template"""
    try:
        from services.montymobile_template_service import montymobile_template_service
        
        template_id = normalize_template_id(request_data.get('template_id', '').strip())
        phone_number = request_data.get('phone_number', '').strip()
        language = request_data.get('language', 'ar')
        
        # Validate inputs
        if not template_id:
            return {
                "success": False,
                "error": "Template ID is required"
            }
        
        if not phone_number:
            return {
                "success": False,
                "error": "Phone number is required"
            }
        
        # Get template info to know which parameters it needs
        template_info = montymobile_template_service.get_template_info(template_id)
        
        if not template_info:
            return {
                "success": False,
                "error": f"Template '{template_id}' not found"
            }
        
        # Get the parameters this template expects
        template_params = template_info['languages'].get(language, {}).get('parameters', [])
        
        # Build test parameters - only include what the template needs
        all_test_values = {
            "customer_name": "Test Customer",
            "appointment_date": "2025-12-25",
            "appointment_time": "02:00 PM",
            "branch_name": "Lina's Laser Center",
            "service_name": "Laser Hair Removal",
            "phone_number": "+961 1 234 567",
            "next_appointment_date": "2026-01-15"
        }
        
        # Only include parameters that this template needs
        test_parameters = {
            param: all_test_values.get(param, f"test_{param}")
            for param in template_params
        }
        
        print(f"📋 Template '{template_id}' expects parameters: {template_params}")
        print(f"📋 Sending parameters: {test_parameters}")
        
        print(f"📤 Sending test template '{template_id}' to {phone_number}")
        
        # Send template message
        result = await montymobile_template_service.send_template_message(
            template_id=template_id,
            phone_number=phone_number,
            language=language,
            parameters=test_parameters
        )
        
        return result
        
    except Exception as e:
        print(f"❌ Error sending test template: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/smart-messaging/send-test")
async def send_test_message(request_data: Dict[str, Any]):
    """Send a test message to a phone number using template data (OLD METHOD - for backward compatibility)"""
    try:
        phone_number = request_data.get('phone_number', '').strip()
        message = request_data.get('message', '').strip()
        template_id = request_data.get('template_id', '')
        language = request_data.get('language', 'ar')

        # Validate inputs
        if not phone_number:
            return {
                "success": False,
                "error": "Phone number is required"
            }

        if not message:
            return {
                "success": False,
                "error": "Message content is empty"
            }

        print(f"📤 Sending test message to phone: {phone_number}")
        print(f"   Template: {template_id}")
        print(f"   Language: {language}")
        print(f"   Message preview: {message[:100]}...")

        # Normalize and clean the phone number for lookup
        phone_clean = phone_number.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        
        # Generate variations for matching
        phone_without_country = phone_clean.lstrip('961')  # Remove Lebanon country code
        phone_with_plus = f"+{phone_clean}"
        
        print(f"🔍 Searching for phone: {phone_number}")
        print(f"   Cleaned: {phone_clean}")
        print(f"   Without country: {phone_without_country}")
        
        print(f"🔍 Searching for phone: {phone_number}")
        print(f"   Cleaned: {phone_clean}")
        
        # Generate multiple phone variations for matching (handles different formats)
        phone_without_country = phone_clean.lstrip('961')  # Remove Lebanon country code
        phone_with_plus = f"+{phone_clean}"
        phone_with_plus_country = f"+961{phone_without_country}"
        
        print(f"   Variations to try:")
        print(f"     - {phone_clean}")
        print(f"     - {phone_without_country}")
        print(f"     - {phone_with_plus}")
        print(f"     - {phone_with_plus_country}")
        
        # For Qiscus: need to fetch the room_id from Firebase using the phone number
        try:
            from utils.utils import get_firestore_db
            import config
            
            # First, try to find the room_id from Firebase by searching through users
            db = get_firestore_db()
            if db:
                app_id = "linas-ai-bot-backend"
                users_collection = db.collection("artifacts").document(app_id).collection("users")
                
                # Search for user by phone number
                room_id = None
                found_match = False
                
                print(f"📂 Searching in Firebase for matching phone...")
                for user_doc in users_collection.stream():
                    user_id = user_doc.id
                    user_data = user_doc.to_dict() or {}
                    
                    # Phone data is stored at root level, NOT in customer_info
                    stored_phone_full = user_data.get("phone_full", "")
                    stored_phone_clean = user_data.get("phone_clean", "")
                    
                    # Log what we're checking
                    if stored_phone_full or stored_phone_clean:
                        print(f"   Checking user_id={user_id}:")
                        print(f"     phone_full: {stored_phone_full}")
                        print(f"     phone_clean: {stored_phone_clean}")
                    
                    # Clean both for comparison
                    stored_phone_full_clean = stored_phone_full.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
                    stored_phone_without_country = stored_phone_clean.lstrip('961') if stored_phone_clean else ""
                    
                    # Try multiple matching strategies
                    match_pairs = [
                        (stored_phone_clean, phone_clean),
                        (stored_phone_clean, phone_without_country),
                        (stored_phone_full_clean, phone_clean),
                        (stored_phone_full_clean, phone_without_country),
                        (stored_phone_full, phone_number),
                        (stored_phone_without_country, phone_without_country),
                    ]
                    
                    if any(stored == inputted for stored, inputted in match_pairs if stored and inputted):
                        room_id = user_id
                        found_match = True
                        print(f"     ✅ MATCH FOUND! room_id = {room_id}")
                        break
                
                if not found_match:
                    print(f"❌ Phone not found in Firebase. Checking config fallback...")
                    # Fall back to config lookup - config has room_id as keys
                    for user_id, user_data in config.user_data_whatsapp.items():
                        user_phone = user_data.get('phone_number', '')
                        if not user_phone:
                            continue
                        
                        user_phone_clean = user_phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
                        user_phone_without_country = user_phone_clean.lstrip('961')
                        
                        print(f"   Checking config user_id={user_id}:")
                        print(f"     phone: {user_phone}")
                        print(f"     cleaned: {user_phone_clean}")
                        
                        # Try matching with multiple variations
                        config_match_pairs = [
                            (user_phone_clean, phone_clean),
                            (user_phone_clean, phone_without_country),
                            (user_phone, phone_number),
                            (user_phone_without_country, phone_without_country),
                        ]
                        
                        if any(stored == inputted for stored, inputted in config_match_pairs if stored and inputted):
                            room_id = user_id
                            found_match = True
                            print(f"     ✅ MATCH FOUND in config! room_id = {room_id}")
                            break
                
                if not room_id:
                    return {
                        "success": False,
                        "error": f"Phone number {phone_number} not found. Make sure customer has an active conversation."
                    }
            else:
                return {
                    "success": False,
                    "error": "Database connection failed"
                }

            # Now send the message using Qiscus adapter with the room_id
            from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
            
            adapter = WhatsAppFactory.get_adapter()
            result = await adapter.send_text_message(
                to_number=room_id,
                message=message
            )

            if result.get("success"):
                print(f"✅ Test message sent successfully to {phone_number} (room {room_id})")

                # Save to conversation history for continuous context
                await save_conversation_message_to_firestore(
                    user_id=room_id,
                    role="ai",
                    text=message,
                    conversation_id=None,
                    user_name="Customer",
                    phone_number=phone_number,
                    metadata={
                        "source": "smart_message",
                        "type": template_id or "test_message"
                    }
                )
                print(f"💾 Saved test message to conversation history for {phone_number}")

                return {
                    "success": True,
                    "message": f"Test message sent to {phone_number}",
                    "phone_number": phone_number,
                    "room_id": room_id,
                    "template_id": template_id,
                    "language": language
                }
            else:
                error_msg = result.get("error", "Unknown error")
                print(f"❌ Failed to send test message to {phone_number} - {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to send message: {error_msg}"
                }

        except Exception as lookup_error:
            print(f"❌ Error looking up room or sending message: {lookup_error}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"Error: {str(lookup_error)}"
            }

    except Exception as e:
        print(f"❌ Error sending test message: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Failed to send test message: {str(e)}"
        }


@app.get("/api/smart-messaging/status")
async def get_scheduler_status():
    """Get the current status of the Smart Messaging Scheduler"""
    try:
        from modules.core import app as fastapi_app
        from services.smart_messaging import smart_messaging
        
        # Check if scheduler is running
        scheduler_running = False
        scheduled_jobs = []
        
        if hasattr(fastapi_app.state, 'scheduler'):
            scheduler = fastapi_app.state.scheduler
            scheduler_running = scheduler.running
            
            # Get all scheduled jobs
            for job in scheduler.get_jobs():
                scheduled_jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                    "trigger": str(job.trigger)
                })
        
        # Get statistics from smart_messaging service
        statistics = {
            "total_scheduled": len(smart_messaging.scheduled_messages),
            "total_sent": len(smart_messaging.sent_messages_log),
            "by_type": {}
        }
        
        # Count by message type
        for msg_id, msg_data in smart_messaging.scheduled_messages.items():
            msg_type = normalize_template_id(msg_data.get("message_type", "unknown"))
            if msg_type in DEPRECATED_TEMPLATE_IDS:
                continue
            if msg_type not in statistics["by_type"]:
                statistics["by_type"][msg_type] = {"scheduled": 0, "sent": 0}
            
            if msg_data.get("status") in ["scheduled", "pending_approval", "sending"]:
                statistics["by_type"][msg_type]["scheduled"] += 1
            elif msg_data.get("status") == "sent":
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
            "last_check": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ Error getting scheduler status: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/smart-messaging/counts")
async def get_message_counts():
    """
    Get counts for each message type (FAST endpoint for lazy loading).
    Only counts in-memory scheduled messages - no Firestore calls.
    Applies the same date filtering as the frontend dashboard.
    """
    try:
        from services.smart_messaging import smart_messaging
        from datetime import datetime as dt, timedelta

        # Initialize counts
        counts = {
            "reminder_24h": 0,
            "post_session_feedback": 0,
            "twenty_day_followup": 0,
            "missed_yesterday": 0,
            "attended_yesterday": 0,
            "missed_paused_appointment": 0,
        }

        # Date calculations for filtering (same as frontend)
        now = dt.now()
        today_str = now.strftime('%Y-%m-%d')
        yesterday = now - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')
        start_of_month_str = now.replace(day=1).strftime('%Y-%m-%d')
        # First day of next month
        if now.month == 12:
            next_month_start = dt(now.year + 1, 1, 1)
        else:
            next_month_start = dt(now.year, now.month + 1, 1)
        start_of_next_month_str = next_month_start.strftime('%Y-%m-%d')

        # Time boundaries for ±24h filters
        past_24h = now - timedelta(hours=24)
        next_24h = now + timedelta(hours=24)

        # Count all messages including sent (in-memory only - FAST)
        for msg_id, msg_data in smart_messaging.scheduled_messages.items():
            if msg_data.get("status") not in ["scheduled", "pending_approval", "sent", "sending"]:
                continue

            msg_type = normalize_template_id(msg_data.get("message_type", "unknown"))
            if msg_type in DEPRECATED_TEMPLATE_IDS:
                continue
            if msg_type not in counts:
                continue

            # Get dates for filtering
            send_at = msg_data.get("send_at")
            send_date_str = send_at.strftime('%Y-%m-%d') if send_at else None
            apt_date = msg_data.get("placeholders", {}).get("appointment_date")

            # Apply date filtering based on message type (same logic as frontend)
            include = False

            if msg_type == "reminder_24h":
                # Tomorrow reminders are generated daily; keep a 24h window view.
                if send_at:
                    include = past_24h <= send_at <= next_24h
                else:
                    include = True

            elif msg_type == "post_session_feedback":
                # Show messages scheduled for today only
                if send_date_str:
                    include = send_date_str == today_str
                else:
                    include = True

            elif msg_type == "missed_yesterday":
                # Show yesterday's missed appointments
                include = apt_date == yesterday_str or send_date_str == yesterday_str

            elif msg_type == "twenty_day_followup":
                # Show 20-day follow-ups scheduled within current month
                if send_date_str:
                    include = start_of_month_str <= send_date_str < start_of_next_month_str

            elif msg_type == "attended_yesterday":
                # Show messages scheduled for today
                if send_date_str:
                    include = send_date_str == today_str
                else:
                    include = True

            elif msg_type == "missed_paused_appointment":
                include = True

            if include:
                counts[msg_type] += 1

        total = sum(counts.values())

        return {
            "success": True,
            "counts": counts,
            "total": total
        }

    except Exception as e:
        print(f"Error getting message counts: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/smart-messaging/messages")
async def get_messages_detail(status: str = "all", message_type: str = None):
    """
    Get detailed message information from in-memory scheduled messages.

    Args:
        status: "sent", "scheduled", or "all"
        message_type: Filter by specific message type (e.g., "twenty_day_followup")

    Returns:
        List of scheduled/sent messages with customer info and content preview
    """
    try:
        from services.smart_messaging import smart_messaging
        from datetime import datetime as dt

        messages = []
        seen_message_ids = set()  # Track message IDs to avoid duplicates

        # Mapping of message types to friendly names and reasons
        message_type_names = {
            "reminder_24h": "24-Hour Appointment Reminder",
            "post_session_feedback": "Post-Session Feedback",
            "twenty_day_followup": "20-Day Follow-up",
            "missed_yesterday": "Missed Yesterday Follow-up",
            "attended_yesterday": "Thank You - Attended Yesterday",
            "missed_paused_appointment": "Missed Paused Appointment Campaign",
        }

        # Get messages from in-memory scheduled_messages dict
        # Shows both scheduled and sent messages with their actual status
        for message_id, msg_data in smart_messaging.scheduled_messages.items():
            msg_status = msg_data.get("status", "unknown")

            # Filter by status parameter
            if status == "scheduled" and msg_status not in ["scheduled", "pending_approval", "sending"]:
                continue
            if status == "sent" and msg_status != "sent":
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

            # Render the template content with placeholders
            content_preview = smart_messaging.get_message_content(
                msg_type,
                language,
                placeholders
            ) or ""

            message_entry = {
                "message_id": message_id,
                "customer_phone": msg_data.get("customer_phone", ""),
                "customer_name": customer_name,
                "message_type": msg_type,
                "language": language,
                "status": msg_status,  # Use actual status (scheduled/sent/pending_approval)
                "reason": message_type_names.get(msg_type, msg_type),
                "scheduled_for": msg_data.get("send_at").isoformat() if msg_data.get("send_at") else None,
                "send_at": msg_data.get("send_at").isoformat() if msg_data.get("send_at") else None,
                "sent_at": msg_data.get("sent_at").isoformat() if msg_data.get("sent_at") else None,
                "created_at": msg_data.get("created_at").isoformat() if msg_data.get("created_at") else None,
                "template_data": placeholders,
                "content_preview": content_preview[:100] + "..." if len(content_preview) > 100 else content_preview,
                "full_content": content_preview,
                "time_until_send": str(msg_data.get("send_at") - dt.now()) if msg_data.get("send_at") and msg_status == "scheduled" else None
            }

            messages.append(message_entry)
            seen_message_ids.add(message_id)

        # Note: Sent messages are now included from scheduled_messages dict
        # (status changes from "scheduled" to "sent" when message is sent)
        # No need for separate sent_messages_log lookup

        # Sort by date (newest first)
        messages.sort(
            key=lambda x: x.get("sent_at") or x.get("send_at") or "9999",
            reverse=True
        )

        return {
            "success": True,
            "status_filter": status,
            "total_messages": len(messages),
            "messages": messages
        }

    except Exception as e:
        print(f"❌ Error getting messages detail: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/smart-messaging/collect-scheduled")
async def collect_scheduled_messages():
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
            "messages_to_send": messages_to_send
        }
        
    except Exception as e:
        print(f"❌ Error collecting scheduled messages: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/smart-messaging/scheduled-log")
async def get_scheduled_messages_log():
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
            messages = [m for m in messages if m.get('status') == status]
        
        # Count by status
        pending_count = len([m for m in messages if m.get('status') == 'pending'])
        sent_count = len([m for m in messages if m.get('status') == 'sent'])
        failed_count = len([m for m in messages if m.get('status') == 'failed'])
        
        return {
            "success": True,
            "total_messages": len(messages),
            "statistics": {
                "pending": pending_count,
                "sent": sent_count,
                "failed": failed_count
            },
            "messages": messages
        }
        
    except Exception as e:
        print(f"❌ Error getting scheduled messages log: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/smart-messaging/pending-messages")
async def get_pending_messages():
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

        return {
            "success": True,
            "pending_count": len(messages),
            "messages": messages
        }

    except Exception as e:
        print(f"❌ Error getting pending messages: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


# ==========================================
# SMART MESSAGING SETTINGS & PREVIEW QUEUE
# ==========================================

@app.get("/api/smart-messaging/settings")
async def get_smart_messaging_settings():
    """Get smart messaging settings including global enabled state"""
    try:
        from services.message_preview_service import message_preview_service

        settings = message_preview_service.get_settings()
        return {
            "success": True,
            "settings": settings
        }
    except Exception as e:
        print(f"Error getting smart messaging settings: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/settings")
async def update_smart_messaging_settings(settings: Dict[str, Any]):
    """Update smart messaging settings"""
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.update_settings(settings)
        return result
    except Exception as e:
        print(f"Error updating smart messaging settings: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/toggle")
async def toggle_smart_messaging(request_data: Dict[str, Any]):
    """Toggle smart messaging on/off globally"""
    try:
        from services.message_preview_service import message_preview_service

        enabled = request_data.get('enabled', True)
        result = message_preview_service.toggle_smart_messaging(enabled)

        if result.get('success'):
            status_text = "enabled" if enabled else "disabled"
            print(f"Smart Messaging {status_text} via API")

        return result
    except Exception as e:
        print(f"Error toggling smart messaging: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# TEMPLATE SCHEDULE SETTINGS
# ==========================================

@app.get("/api/smart-messaging/template-schedules")
async def get_template_schedules():
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
async def update_template_schedule(template_id: str, request_data: Dict[str, Any]):
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
async def preview_missed_paused_campaign(filters: Dict[str, Any]):
    """Preview recipients for Missed Paused Appointment campaign."""
    try:
        result = await missed_paused_campaign_service.preview(filters or {})
        return result
    except Exception as e:
        print(f"Error previewing missed paused campaign: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/campaigns/missed-paused/send")
async def send_missed_paused_campaign(request_data: Dict[str, Any]):
    """Send now or schedule a Missed Paused Appointment campaign."""
    try:
        filters = request_data.get("filters", {}) if isinstance(request_data, dict) else {}
        send_mode = request_data.get("send_mode", "send_now")
        schedule_time = request_data.get("schedule_time")
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


@app.get("/api/smart-messaging/campaign-logs")
async def get_campaign_logs(limit: int = 50):
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
async def get_service_template_mappings():
    """Get all service-to-template mappings"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        result = service_template_mapping_service.get_all_mappings()
        return result
    except Exception as e:
        print(f"Error getting service mappings: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/service-mappings/{service_id}")
async def update_service_template_mapping(service_id: int, mapping_data: Dict[str, Any]):
    """Update template mapping for a specific service"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        templates = mapping_data.get('templates', {})
        service_name = mapping_data.get('service_name')

        result = service_template_mapping_service.update_mapping(
            service_id=service_id,
            templates=templates,
            service_name=service_name
        )
        return result
    except Exception as e:
        print(f"Error updating service mapping: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/services")
async def get_available_services():
    """Get list of all clinic services for mapping UI"""
    try:
        from services.service_template_mapping_service import service_template_mapping_service

        services = service_template_mapping_service.get_available_services()
        templates = service_template_mapping_service.get_available_templates()

        return {
            "success": True,
            "services": services,
            "templates": templates
        }
    except Exception as e:
        print(f"Error getting services: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# PREVIEW QUEUE ENDPOINTS
# ==========================================

@app.get("/api/smart-messaging/preview-queue/{message_id}")
async def get_preview_message_details(message_id: str):
    """Get full details of a single message from the preview queue"""
    try:
        from services.message_preview_service import message_preview_service

        # Get all messages and find the one we need
        all_messages = message_preview_service.get_pending_messages(status=None)

        for msg in all_messages:
            if msg.get("message_id") == message_id:
                return {
                    "success": True,
                    "message": msg
                }

        return {
            "success": False,
            "error": "Message not found"
        }
    except Exception as e:
        print(f"Error getting message details: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/preview-queue")
async def get_preview_queue(status: str = "pending_approval"):
    """
    Get messages pending approval with full details.

    Args:
        status: Filter by status (pending_approval, approved, rejected, sent, all)

    Returns messages with:
    - customer_name, customer_phone
    - template_id, service_type
    - rendered message content
    - scheduled_send_time
    - validation_status (errors if any)
    """
    try:
        from services.message_preview_service import message_preview_service

        if status == "all":
            status = None

        messages = message_preview_service.get_pending_messages(status=status)
        stats = message_preview_service.get_queue_stats()

        return {
            "success": True,
            "status_filter": status or "all",
            "total": len(messages),
            "statistics": stats,
            "messages": messages
        }
    except Exception as e:
        print(f"Error getting preview queue: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/approve")
async def approve_preview_message(message_id: str):
    """Approve a single message for sending"""
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.approve_message(message_id)
        return result
    except Exception as e:
        print(f"Error approving message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/reject")
async def reject_preview_message(message_id: str, request_data: Dict[str, Any] = None):
    """Reject/delete a message from the queue"""
    try:
        from services.message_preview_service import message_preview_service

        reason = request_data.get('reason') if request_data else None
        result = message_preview_service.reject_message(message_id, reason)
        return result
    except Exception as e:
        print(f"Error rejecting message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/edit")
async def edit_preview_message(message_id: str, request_data: Dict[str, Any]):
    """Edit message content before sending"""
    try:
        from services.message_preview_service import message_preview_service
        from services.smart_messaging import smart_messaging

        # First try to edit in preview queue
        result = message_preview_service.edit_message(message_id, request_data)

        if result.get('success'):
            return result

        # If not found in preview queue, try to edit in smart_messaging scheduled messages
        if message_id in smart_messaging.scheduled_messages:
            msg = smart_messaging.scheduled_messages[message_id]

            # Update the message content if provided
            if 'rendered_content' in request_data:
                msg['content'] = request_data['rendered_content']

            # Update scheduled send time if provided
            if 'scheduled_send_time' in request_data:
                from datetime import datetime
                try:
                    new_time = datetime.fromisoformat(request_data['scheduled_send_time'].replace('Z', '+00:00'))
                    msg['send_at'] = new_time
                except:
                    pass

            smart_messaging.scheduled_messages[message_id] = msg
            return {
                "success": True,
                "message": "Scheduled message updated successfully",
                "message_id": message_id
            }

        return {"success": False, "error": "Message not found in any queue"}
    except Exception as e:
        print(f"Error editing message: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/batch-approve")
async def batch_approve_messages(request_data: Dict[str, Any]):
    """Approve multiple messages at once"""
    try:
        from services.message_preview_service import message_preview_service

        message_ids = request_data.get('message_ids', [])
        if not message_ids:
            return {"success": False, "error": "No message IDs provided"}

        result = message_preview_service.batch_approve(message_ids)
        return result
    except Exception as e:
        print(f"Error batch approving messages: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/batch-reject")
async def batch_reject_messages(request_data: Dict[str, Any]):
    """Reject multiple messages at once"""
    try:
        from services.message_preview_service import message_preview_service

        message_ids = request_data.get('message_ids', [])
        reason = request_data.get('reason')

        if not message_ids:
            return {"success": False, "error": "No message IDs provided"}

        result = message_preview_service.batch_reject(message_ids, reason)
        return result
    except Exception as e:
        print(f"Error batch rejecting messages: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/validate")
async def validate_message(request_data: Dict[str, Any]):
    """
    Validate a message before queueing.
    Checks phone format, required variables, and message length.
    """
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.validate_message(request_data)
        return {
            "success": True,
            "validation": result
        }
    except Exception as e:
        print(f"Error validating message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/add")
async def add_to_preview_queue(request_data: Dict[str, Any]):
    """
    Add a message to the preview queue.
    Used for testing or manual message addition.
    """
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.add_to_preview_queue(request_data)
        return result
    except Exception as e:
        print(f"Error adding to preview queue: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/preview-queue/stats")
async def get_preview_queue_stats():
    """Get statistics about the preview queue"""
    try:
        from services.message_preview_service import message_preview_service

        stats = message_preview_service.get_queue_stats()
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        print(f"Error getting queue stats: {e}")
        return {"success": False, "error": str(e)}
