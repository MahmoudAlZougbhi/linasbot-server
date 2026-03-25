"""
Smart Messaging API Module
Handles message templates endpoints for the dashboard
"""

import json
import os
import tempfile
import uuid
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from fastapi import Body

from modules.core import app
from utils.utils import save_conversation_message_to_firestore
from services.message_logs_service import message_logs_service
from services.chatted_no_crm_lead_campaign_service import chatted_no_crm_lead_campaign_service
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


from storage.persistent_storage import (
    MESSAGE_TEMPLATES_FILE,
    MESSAGE_TEMPLATES_LOCK_FILE,
    SMART_MESSAGING_DIR,
    ensure_dirs,
)

_TEMPLATE_FILE = MESSAGE_TEMPLATES_FILE
_TEMPLATE_LOCK_FILE = MESSAGE_TEMPLATES_LOCK_FILE
_PROCESS_TEMPLATE_LOCK = threading.Lock()


@contextmanager
def _template_store_lock():
    """Lock template read/write across threads and (on Unix) processes."""
    ensure_dirs()
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
    ensure_dirs()
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(SMART_MESSAGING_DIR),
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


def _monty_whatsapp_language_code(saved_lang: str) -> str:
    """Map persisted user language to MontyMobile template language code."""
    s = (saved_lang or "ar").strip().lower()
    if s == "franco":
        return "ar"
    if s in ("ar", "en", "fr"):
        return s
    return "ar"


