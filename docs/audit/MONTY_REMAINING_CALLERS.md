# Monty remaining callers (Wave 8 inventory)

**Generated:** Phase 1 Wave 8. No deletes. No Meta cutover.

## Call sites (non-audit)

```
docker-compose.prod.yml:23:      - MONTYMOBILE_API_KEY=${MONTYMOBILE_API_KEY}
modules/dashboard_api_health.py:73:    # MontyMobile outbound key required when WhatsApp provider is montymobile in production
modules/dashboard_api_health.py:74:    provider = (os.getenv("WHATSAPP_PROVIDER") or "montymobile").strip().lower()
modules/dashboard_api_health.py:75:    monty_configured = bool((os.getenv("MONTYMOBILE_API_KEY") or "").strip())
modules/dashboard_api_health.py:76:    if is_production_env() and provider == "montymobile":
modules/dashboard_api_health.py:77:        checks["montymobile_api_key"] = {"ok": monty_configured, "configured": monty_configured}
modules/dashboard_api_health.py:81:        checks["montymobile_api_key"] = {"ok": True, "configured": monty_configured, "required": False}
docker-compose.yml:46:      - MONTYMOBILE_API_KEY=${MONTYMOBILE_API_KEY}
modules/smart_messaging_api_templates.py:150:    """Map persisted user language to MontyMobile template language code."""
services/montymobile_template_service.py:2:MontyMobile Template Message Service
services/montymobile_template_service.py:3:Handles sending WhatsApp template messages via MontyMobile API
services/montymobile_template_service.py:5:Payload mixin: montymobile_template_service_payload (LOC split).
services/montymobile_template_service.py:16:from services.montymobile_template_service_payload import MontyMobileTemplatePayloadMixin
services/montymobile_template_service.py:31:class MontyMobileTemplateService(MontyMobileTemplatePayloadMixin):
services/montymobile_template_service.py:32:    """Service for sending WhatsApp template messages via MontyMobile"""
services/montymobile_template_service.py:34:    # Legacy omni-apis + /notification/... paths now return nginx 404; same stack as montymobile_adapter.
services/montymobile_template_service.py:35:    _DEFAULT_TEMPLATE_BASE = "https://whatsapp-notification.montymobile.com"
services/montymobile_template_service.py:40:        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "montymobile_templates.json")
services/montymobile_template_service.py:43:                print(f"❌ MontyMobile config not found at: {config_path}")
services/montymobile_template_service.py:53:            env_key = (os.getenv("MONTYMOBILE_API_KEY") or "").strip()
services/montymobile_template_service.py:61:            print(f"✅ Loaded {len(self.templates)} MontyMobile templates")
services/montymobile_template_service.py:63:            print(f"❌ Error loading MontyMobile config: {e}")
services/montymobile_template_service.py:71:        (nginx 404) to whatsapp-notification host used by MontyMobileAdapter.send-session.
services/montymobile_template_service.py:80:        legacy = "omni-apis.montymobile.com" in url or "/notification/api/v2/" in url
services/montymobile_template_service.py:82:            base = (os.getenv("MONTYMOBILE_BASE_URL") or self._DEFAULT_TEMPLATE_BASE).strip().rstrip("/")
services/montymobile_template_service.py:83:            path = (os.getenv("MONTYMOBILE_TEMPLATE_PATH") or self._DEFAULT_TEMPLATE_PATH).strip()
services/montymobile_template_service.py:106:        for Monty template sends. Set in config/montymobile_templates.json api_config.
services/montymobile_template_service.py:124:        If the user's language is not approved for this template in montymobile_templates.json,
services/montymobile_template_service.py:187:        Send a template message via MontyMobile API
services/montymobile_template_service.py:241:                        "(4) config/montymobile_templates.json → api_config.default_header_component.image_link."
services/montymobile_template_service.py:249:            api_key = (self.api_config.get("api_key") or os.getenv("MONTYMOBILE_API_KEY") or "").strip()
services/montymobile_template_service.py:253:                    "error": "MONTYMOBILE_API_KEY is not configured",
services/montymobile_template_service.py:257:            # Send request (URL may override legacy montymobile_templates.json omni-apis paths)
services/montymobile_template_service.py:368:                            f"MontyMobile/WhatsApp API HTTP {response.status_code} "
services/montymobile_template_service.py:409:montymobile_template_service = MontyMobileTemplateService()
modules/dashboard_api_lab_upload.py:35:    audio: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("montymobile")
modules/dashboard_api_lab_upload.py:171:    image: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("montymobile")
modules/smart_messaging_api_send_template.py:16:    """Send a test message using MontyMobile template"""
modules/smart_messaging_api_send_template.py:18:        from services.montymobile_template_service import montymobile_template_service
modules/smart_messaging_api_send_template.py:52:        template_info = montymobile_template_service.get_template_info(template_id)
modules/smart_messaging_api_send_template.py:57:        # Body variable names + count (must match montymobile_template_service / Meta {{1}}..{{n}})
modules/smart_messaging_api_send_template.py:58:        effective_lang = montymobile_template_service.resolve_whatsapp_language_for_template(
modules/smart_messaging_api_send_template.py:159:        if not montymobile_template_service.templates_are_text_only():
modules/smart_messaging_api_send_template.py:181:        result = await montymobile_template_service.send_template_message(
modules/webhook_handlers_photo.py:65:        elif current_provider == "montymobile":
modules/webhook_handlers_photo.py:66:            print("DEBUG: Using MontyMobile provider - downloading media via MontyMobile API")
modules/webhook_handlers_photo.py:68:            # Use MontyMobile's media download endpoint
modules/webhook_handlers_photo.py:72:                # MontyMobile media download endpoint (CORRECT - as provided by MontyMobile support)
modules/webhook_handlers_photo.py:75:                montymobile_headers = {"Tenant": adapter.tenant_id, "api-key": adapter.api_token}
modules/webhook_handlers_photo.py:77:                print(f"DEBUG: Downloading media from MontyMobile API: {media_api_url}")
modules/webhook_handlers_photo.py:82:                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
modules/webhook_handlers_photo.py:90:                    # Check if response is JSON (MontyMobile returns JSON with image data inside)
modules/webhook_handlers_photo.py:97:                        # MontyMobile might return base64 data or a URL
modules/webhook_handlers_photo.py:109:                                # MontyMobile returns {"data": {"data": "base64string"}}
modules/webhook_handlers_photo.py:209:                print(f"ERROR: Failed to download media from MontyMobile: {e}")
modules/webhook_handlers_photo.py:227:            if current_provider not in ("qiscus", "montymobile")
modules/webhook_handlers_voice.py:37:        elif current_provider == "montymobile":
modules/webhook_handlers_voice.py:38:            print("DEBUG: Using MontyMobile provider - downloading audio via MontyMobile API")
modules/webhook_handlers_voice.py:41:                # MontyMobile media download endpoint (same as images)
modules/webhook_handlers_voice.py:44:                montymobile_headers = {"Tenant": adapter.tenant_id, "api-key": adapter.api_token}
modules/webhook_handlers_voice.py:46:                print(f"DEBUG: Downloading audio from MontyMobile API: {media_api_url}")
modules/webhook_handlers_voice.py:51:                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
modules/webhook_handlers_voice.py:58:                    # Check if response is JSON (MontyMobile returns JSON with audio data inside)
modules/webhook_handlers_voice.py:76:                                # MontyMobile returns {"data": {"data": "base64string"}}
modules/webhook_handlers_voice.py:141:                print(f"ERROR: Failed to download audio from MontyMobile: {e}")
modules/dashboard_api_lab_message.py:49:        "hint": "Configure this EXACT URL in MontyMobile dashboard. If Response Body is null in Monty logs, the webhook URL is wrong or the server is unreachable. Set PUBLIC_URL in .env to your domain (e.g. https://linasaibot.com).",
services/message_preview_service_settings.py:124:    def _montymobile_templates_config_path(self) -> str:
services/message_preview_service_settings.py:125:        envp = os.getenv("MONTYMOBILE_TEMPLATES_CONFIG_PATH", "").strip()
services/message_preview_service_settings.py:131:            "montymobile_templates.json",
services/message_preview_service_settings.py:134:    def _default_header_url_from_montymobile_templates_file(self) -> str:
services/message_preview_service_settings.py:135:        """api_config.default_header_component.image_link in config/montymobile_templates.json."""
services/message_preview_service_settings.py:137:            path = self._montymobile_templates_config_path()
services/message_preview_service_settings.py:146:            print(f"⚠️ montymobile_templates.json default header: {ex}")
services/message_preview_service_settings.py:155:        mpath = self._montymobile_templates_config_path()
services/message_preview_service_settings.py:162:                "or montymobile_templates.json — if all are empty, you see the error."
services/message_preview_service_settings.py:176:            "montymobile_templates_config_path": mpath,
services/message_preview_service_settings.py:177:            "montymobile_templates_config_exists": os.path.isfile(mpath),
services/message_preview_service_settings.py:178:            "montymobile_default_header_link_nonempty": bool(
services/message_preview_service_settings.py:179:                self._default_header_url_from_montymobile_templates_file()
services/message_preview_service_settings.py:187:        Order: env → sidecar → dashboard JSON → montymobile_templates.json default → raw smartMessaging case-insensitive.
```

## Notes
- Keep Monty keys in `.env.example`.
- Isolation stays until Mahmoud approves cutover.
- `config/montymobile_templates.json` is KEEP (loaded by montymobile_template_service) — Wave 1 delete STOP/reclassified.
