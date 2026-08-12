"""
WhatsApp Cloud template message service.

Sends approved WhatsApp template messages via Meta Graph API.
Legacy MontyMobile HTTP transport is disabled (Decision #9 — Meta Cloud-only).

Payload mixin: montymobile_template_service_payload (LOC split; Cloud payload shape).
"""

from __future__ import annotations

import json
import os
from typing import Any, cast

import httpx

from services.montymobile_template_service_payload import MontyMobileTemplatePayloadMixin
from services.smart_messaging_catalog import normalize_template_id

# Internal IDs that map to a different key under config/templates (and thus a different Meta `name`).
_LEGACY_TEMPLATE_CONFIG_KEYS: dict[str, str] = {
    "post_session_feedback": "thank_you_message_sent_after_session",
    "twenty_day_followup": "sent_17_days_after_last_session_new",
    "one_month_followup": "sent_17_days_after_last_session_new",
    "missed_paused_appointment": "sent_for_pause",
    "missed_this_month": "sent_for_pause",
    "attended_yesterday": "session_feedback",
}

_CLOUD_TEMPLATES_REL = ("config", "whatsapp_cloud_templates.json")
_GRAPH_VERSION = (os.getenv("WHATSAPP_GRAPH_API_VERSION") or "v19.0").strip() or "v19.0"


