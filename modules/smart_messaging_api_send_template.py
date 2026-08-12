"""Smart messaging send-test-template route (LOC split)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from modules.core import app
from modules.smart_messaging_api_templates import _monty_whatsapp_language_code
from services.smart_messaging_catalog import normalize_template_id


@app.post("/api/smart-messaging/send-test-template")
async def send_test_template_message(request_data: dict[str, Any]) -> Any:
    """Send a test message using MontyMobile template"""
    try:
        from services.montymobile_template_service import montymobile_template_service
        from services.user_persistence_service import user_persistence

        template_id = normalize_template_id(request_data.get("template_id", "").strip())
        phone_number = request_data.get("phone_number", "").strip()
        explicit = request_data.get("language")
        if isinstance(explicit, str):
            explicit = explicit.strip().lower()
        else:
            explicit = None
        if explicit in (None, "", "auto"):
            explicit = None

        # Validate inputs
        if not template_id:
            return {"success": False, "error": "Template ID is required"}

        if not phone_number:
            return {"success": False, "error": "Phone number is required"}

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
            return {"success": False, "error": f"Template '{template_id}' not found"}

        # Body variable names + count (must match montymobile_template_service / Meta {{1}}..{{n}})
        effective_lang = montymobile_template_service.resolve_whatsapp_language_for_template(
            template_info, language, template_id_for_log=template_id
        )
        langs = template_info.get("languages") or {}
        template_lang = langs.get(effective_lang) or {}
        raw_specs = template_lang.get("body_parameters")
        if not isinstance(raw_specs, list) or not raw_specs:
            raw_specs = template_lang.get("parameters") or []
        template_param_names = [x for x in raw_specs if isinstance(x, str)]

        raw_count = template_lang.get("parameters_count")
        try:
            n_body = max(0, int(raw_count)) if raw_count is not None else len(template_param_names)
        except (TypeError, ValueError):
            n_body = len(template_param_names)

        from services.smart_messaging_test_context import (
            resolve_real_test_template_placeholders,
            validate_test_placeholders_for_template,
        )

        vals, ph_meta = await resolve_real_test_template_placeholders(phone_number)
        _test_correlation_id = uuid.uuid4().hex[:10]

        test_parameters = {param: str(vals.get(param) or "").strip() for param in template_param_names}
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

        # Same defaults as scheduled sends when CRM omits branch/service (test UI must not block).
        _test_slot_defaults = {
            "branch_name": "الفرع الرئيسي",
            "service_name": "جلسة ليزر",
        }
        for _slot, _default in _test_slot_defaults.items():
            if _slot in template_param_names and not str(test_parameters.get(_slot) or "").strip():
                test_parameters[_slot] = _default
                ph_meta.setdefault("warnings", [])
                _w = f"{_slot} was empty after CRM merge — filled with default for test send."
                if _w not in ph_meta["warnings"]:
                    ph_meta["warnings"].append(_w)

        _ph_err = validate_test_placeholders_for_template(template_param_names, n_body, test_parameters, ph_meta)
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

        print(f"📋 Template '{template_id}' body slots: count={n_body} named={template_param_names!r}")
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
            language=effective_lang,
            parameters=cast(dict[str, str | None], test_parameters),
        )

        if isinstance(result, dict):
            result = {
                **result,
                "user_language": user_language,
                "requested_template_language": language,
                "template_language": effective_lang,
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
            if template_id == "thank_you_message_sent_after_session":
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
                    print(f"⚠️ Test template: thank_you_message_sent_after_session awaiting flag: {_psf_mark_e}")
            mid = result.get("message_id")
            if mid and str(mid).strip() and str(mid).strip().lower() != "unknown":
                try:
                    from services.message_preview_service import message_preview_service
                    from services.smart_messaging import smart_messaging
                    from utils.utils import save_conversation_message_to_firestore

                    # Live Chat should show the same body the customer sees (placeholders filled),
                    # matching scheduled sends that persist `content` / rendered template text.
                    _ph_display = {
                        k: v
                        for k, v in test_parameters.items()
                        if isinstance(k, str) and not str(k).isdigit() and k != "header_image"
                    }
                    _display_text = smart_messaging.get_message_content(template_id, effective_lang, _ph_display)
                    if not _display_text:
                        _display_text = message_preview_service.render_message_preview(
                            template_id, effective_lang, _ph_display
                        )
                    if not _display_text or not str(_display_text).strip() or str(_display_text).startswith("["):
                        _display_text = (
                            f"Template «{template_id}» (test send, lang {effective_lang}). "
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
                            "template_language": effective_lang,
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
        return {"success": False, "error": str(e)}