@app.get("/api/smart-messaging/user-language")
async def smart_messaging_resolve_user_language(phone: str):
    """Resolve saved user language from phone (runtime memory / same keys as the bot)."""
    try:
        from services.user_persistence_service import user_persistence
        from utils.phone_utils import normalize_phone

        raw = (phone or "").strip()
        if not raw:
            return {"success": False, "error": "phone query parameter is required"}

        user_lang, source = await user_persistence.enrich_language_from_firestore_if_needed(raw)
        return {
            "success": True,
            "language": user_lang,
            "language_source": source,
            "template_language": _monty_whatsapp_language_code(user_lang),
            "normalized_phone": normalize_phone(raw),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/send-test-template")
async def send_test_template_message(request_data: Dict[str, Any]):
    """Send a test message using MontyMobile template"""
    try:
        from services.montymobile_template_service import montymobile_template_service
        from services.user_persistence_service import user_persistence

        template_id = normalize_template_id(request_data.get('template_id', '').strip())
        phone_number = request_data.get('phone_number', '').strip()
        explicit = request_data.get("language")
        if isinstance(explicit, str):
            explicit = explicit.strip().lower()
        else:
            explicit = None
        if explicit in (None, "", "auto"):
            explicit = None

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

        if explicit:
            if explicit not in ("ar", "en", "fr", "franco"):
                return {
                    "success": False,
                    "error": "Invalid language; use ar, en, fr, franco, or omit for auto (saved per user)",
                }
            user_language = explicit
            language_source = "manual"
        else:
            user_language, language_source = user_persistence.resolve_language_for_phone(phone_number)

        language = _monty_whatsapp_language_code(user_language)
        
        # Get template info to know which parameters it needs
        template_info = montymobile_template_service.get_template_info(template_id)
        
        if not template_info:
            return {
                "success": False,
                "error": f"Template '{template_id}' not found"
            }
        
        # Body variable names + count (must match montymobile_template_service / Meta {{1}}..{{n}})
        langs = template_info.get("languages") or {}
        template_lang = langs.get(language) or {}
        if not template_lang and language != "ar":
            template_lang = langs.get("ar") or {}
        raw_specs = template_lang.get("body_parameters")
        if not isinstance(raw_specs, list) or not raw_specs:
            raw_specs = template_lang.get("parameters") or []
        template_param_names = [x for x in raw_specs if isinstance(x, str)]

        raw_count = template_lang.get("parameters_count")
        try:
            n_body = (
                max(0, int(raw_count))
                if raw_count is not None
                else len(template_param_names)
            )
        except (TypeError, ValueError):
            n_body = len(template_param_names)

        from services.smart_messaging_test_context import (
            resolve_real_test_template_placeholders,
            validate_test_placeholders_for_template,
        )

        vals, ph_meta = await resolve_real_test_template_placeholders(phone_number)
        _test_correlation_id = uuid.uuid4().hex[:10]

        test_parameters = {
            param: str(vals.get(param) or "").strip()
            for param in template_param_names
        }
        _fill_order = [
            "customer_name",
            "appointment_date",
            "appointment_time",
            "branch_name",
            "service_name",
            "phone_number",
            "next_appointment_date",
        ]
        _fill_list = [str(vals[k] or "").strip() for k in _fill_order if str(vals.get(k) or "").strip()]
        _fi = 0
        for i in range(len(template_param_names), n_body):
            if _fill_list:
                test_parameters[str(i + 1)] = _fill_list[_fi % len(_fill_list)]
                _fi += 1
            else:
                test_parameters[str(i + 1)] = ""

        _ph_err = validate_test_placeholders_for_template(
            template_param_names, n_body, test_parameters, ph_meta
        )
        if _ph_err:
            return {
                "success": False,
                "error": _ph_err,
                "placeholder_meta": ph_meta,
                "test_correlation_id": _test_correlation_id,
            }

        # Monty often accepts the HTTP request while **WhatsApp (Meta)** may not deliver a second
        # template if the rendered body matches a very recent send to the same user (utility dedupe).
        # A tiny per-click suffix keeps CRM-based values accurate but avoids byte-identical repeats.
        # Send JSON `"vary_test_payload": false` to disable (strict pixel-perfect preview vs CRM only).
        _vary_raw = request_data.get("vary_test_payload", True)
        if isinstance(_vary_raw, str):
            _vary = _vary_raw.strip().lower() not in ("0", "false", "no", "off")
        else:
            _vary = bool(_vary_raw)
        _vary_applied = False
        if _vary and n_body > 0:
            _stamp = datetime.utcnow().strftime("%H%M%S")
            _token = f" test#{_stamp}"
            _tweaked = False
            for _k in ("service_name", "customer_name", "branch_name", "appointment_time"):
                if str(test_parameters.get(_k) or "").strip():
                    test_parameters[_k] = str(test_parameters[_k]).rstrip() + _token
                    _tweaked = True
                    break
            if not _tweaked:
                for _i in range(n_body, 0, -1):
                    _sk = str(_i)
                    if str(test_parameters.get(_sk) or "").strip():
                        test_parameters[_sk] = str(test_parameters[_sk]).rstrip() + _token
                        _tweaked = True
                        break
            _vary_applied = _tweaked
        
        print(
            f"📋 Template '{template_id}' body slots: count={n_body} "
            f"named={template_param_names!r}"
        )
        print(f"📋 Sending parameters: {test_parameters}")
        
        print(
            f"📤 Sending test template '{template_id}' to {phone_number} "
            f"(user_lang={user_language} source={language_source} monty_lang={language})"
        )

        if not montymobile_template_service.templates_are_text_only():
            from services.message_preview_service import message_preview_service

            _hdr_req = (
                request_data.get("header_image_url")
                or request_data.get("template_header_image_url")
                or request_data.get("templateHeaderImageUrl")
                or ""
            )
            _hdr_req = str(_hdr_req).strip()
            _hdr_saved = message_preview_service.get_template_header_image_url()
            _hdr_eff = _hdr_req or _hdr_saved
            if _hdr_eff:
                test_parameters = {**test_parameters, "header_image": _hdr_eff}
            print(
                f"📋 Template header image: {'OK (' + str(len(_hdr_eff)) + ' chars)' if _hdr_eff else 'MISSING'} "
                f"(request={'yes' if _hdr_req else 'no'}, saved={'yes' if _hdr_saved else 'no'})"
            )
        else:
            print("📋 Template send: templates_are_text_only — skipping header_image injection for test send")

        # Send template message
        result = await montymobile_template_service.send_template_message(
            template_id=template_id,
            phone_number=phone_number,
            language=language,
            parameters=test_parameters
        )

        if isinstance(result, dict):
            result = {
                **result,
                "user_language": user_language,
                "template_language": language,
                "language_source": language_source,
                "test_correlation_id": _test_correlation_id,
                "placeholder_source": ph_meta.get("source"),
                "placeholder_warnings": ph_meta.get("warnings") or [],
                "vary_test_payload_applied": _vary_applied,
            }
            if n_body == 0:
                result["test_template_note"] = (
                    "This template has no body variables in Meta — every test send is identical. "
                    "WhatsApp often delivers only one per recipient per window; use another number "
                    "or wait before retesting."
                )

        if isinstance(result, dict) and result.get("success"):
            if template_id == "post_session_feedback":
                try:
                    from services.post_session_feedback_rating_service import (
                        mark_awaiting_post_session_feedback_after_send,
                    )

                    mark_awaiting_post_session_feedback_after_send(
                        phone_number,
                        appointment_id=None,
                        reference_date=None,
                        smart_message_id=f"test:{_test_correlation_id}",
                    )
                except Exception as _psf_mark_e:
                    print(f"⚠️ Test template: post_session_feedback awaiting flag: {_psf_mark_e}")
            mid = result.get("message_id")
            if mid and str(mid).strip() and str(mid).strip().lower() != "unknown":
                try:
                    from utils.utils import save_conversation_message_to_firestore
                    from services.smart_messaging import smart_messaging
                    from services.message_preview_service import message_preview_service

                    # Live Chat should show the same body the customer sees (placeholders filled),
                    # matching scheduled sends that persist `content` / rendered template text.
                    _ph_display = {
                        k: v
                        for k, v in test_parameters.items()
                        if isinstance(k, str)
                        and not str(k).isdigit()
                        and k != "header_image"
                    }
                    _display_text = smart_messaging.get_message_content(
                        template_id, language, _ph_display
                    )
                    if not _display_text:
                        _display_text = message_preview_service.render_message_preview(
                            template_id, language, _ph_display
                        )
                    if (
                        not _display_text
                        or not str(_display_text).strip()
                        or str(_display_text).startswith("[")
                    ):
                        _display_text = (
                            f"Template «{template_id}» (test send, lang {language}). "
                            f"Parameters: {test_parameters}"
                        )

                    await save_conversation_message_to_firestore(
                        user_id=phone_number,
                        role="ai",
                        text=_display_text,
                        conversation_id=None,
                        user_name=vals.get("customer_name") or "Customer",
                        phone_number=phone_number,
                        metadata={
                            "source": "smart_message",
                            "type": template_id,
                            "monty_message_id": mid,
                            "template_language": language,
                            "recipient_to_monty": result.get("recipient_to_monty"),
                            "test_send": True,
                            "test_correlation_id": _test_correlation_id,
                            "placeholder_source": ph_meta.get("source"),
                        },
                    )
                except Exception as _fs_err:
                    print(f"⚠️ Test template: could not log to Firestore: {_fs_err}")
            else:
                print(
                    "⚠️ Test template: Monty reported success but no messageId — "
                    "not logging to Live Chat (WhatsApp delivery unconfirmed)."
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

            if result.get("dry_run"):
                print(f"📋 [DRY-RUN] Test message would be sent to {phone_number} (room {room_id})")
                return {
                    "success": True,
                    "message": f"Dry-run: message not sent (local/sandbox mode). Would send to {phone_number}.",
                    "phone_number": phone_number,
                    "room_id": room_id,
                    "dry_run": True
                }
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


def _apply_count_date_filter(msg_type: str, send_date_str, apt_date, send_at, now, today_str,
                             yesterday_str, start_of_month_str, start_of_next_month_str,
                             past_24h, next_24h) -> bool:
    """Apply same date filtering as frontend for a message."""
    if msg_type == "reminder_24h":
        if send_at:
            return past_24h <= send_at <= next_24h
        return True
    if msg_type == "post_session_feedback":
        return (send_date_str or "") == today_str or not send_date_str
    if msg_type == "attended_yesterday":
        return (send_date_str or "") == today_str or not send_date_str
    if msg_type == "missed_yesterday":
        return apt_date == yesterday_str or send_date_str == yesterday_str
    if msg_type == "twenty_day_followup":
        if send_date_str:
            return start_of_month_str <= send_date_str < start_of_next_month_str
        return False
    if msg_type in ("missed_paused_appointment", "whatsapp_lead_no_booking"):
        return True
    return True


@app.get("/api/smart-messaging/counts")
async def get_message_counts():
    """
    Get counts for each message type. Source of truth: API-only (smart_messaging_customers_service).
    Counts = number of customers in each category; never negative. If API fails, fallback to 0.
    """
    try:
        from services.smart_messaging_customers_service import get_all_counts_and_customers

        data = await get_all_counts_and_customers()
        counts = data.get("counts", {})
        # Ensure no negative and all keys present
        for key in ("reminder_24h", "post_session_feedback", "attended_yesterday",
                    "twenty_day_followup", "missed_yesterday", "missed_paused_appointment",
                    "whatsapp_lead_no_booking"):
            if key not in counts:
                counts[key] = 0
            counts[key] = max(0, int(counts[key]))
        total = max(0, sum(counts.values()))
        return {
            "success": True,
            "counts": counts,
            "total": total
        }
    except Exception as e:
        print(f"Error getting message counts: {e}")
        import traceback
        traceback.print_exc()
        counts = {
            "reminder_24h": 0,
            "post_session_feedback": 0,
            "attended_yesterday": 0,
            "twenty_day_followup": 0,
            "missed_yesterday": 0,
            "missed_paused_appointment": 0,
            "whatsapp_lead_no_booking": 0,
        }
        return {
            "success": True,
            "counts": counts,
            "total": 0
        }


@app.get("/api/smart-messaging/customers-by-category")
async def get_customers_by_category(category: str):
    """
    Get the list of customers for a given category (source of truth from APIs).
    Returns: { success, category, count, customers: [ { customer_name, phone, appointment_id, status, type, reason, date, time, details, action_state } ] }
    If count > 0 the list will not be empty; if list is empty count is 0.
    """
    try:
        from services.smart_messaging_customers_service import get_customers_by_category as fetch_customers

        canonical = normalize_template_id(category) if category else ""
        if not canonical or canonical in ("missed_paused_appointment", "whatsapp_lead_no_booking"):
            return {
                "success": True,
                "category": canonical or category,
                "count": 0,
                "customers": []
            }
        customers = await fetch_customers(canonical)
        customers = list(customers) if customers else []
        count = max(0, len(customers))
        return {
            "success": True,
            "category": canonical,
            "count": count,
            "customers": customers
        }
    except Exception as e:
        print(f"Error getting customers by category: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "category": category or "",
            "count": 0,
            "customers": []
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
            "post_session_feedback": "Post Session Feedback",
            "attended_yesterday": "Attended Yesterday (thank you, next day)",
            "twenty_day_followup": "One Month Follow Up",
            "missed_yesterday": "Missed Yesterday Follow-up",
            "missed_paused_appointment": "Missed This Month",
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


@app.get("/api/smart-messaging/template-header-status")
async def smart_messaging_template_header_status():
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
async def update_smart_messaging_settings(body: Dict[str, Any] = Body(...)):
    """Update smart messaging settings (JSON body merged into smartMessaging)."""
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.update_settings(body)
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

@app.get("/api/smart-messaging/post-session-feedback-ratings")
async def get_post_session_feedback_ratings_api(limit: int = 200):
    """Logged 1–5 star replies after Post Session Feedback template (analytics JSONL)."""
    from services.analytics_events import analytics

    rows = analytics.get_post_session_feedback_ratings(limit)
    return {"success": True, "ratings": rows}


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
async def preview_missed_paused_campaign(
    request_data: Dict[str, Any] = Body(default_factory=dict),
):
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
async def send_missed_paused_campaign(request_data: Dict[str, Any]):
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
    request_data: Dict[str, Any] = Body(default_factory=dict),
):
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
    request_data: Dict[str, Any] = Body(default_factory=dict),
):
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