class MontyMobileTemplateService(MontyMobileTemplatePayloadMixin):
    """Template send via Meta Cloud (legacy class name retained for callers/tests)."""

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "..", *_CLOUD_TEMPLATES_REL)
        # One-time migration: if Cloud file missing but legacy Monty JSON present, do not load Monty
        # credentials — fail closed on empty templates instead of Monty HTTP.
        try:
            if not os.path.exists(config_path):
                print(f"❌ WhatsApp Cloud templates config not found at: {config_path}")
                self.config = {}
                self.templates = {}
                self.api_config = {}
                return
            with open(config_path, encoding="utf-8") as f:
                self.config = json.load(f)
            self.templates = self.config.get("templates", {})
            self.api_config = dict(self.config.get("api_config", {}) or {})
            print(f"✅ Loaded {len(self.templates)} WhatsApp Cloud templates")
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"❌ Error loading WhatsApp Cloud templates config: {e}")
            self.config = {}
            self.templates = {}
            self.api_config = {}

    def get_template_info(self, template_id: str) -> dict | None:
        """Get template information by ID"""
        canonical = normalize_template_id(template_id)
        template = self.templates.get(canonical)
        if template:
            return cast(dict[Any, Any] | None, template)

        alt = _LEGACY_TEMPLATE_CONFIG_KEYS.get(canonical, canonical)
        return self.templates.get(alt)

    def templates_are_text_only(self) -> bool:
        """When True: never attach header image components for template sends."""
        return bool((self.api_config or {}).get("templates_are_text_only", False))

    def _resolve_template_config_key(self, canonical_id: str) -> str:
        if canonical_id in self.templates:
            return canonical_id
        return _LEGACY_TEMPLATE_CONFIG_KEYS.get(canonical_id, canonical_id)

    def resolve_whatsapp_language_for_template(
        self,
        template: dict[str, Any],
        requested: str,
        template_id_for_log: str = "",
    ) -> str:
        """Pick template.language.code for Meta Cloud."""
        langs = template.get("languages") or {}
        rid = (requested or "ar").strip().lower()
        if rid == "franco":
            rid = "ar"
        tid = template_id_for_log or "?"

        forced = str(template.get("force_whatsapp_language") or "").strip().lower()
        if forced and forced in langs:
            if rid != forced:
                print(f"⚠️ [{tid}] force_whatsapp_language={forced!r} overrides requested={rid!r}")
            return forced

        if rid in langs:
            return rid
        for fb in ("ar", "en", "fr"):
            if fb in langs:
                print(
                    f"⚠️ [{tid}] WhatsApp template language {rid!r} not in config; using {fb!r} "
                    f"(add that language under languages{{}} or approve it in Meta)"
                )
                return fb
        if langs:
            first = next(iter(langs.keys()))
            print(f"⚠️ [{tid}] WhatsApp template language {rid!r} not in config; using {first!r}")
            return str(first)
        return rid

    def _outbound_template_name(self, template: dict[str, Any], canonical_id: str) -> str:
        env_key = "WHATSAPP_META_NAME_" + canonical_id.upper().replace("-", "_")
        env_override = os.getenv(env_key, "").strip()
        if not env_override:
            # Legacy env alias still honored during migration
            env_override = os.getenv("MONTY_META_NAME_" + canonical_id.upper().replace("-", "_"), "").strip()
        if env_override:
            print(f"   Outbound template name from env={env_override!r}")
            return env_override
        return str(
            template.get("meta_template_name")
            or template.get("whatsapp_template_name")
            or template.get("name")
            or canonical_id
        ).strip()

    def _describe_template_resolution(self, requested_id: str, canonical_id: str) -> str:
        norm = normalize_template_id(requested_id)
        if norm != requested_id:
            return f"alias {requested_id!r} -> {norm!r}"
        if canonical_id in self.templates:
            return "direct"
        mapped = _LEGACY_TEMPLATE_CONFIG_KEYS.get(canonical_id)
        if mapped and mapped in self.templates:
            return f"legacy_map {canonical_id!r} -> config key {mapped!r}"
        return "unknown"

    def _meta_cloud_credentials(self) -> tuple[str, str] | None:
        token = (os.getenv("WHATSAPP_API_TOKEN") or "").strip()
        phone_number_id = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
        if not token or not phone_number_id:
            return None
        return token, phone_number_id

    async def send_template_message(
        self, template_id: str, phone_number: str, language: str = "ar", parameters: dict[str, str | None] | None = None
    ) -> dict:
        """Send a template message via Meta WhatsApp Cloud API (no Monty HTTP)."""
        try:
            if not self._normalize_recipient_for_monty_template(phone_number):
                return {
                    "success": False,
                    "error": (
                        f"Invalid phone number for WhatsApp template "
                        f"(use Lebanon mobile, e.g. 9617XXXXXXX): {phone_number!r}"
                    ),
                }

            creds = self._meta_cloud_credentials()
            if not creds:
                return {
                    "success": False,
                    "error": (
                        "Meta Cloud template send refused: WHATSAPP_API_TOKEN and "
                        "WHATSAPP_PHONE_NUMBER_ID are required (MontyMobile HTTP disabled)."
                    ),
                }
            api_token, phone_number_id = creds

            payload = self.build_template_payload(template_id, phone_number, language, parameters)
            if not payload:
                return {
                    "success": False,
                    "error": (
                        f"Template '{template_id}' not found in Cloud templates config, or payload build failed "
                        f"(check language/body variables vs Meta template)"
                    ),
                }

            tpl_meta = self.get_template_info(normalize_template_id(template_id))
            assume_hdr = bool((self.api_config or {}).get("assume_whatsapp_image_header", False))
            hcfg = (tpl_meta or {}).get("header") if tpl_meta else {}
            header_opt_out = isinstance(hcfg, dict) and str(hcfg.get("format", "")).strip().lower() == "none"
            comps = (payload.get("template") or {}).get("components") or []
            has_header = any(str(c.get("type", "")).lower() == "header" for c in comps)
            if not self.templates_are_text_only() and assume_hdr and tpl_meta and not header_opt_out and not has_header:
                return {
                    "success": False,
                    "error": (
                        "WhatsApp template requires a HEADER (image). No header image URL was found. "
                        "Set Dashboard Smart Messaging template header image URL, or env "
                        "WHATSAPP_TEMPLATE_HEADER_IMAGE_URL / MONTY_TEMPLATE_HEADER_IMAGE_URL."
                    ),
                }

            canon = normalize_template_id(template_id)
            self._log_outbound_template_payload(template_id, canon, payload)

            # Meta Cloud body (never Monty source/apiId fields)
            cloud_body = {
                "messaging_product": "whatsapp",
                "to": payload.get("to"),
                "type": "template",
                "template": payload.get("template"),
            }
            url = f"https://graph.facebook.com/{_GRAPH_VERSION}/{phone_number_id}/messages"
            headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

            print(f"📤 Sending Cloud template '{template_id}' to ***{str(phone_number)[-4:] if phone_number else ''} (lang: {language})")
            print(f"   URL: graph.facebook.com/.../{phone_number_id}/messages")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=cloud_body)
                print(f"   Response: {response.status_code}")

                try:
                    response_data = response.json() if response.content else {}
                except json.JSONDecodeError:
                    response_data = {}

                if response.status_code >= 400:
                    err = response_data.get("error") if isinstance(response_data, dict) else None
                    err_msg = None
                    if isinstance(err, dict):
                        err_msg = err.get("message") or err.get("error_user_msg")
                    return {
                        "success": False,
                        "error": (
                            f"Meta Cloud template HTTP {response.status_code}: "
                            f"{err_msg or (response.text or '')[:500]}"
                        ),
                        "outbound_template_name": (payload.get("template") or {}).get("name"),
                        "response": response_data,
                    }

                # Meta success: messages[0].id
                message_id = None
                if isinstance(response_data, dict):
                    msgs = response_data.get("messages")
                    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                        message_id = str(msgs[0].get("id") or "").strip() or None

                if not message_id:
                    return {
                        "success": False,
                        "error": "Meta Cloud returned success without message id — delivery not confirmed",
                        "response": response_data,
                        "template_id": template_id,
                        "phone_number": phone_number,
                    }

                print(f"✅ Cloud template sent successfully! Message ID: {message_id}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "template_id": template_id,
                    "phone_number": phone_number,
                    "recipient_to_monty": payload.get("to"),  # legacy key kept for UI/metadata
                    "language": language,
                    "response": response_data,
                    "transport": "meta_cloud",
                }

        except httpx.TimeoutException:
            print("❌ Request timeout after 30 seconds")
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_all_templates(self) -> dict:
        """Get all available templates"""
        return {
            template_id: {
                "name": template["name"],
                "status": template["status"],
                "category": template["category"],
                "languages": list(template["languages"].keys()),
                "parameters": template["languages"].get("ar", {}).get("parameters", []),
            }
            for template_id, template in self.templates.items()
        }

    def is_template_approved(self, template_id: str) -> bool:
        """Check if a template is approved by WhatsApp"""
        template = self.templates.get(template_id)
        if not template:
            return False
        return cast(bool, template.get("status") == "APPROVED")


# Global instance (name retained for callers)
montymobile_template_service = MontyMobileTemplateService()
