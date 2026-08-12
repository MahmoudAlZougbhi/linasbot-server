"""WhatsApp / wa.me handoff guidance instead of unauthorized operator-queue coerce."""

from __future__ import annotations

from typing import Any


def build_wa_me_handoff_guidance(
    *,
    user_data: dict[str, Any] | None,
    language: str | None = None,
) -> str:
    """Return WhatsApp/wa.me contact guidance for unauthorized handover paths.

    Never invents a phone number. Uses published CM handoff when available;
    otherwise a safe generic retry/contact message (no operator queue).
    """
    from services.cm.constants import DEFAULT_TENANT_ID
    from services.cm.runtime_pipeline import _handoff_reply
    from services.cm.schemas import HandoffPolicy
    from services.cm.structured_resolver import resolve_handoff
    from services.dynamic_messages_service import get_dynamic_message

    ud = user_data if isinstance(user_data, dict) else {}
    tenant_id = str(ud.get("tenant_id") or ud.get("tenantId") or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    lang = str(language or ud.get("user_preferred_lang") or "ar").strip().lower()
    if lang not in {"ar", "en", "fr", "franco"}:
        lang = "ar"

    try:
        from services.cm.version_store import load_published_content

        _pointer, sections = load_published_content(tenant_id)
        policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
        resolution = resolve_handoff(policy)
        if resolution.destination_value:
            dtype = (resolution.destination_type or "whatsapp").strip().lower()
            # Product mandate: WhatsApp / wa.me handoff only (no operator queue coerce).
            if dtype in {"whatsapp", "phone"}:
                return _handoff_reply("whatsapp", resolution.destination_value, lang)
            return _handoff_reply(dtype, resolution.destination_value, lang)
    except Exception as exc:
        print(f"[wa_me_handoff] published handoff resolve failed: {exc}")

    return (
        get_dynamic_message("generic_error_message", lang)
        or "عذراً، واجهت مشكلة تقنية لحظية. جرّب إعادة صياغة سؤالك أو تواصل معنا على واتساب."
    )
