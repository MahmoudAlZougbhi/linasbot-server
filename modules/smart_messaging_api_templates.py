"""Smart messaging template CRUD and language routes (LOC split)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.core import app
from modules.smart_messaging_api_store import (
    _build_template_record,
    _default_template_ids,
    _load_templates_from_disk,
    _migrate_templates,
    _save_templates_to_disk,
    _template_store_lock,
)
from services.smart_messaging_catalog import DEPRECATED_TEMPLATE_IDS, normalize_template_id


@app.get("/api/smart-messaging/templates")
async def get_message_templates() -> Any:
    """Get all message templates from JSON file"""
    try:
        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, changed = _migrate_templates(templates)
            if changed:
                _save_templates_to_disk(templates)

        return {"success": True, "templates": templates}
    except Exception as e:
        print(f"❌ Error getting templates: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/templates/{template_id}")
async def update_message_template(template_id: str, template_data: dict[str, Any]) -> Any:
    """Update or create a message template"""
    try:
        template_id = normalize_template_id(template_id)
        if template_id in DEPRECATED_TEMPLATE_IDS:
            return {"success": False, "error": f"Template '{template_id}' is deprecated and cannot be updated"}

        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, _ = _migrate_templates(templates)

            is_new = bool(template_data.get("isNew", False)) or template_id not in templates
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
                base_template["isCustom"] = bool(
                    template_data.get("isCustom", template_id not in _default_template_ids())
                )
                base_template["createdAt"] = now_iso
                templates[template_id] = base_template
                action = "created"
            else:
                # Merge updates so partial payloads never wipe other languages/fields
                for field in ("ar", "en", "fr", "name", "description"):
                    if field in template_data:
                        value = template_data[field]
                        templates[template_id][field] = "" if value is None else str(value)

                templates[template_id]["updatedAt"] = now_iso
                action = "updated"

            _save_templates_to_disk(templates)
            saved_template = templates[template_id]

        # Reload templates in smart_messaging service if available
        try:
            from services.smart_messaging import smart_messaging

            smart_messaging.message_templates[template_id] = {
                "ar": saved_template.get("ar", ""),
                "en": saved_template.get("en", ""),
                "fr": saved_template.get("fr", ""),
            }
        except ImportError:
            # Service may not be available in all deployments
            pass

        return {
            "success": True,
            "message": f"Template {action} successfully",
            "template_id": template_id,
            "template": saved_template,
        }
    except Exception as e:
        print(f"❌ Error updating template: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.delete("/api/smart-messaging/templates/{template_id}")
async def delete_message_template(template_id: str) -> Any:
    """Delete a custom message template"""
    try:
        template_id = normalize_template_id(template_id)
        # Default templates that cannot be deleted
        default_templates = _default_template_ids()

        if template_id in default_templates:
            return {"success": False, "error": "Cannot delete default templates"}

        with _template_store_lock():
            templates = _load_templates_from_disk()
            templates, _ = _migrate_templates(templates)

            if template_id not in templates:
                return {"success": False, "error": "Template not found"}

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

        return {"success": True, "message": "Template deleted successfully", "template_id": template_id}
    except Exception as e:
        print(f"❌ Error deleting template: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _whatsapp_template_language_code(saved_lang: str) -> str:
    """Map persisted user language to WhatsApp template language code."""
    s = (saved_lang or "ar").strip().lower()
    if s == "franco":
        return "ar"
    if s in ("ar", "en", "fr"):
        return s
    return "ar"


# Backward-compatible alias
_monty_whatsapp_language_code = _whatsapp_template_language_code


@app.get("/api/smart-messaging/user-language")
async def smart_messaging_resolve_user_language(phone: str) -> Any:
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
            "template_language": _whatsapp_template_language_code(user_lang),
            "normalized_phone": normalize_phone(raw),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
