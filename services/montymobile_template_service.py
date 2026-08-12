"""
MontyMobile Template Message Service
Handles sending WhatsApp template messages via MontyMobile API

Payload mixin: montymobile_template_service_payload (LOC split).
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
    # whatsapp_lead_no_booking has its own Meta template (0 body vars); see templates.whatsapp_lead_no_booking
}


class MontyMobileTemplateService(MontyMobileTemplatePayloadMixin):
    """Service for sending WhatsApp template messages via MontyMobile"""

    # Legacy omni-apis + /notification/... paths now return nginx 404; same stack as montymobile_adapter.
    _DEFAULT_TEMPLATE_BASE = "https://whatsapp-notification.montymobile.com"
    _DEFAULT_TEMPLATE_PATH = "/api/v2/WhatsappApi/send-whatsapp"

    def __init__(self) -> None:
        # Load template configuration
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "montymobile_templates.json")
        try:
            if not os.path.exists(config_path):
                print(f"❌ MontyMobile config not found at: {config_path}")
                self.config = {}
                self.templates = {}
                self.api_config = {}
                return
            with open(config_path, encoding="utf-8") as f:
                self.config = json.load(f)
            self.templates = self.config.get("templates", {})
            self.api_config = dict(self.config.get("api_config", {}) or {})
            # Credentials must come from environment — never from tracked JSON
            env_key = (os.getenv("MONTYMOBILE_API_KEY") or "").strip()
            if env_key:
                self.api_config["api_key"] = env_key
            else:
                self.api_config["api_key"] = ""
            # Never keep a committed secret if one slipped into JSON
            if self.api_config.get("api_key") and not env_key:
                self.api_config["api_key"] = ""
            print(f"✅ Loaded {len(self.templates)} MontyMobile templates")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Error loading MontyMobile config: {e}")
            self.config = {}
            self.templates = {}
            self.api_config = {}

    def _resolve_send_url(self) -> str:
        """
        Full POST URL for template send. Migrates deprecated omni-apis /notification/... URLs
        (nginx 404) to whatsapp-notification host used by MontyMobileAdapter.send-session.
        """
        cfg = self.api_config or {}
        base = (cfg.get("base_url") or "").strip().rstrip("/")
        endpoint = (cfg.get("endpoint") or "").strip()
        if endpoint and not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        url = f"{base}{endpoint}" if base and endpoint else ""

        legacy = "omni-apis.montymobile.com" in url or "/notification/api/v2/" in url
        if legacy or not url:
            base = (os.getenv("MONTYMOBILE_BASE_URL") or self._DEFAULT_TEMPLATE_BASE).strip().rstrip("/")
            path = (os.getenv("MONTYMOBILE_TEMPLATE_PATH") or self._DEFAULT_TEMPLATE_PATH).strip()
            if path and not path.startswith("/"):
                path = "/" + path
            url = f"{base}{path}"
            print(
                f"📌 Monty template send URL (notification stack): {url} "
                f"(legacy omni-apis /notification path is deprecated)"
            )
        return url

    def get_template_info(self, template_id: str) -> dict | None:
        """Get template information by ID"""
        canonical = normalize_template_id(template_id)
        template = self.templates.get(canonical)
        if template:
            return cast(dict[Any, Any] | None, template)

        alt = _LEGACY_TEMPLATE_CONFIG_KEYS.get(canonical, canonical)
        return self.templates.get(alt)

    def templates_are_text_only(self) -> bool:
        """
        When True: never attach header components and never use dashboard/env/default image URLs
        for Monty template sends. Set in config/montymobile_templates.json api_config.
        """
        return bool((self.api_config or {}).get("templates_are_text_only", False))

    def _resolve_template_config_key(self, canonical_id: str) -> str:
        """JSON object key under templates{} used for this logical id (after normalize_template_id)."""
        if canonical_id in self.templates:
            return canonical_id
        return _LEGACY_TEMPLATE_CONFIG_KEYS.get(canonical_id, canonical_id)

    def resolve_whatsapp_language_for_template(
        self,
        template: dict[str, Any],
        requested: str,
        template_id_for_log: str = "",
    ) -> str:
        """
        Pick template.language.code for Meta/Monty. Respects force_whatsapp_language when set.
        If the user's language is not approved for this template in montymobile_templates.json,
        falls back to ar, then en, fr, then any available key (avoids KeyError / wrong code).
        """
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
        """
        Name sent to Monty/Meta must match WhatsApp Manager exactly for this WABA.
        Override per template: env MONTY_META_NAME_<CANONICAL> e.g. MONTY_META_NAME_SENT_FOR_PAUSE.
        Or set meta_template_name / whatsapp_template_name on the template JSON block.
        """
        env_key = "MONTY_META_NAME_" + canonical_id.upper().replace("-", "_")
        env_override = os.getenv(env_key, "").strip()
        if env_override:
            print(f"   Outbound template name from {env_key}={env_override!r}")
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
            return f"legacy_map {canonical_id!r} -> config key {mapped!r} (Meta name={self.templates[mapped].get('name')!r})"
        return "unknown"

    async def send_template_message(
        self, template_id: str, phone_number: str, language: str = "ar", parameters: dict[str, str | None] | None = None
    ) -> dict:
        """
        Send a template message via MontyMobile API

        Args:
            template_id: Template identifier
            phone_number: Recipient phone number
            language: Language code
            parameters: Template parameter values

        Returns:
            Response dict with success status and data
        """
        try:
            if not self._normalize_recipient_for_monty_template(phone_number):
                return {
                    "success": False,
                    "error": f"Invalid phone number for WhatsApp template (use Lebanon mobile, e.g. 9617XXXXXXX): {phone_number!r}",
                }
            # Build payload
            payload = self.build_template_payload(template_id, phone_number, language, parameters)
            if not payload:
                return {
                    "success": False,
                    "error": (
                        f"Template '{template_id}' not found in Monty config, or payload build failed "
                        f"(check language/body variables vs Meta template)"
                    ),
                }

            tpl_meta = self.get_template_info(normalize_template_id(template_id))
            # When templates_are_text_only: never require or validate image headers.
            assume_hdr = bool((self.api_config or {}).get("assume_whatsapp_image_header", False))
            hcfg = (tpl_meta or {}).get("header") if tpl_meta else {}
            header_opt_out = isinstance(hcfg, dict) and str(hcfg.get("format", "")).strip().lower() == "none"
            comps = (payload.get("template") or {}).get("components") or []
            has_header = any(str(c.get("type", "")).lower() == "header" for c in comps)
            if not self.templates_are_text_only() and assume_hdr and tpl_meta and not header_opt_out and not has_header:
                try:
                    from services.message_preview_service import message_preview_service

                    _probe = message_preview_service.get_template_header_image_url()
                    print(
                        "⚠️ Monty template: header component missing after build; "
                        f"get_template_header_image_url() len={len(_probe)} "
                        f"(app_settings_file={getattr(message_preview_service, 'app_settings_file', '?')})"
                    )
                except Exception as _pe:
                    print(f"⚠️ Monty header diagnostic: {_pe}")
                return {
                    "success": False,
                    "error": (
                        "WhatsApp template requires a HEADER (image). No header image URL was found. "
                        'Do one of: (1) Dashboard → Smart Messaging → "Template header image URL" → Save; '
                        "(2) server env MONTY_TEMPLATE_HEADER_IMAGE_URL or WHATSAPP_TEMPLATE_HEADER_IMAGE_URL; "
                        "(3) file settings/template_header_image_url.txt next to app_settings.json (one HTTPS URL per line); "
                        "(4) config/montymobile_templates.json → api_config.default_header_component.image_link."
                    ),
                }

            canon = normalize_template_id(template_id)
            self._log_outbound_template_payload(template_id, canon, payload)

            # Prepare headers — api key from environment only
            api_key = (self.api_config.get("api_key") or os.getenv("MONTYMOBILE_API_KEY") or "").strip()
            if not api_key:
                return {
                    "success": False,
                    "error": "MONTYMOBILE_API_KEY is not configured",
                }

            # Fail closed: never send via Monty when this source number is Cloud-bound.
            monty_source = str((self.api_config.get("source") or "")).strip()
            try:
                from services.whatsapp_cloud.legacy_isolation import cloud_blocks_monty_send

                if monty_source and cloud_blocks_monty_send(monty_source):
                    return {
                        "success": False,
                        "error": "cloud_bound_number",
                        "message": "MontyMobile template send blocked for Cloud-bound WhatsApp number",
                    }
            except Exception as exc:
                return {
                    "success": False,
                    "error": "legacy_isolation_check_failed",
                    "message": f"MontyMobile template send refused: isolation check failed ({exc})",
                }

            headers = {"Tenant": self.api_config["tenant"], "api-key": api_key, "Content-Type": "application/json"}

            # Send request (URL may override legacy montymobile_templates.json omni-apis paths)
            url = self._resolve_send_url()

            print(f"📤 Sending template '{template_id}' to {phone_number} (lang: {language})")
            print(f"   URL: {url}")
            print(f"   Tenant: {self.api_config['tenant']}")
            print(f"   API ID: {self.api_config['api_id']}")
            print(f"   API Key: configured={bool(api_key)}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)

                print(f"   Response: {response.status_code}")

                if response.status_code == 200:
                    try:
                        response_data = response.json()

                        def _extract_message_id(body: dict[str, Any]) -> str | None:
                            if not isinstance(body, dict):
                                return None
                            data = body.get("data")
                            if isinstance(data, dict):
                                raw = data.get("messageId") or data.get("message_id")
                                if raw is not None and str(raw).strip():
                                    return str(raw).strip()
                            raw = body.get("messageId") or body.get("message_id")
                            if raw is not None and str(raw).strip():
                                return str(raw).strip()
                            return None

                        if response_data.get("success"):
                            message_id = _extract_message_id(response_data)
                            invalid = (
                                not message_id
                                or message_id.lower() == "unknown"
                                or message_id.lower() in ("null", "none", "n/a")
                            )
                            if invalid:
                                print(
                                    "❌ Monty success=true but no usable messageId — "
                                    "treating as failure (WhatsApp delivery not confirmed)"
                                )
                                return {
                                    "success": False,
                                    "error": (
                                        "Monty reported success but returned no messageId — "
                                        "check Monty dashboard / template name and API response body"
                                    ),
                                    "response": response_data,
                                    "template_id": template_id,
                                    "phone_number": phone_number,
                                }
                            print(f"✅ Template sent successfully! Message ID: {message_id}")
                            to_used = payload.get("to") if isinstance(payload, dict) else None
                            return {
                                "success": True,
                                "message_id": message_id,
                                "template_id": template_id,
                                "phone_number": phone_number,
                                "recipient_to_monty": to_used,
                                "language": language,
                                "response": response_data,
                            }
                        else:
                            error_msg = response_data.get("message", "Unknown error")
                            print(f"❌ Template send failed: {error_msg}")

                            return {
                                "success": False,
                                "error": error_msg,
                                "outbound_template_name": (payload.get("template") or {}).get("name"),
                                "response": response_data,
                            }
                    except json.JSONDecodeError:
                        raw_txt = (response.text or "")[:2000]
                        print(f"⚠️ Could not parse Monty template response JSON: {raw_txt[:500]}")
                        return {
                            "success": False,
                            "error": "Monty returned HTTP 200 but non-JSON body; delivery not confirmed",
                            "response_text": raw_txt,
                        }
                else:
                    raw = response.text or ""
                    error_text = raw[:2000]
                    print(f"❌ HTTP Error {response.status_code}: {error_text[:500]}")
                    monty_message = None
                    try:
                        err_body = response.json()
                        if isinstance(err_body, dict):
                            monty_message = (
                                err_body.get("message")
                                or err_body.get("error")
                                or err_body.get("title")
                                or err_body.get("detail")
                            )
                            if isinstance(monty_message, list):
                                monty_message = monty_message[0] if monty_message else None
                    except Exception as parse_err:
                        print(
                            f"⚠️ Monty template HTTP {response.status_code}: "
                            f"could not parse error JSON: {parse_err}"
                        )
                    if not monty_message and raw.strip():
                        monty_message = raw.strip()[:500]

                    return {
                        "success": False,
                        "error": (
                            f"MontyMobile/WhatsApp API HTTP {response.status_code} "
                            f"(dashboard route OK — provider rejected the request)"
                        ),
                        "monty_message": (str(monty_message)[:800] if monty_message else None),
                        "outbound_template_name": (payload.get("template") or {}).get("name"),
                        "response_text": error_text,
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


# Global instance
montymobile_template_service = MontyMobileTemplateService()
