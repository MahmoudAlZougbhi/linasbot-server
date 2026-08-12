"""MontyMobile template payload builder mixin (LOC split)."""

from __future__ import annotations

import json
import re
from typing import Any

from services.smart_messaging_catalog import normalize_template_id
from utils.phone_utils import normalize_phone


class MontyMobileTemplatePayloadMixin:
    """Build Monty WhatsApp template payloads (header/body/recipient)."""

    def _resolve_template_header_components(
        self, template: dict[str, Any], template_lang: dict[str, Any], lookup: dict[str, str | None]
    ) -> list[dict[str, Any]]:
        """
        Build optional WhatsApp template header components. Skipped entirely when
        api_config.templates_are_text_only is True (body-only / text-only templates),
        unless api_config.send_empty_header_component is True — then we send
        {"type": "header", "parameters": []} for Meta templates with a fixed header
        and zero variable slots (Monty: "Header required" vs "0 parameters" mismatch).
        """
        api_cfg = self.api_config or {}
        send_empty = bool(api_cfg.get("send_empty_header_component", False))

        if self.templates_are_text_only():
            # Per-template: Meta has no HEADER section at all — do not send even an empty header.
            # (Global send_empty_header_component would add {"type":"header","parameters":[]}.)
            if template.get("omit_empty_header_component") is True:
                return []
            if send_empty:
                return [{"type": "header", "parameters": []}]
            return []

        out: list[dict[str, Any]] = []
        header_cfg = template.get("header")
        if not isinstance(header_cfg, dict):
            header_cfg = {}

        fmt = str(header_cfg.get("format") or header_cfg.get("type") or "").strip().lower()
        if fmt in ("none", "skip", "no", "false"):
            return out

        # 1) Explicit image header (per template or per-send lookup)
        image_link = (header_cfg.get("image_link") or header_cfg.get("link") or "").strip() or str(
            lookup.get("header_image") or lookup.get("image_url") or ""
        ).strip()
        # Same-file default (always honored): not the same as "global" dashboard/env chain.
        dc = (self.api_config or {}).get("default_header_component") or {}
        if not image_link and isinstance(dc, dict):
            image_link = str(dc.get("image_link") or dc.get("link") or "").strip()
        # When false: do not pull from env / dashboard / sidecar — only template, lookup, and
        # default_header_component above. When true: also message_preview_service chain.
        allow_global = bool((self.api_config or {}).get("allow_global_template_header_image_url", True))
        if not image_link and allow_global:
            try:
                from services.message_preview_service import message_preview_service

                # Includes env MONTY_/WHATSAPP_*, sidecar, dashboard JSON, default_header_component file
                image_link = message_preview_service.get_template_header_image_url()
            except Exception as ex:
                print(f"❌ Monty template header: could not read header image URL settings: {ex}")
                raise

        # IMAGE header: empty format + URL means "use default branded header for this template"
        if fmt in ("", "image", "img", "picture"):
            if image_link:
                out.append(
                    {
                        "type": "header",
                        "parameters": [{"type": "image", "image": {"link": image_link}}],
                    }
                )
                return out
            if fmt in ("image", "img", "picture"):
                print(
                    f"⚠️ Template '{template.get('name')}' expects IMAGE header but no URL — set "
                    f"template.header.image_link, MONTY_TEMPLATE_HEADER_IMAGE_URL, or "
                    f"api_config.default_header_component.link"
                )

        # 2) Variable TEXT header (legacy list on template or per-language)
        header_param_names = template.get("header_parameters")
        if not isinstance(header_param_names, list):
            header_param_names = template_lang.get("header_parameters") or []
        if isinstance(header_param_names, list) and header_param_names:
            tpl_name = str(template.get("name") or "").strip()
            hdr_vals = []
            for hp in header_param_names:
                if not isinstance(hp, str):
                    continue
                raw = lookup.get(hp)
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    raw = tpl_name
                hdr_vals.append({"type": "text", "text": str(raw)})
            if hdr_vals:
                out.append({"type": "header", "parameters": hdr_vals})

        if not out and send_empty:
            return [{"type": "header", "parameters": []}]
        return out

    def _build_body_component_parameters(
        self, template_lang: dict[str, Any], lookup: dict[str, Any]
    ) -> list[dict[str, str]]:
        """
        Build WhatsApp body `parameters` array. Meta matches by position; the array length must
        equal the template's body variable count. Prefer `parameters_count` from config when set
        so we still send the right number of slots if `parameters` names are missing/outdated.
        """
        raw_specs = template_lang.get("body_parameters")
        if not isinstance(raw_specs, list) or not raw_specs:
            raw_specs = template_lang.get("parameters") or []
        param_specs: list[str] = [x for x in raw_specs if isinstance(x, str)]

        raw_count = template_lang.get("parameters_count")
        if raw_count is not None:
            try:
                n_body = max(0, int(raw_count))
            except (TypeError, ValueError):
                n_body = len(param_specs)
        else:
            n_body = len(param_specs)

        if len(param_specs) > n_body > 0:
            _log = f"template_lang body specs len={len(param_specs)} > parameters_count={n_body}; trimming"
            print(f"⚠️ Monty template body: {_log}")
            param_specs = param_specs[:n_body]
        elif n_body > len(param_specs):
            print(
                f"⚠️ Monty template body: parameters_count={n_body} but only {len(param_specs)} "
                f'named slot(s) in JSON — padding with positional keys "1".."{n_body}" / empty strings'
            )

        texts: list[str] = []
        for i in range(n_body):
            if i < len(param_specs):
                key = param_specs[i]
                val = lookup.get(key, "")
            else:
                pos = str(i + 1)
                val = lookup.get(pos, lookup.get(f"body_{pos}", ""))
            texts.append(str(val if val is not None else "").strip())

        return [{"type": "text", "text": t} for t in texts]

    def _normalize_recipient_for_monty_template(self, raw: str | None) -> str | None:
        """
        Monty send-whatsapp often requires a consistent MSISDN (digits, country code, no '+').
        Raw dashboard input may include spaces, missing country code, or '+' — normalize so
        delivery matches session sends and WhatsApp routing.
        """
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        e164 = normalize_phone(s)
        if e164:
            return e164.lstrip("+")
        digits = re.sub(r"\D", "", s)
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0") and len(digits) > 1:
            digits = digits[1:]
        if not digits.startswith("961") and len(digits) <= 10:
            digits = "961" + digits.lstrip("0")
        if len(digits) >= 10 and digits.startswith("961"):
            return digits
        return None

    def build_template_payload(
        self, template_id: str, phone_number: str, language: str = "ar", parameters: dict[str, str | None] | None = None
    ) -> dict | None:
        """
        Build the payload for sending a template message

        Args:
            template_id: Template identifier (e.g., 'reminder_24h')
            phone_number: Recipient phone number
            language: Language code (ar, en, fr)
            parameters: Dictionary of parameter values

        Returns:
            Payload dict or None if template not found
        """
        # Debug: Print what we received
        print("🔍 DEBUG build_template_payload:")
        print(f"   template_id: {template_id} (type: {type(template_id)})")
        print(f"   phone_number (raw): {phone_number} (type: {type(phone_number)})")
        print(f"   language: {language} (type: {type(language)})")
        print(f"   parameters: {parameters}")

        canonical_template_id = normalize_template_id(template_id)

        to_digits = self._normalize_recipient_for_monty_template(phone_number)
        if not to_digits:
            print(f"❌ Invalid or unsupported phone for Monty template: {phone_number!r}")
            return None
        print(f"   phone_number (Monty 'to'): {to_digits!r}")

        if not self.templates:
            print("❌ WhatsApp Cloud templates not loaded")
            return None
        template = self.get_template_info(canonical_template_id)
        if not template:
            print(f"❌ Template '{canonical_template_id}' not found")
            return None

        # Ensure language is a string, not a dict
        if isinstance(language, dict):
            print(f"⚠️ WARNING: language is a dict: {language}")
            print("   Converting to string...")
            # Try to extract language code if it's a dict
            if "code" in language:
                language = language["code"]
            else:
                language = "ar"  # Default fallback
            print(f"   Using language: {language}")

        language = self.resolve_whatsapp_language_for_template(
            template, language, template_id_for_log=canonical_template_id
        )
        template_lang = template["languages"][language]

        # Body variables: count must match Meta {{1}}..{{n}} exactly (Monty HTTP 500:
        # "Number of body variables is invalid" if count is wrong or body component missing).
        lookup = parameters if isinstance(parameters, dict) else {}
        param_values = self._build_body_component_parameters(template_lang, lookup)

        # WhatsApp Manager template name may differ from config key / templates[].name
        # (e.g. legacy internal ids map to JSON key sent_17_days_after_last_session_new).
        outbound_name = self._outbound_template_name(template, canonical_template_id)

        # Meta Cloud payload core (messaging_product added by send_template_message).
        # Do not attach Monty source/apiId — those fields are legacy-only.
        payload: dict[str, Any] = {
            "to": to_digits,
            "type": "template",
            "template": {
                "name": outbound_name,
                "language": {"code": language},
                "components": [],
            },
        }

        print(f"   Template Name (outbound): {outbound_name} (config name={template.get('name')!r})")
        print(
            f"   Resolution: {self._describe_template_resolution(template_id, canonical_template_id)}; "
            f"config_key={self._resolve_template_config_key(canonical_template_id)!r}; "
            f"text_only_mode={self.templates_are_text_only()}; "
            f"send_empty_header_component={bool((self.api_config or {}).get('send_empty_header_component', False))}; "
            f"omit_empty_header_component={template.get('omit_empty_header_component')!r}"
        )

        header_components = self._resolve_template_header_components(template, template_lang, lookup)
        payload["template"]["components"].extend(header_components)

        # Always add body component (Meta requires it for templates with body).
        # Use empty parameters[] when template has 0 body variables.
        payload["template"]["components"].append({"type": "body", "parameters": param_values})

        return payload

    def _log_outbound_template_payload(
        self, requested_template_id: str, canonical_id: str, payload: dict[str, Any]
    ) -> None:
        t = payload.get("template") or {}
        name = t.get("name")
        lang = (t.get("language") or {}).get("code")
        comps = t.get("components") or []
        has_header = any(str(c.get("type", "")).lower() == "header" for c in comps)
        print(
            "[Cloud template outbound] "
            f"requested_template_id={requested_template_id!r} normalized_id={canonical_id!r} "
            f"payload_template_name={name!r} language={lang!r} "
            f"has_header_component={has_header} "
            f"resolution={self._describe_template_resolution(requested_template_id, canonical_id)} "
            f"components={json.dumps(comps, ensure_ascii=False)}"
        )
