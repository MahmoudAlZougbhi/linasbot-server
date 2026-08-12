"""Legacy GPT chat-response helpers group 4."""

from __future__ import annotations

import json
from typing import Any

import config
from services.chat_response_service_constants import (
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    _normalize_body_part_ids,
    _safe_float,
    _safe_int,
)


def _reply_from_submit_booking_tool(tool_output: dict[str, Any], language: str) -> str:
    if (
        isinstance(tool_output, dict)
        and tool_output.get("success")
        and tool_output.get("booking_flow_state") == "booked"
    ):
        api = tool_output.get("api_response") or {}
        data = api.get("data") if isinstance(api, dict) else {}
        appt_raw = (data or {}).get("appointment") if isinstance(data, dict) else {}
        appt = appt_raw if isinstance(appt_raw, dict) else {}
        aid = appt.get("id") or appt.get("appointment_id")
        date = appt.get("date")
        cost = appt.get("cost")
        if language == "en":
            return f"Appointment booked successfully. Appointment ID: {aid}, date: {date}, system price: {cost}."
        return f"تم تثبيت الحجز على السيستم. رقم الموعد {aid}، التاريخ {date}، والسعر الظاهر بالنظام {cost}."
    reason = (
        tool_output.get("human_readable_reason") or tool_output.get("message") or "لم يكتمل الحجز على السيستم."
        if isinstance(tool_output, dict)
        else "لم يكتمل الحجز على السيستم."
    )
    return str(reason)


def _get_body_part_required_service_ids() -> set[int]:
    configured_ids = set(DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS)
    try:
        from storage.persistent_storage import APP_SETTINGS_FILE

        with open(APP_SETTINGS_FILE, encoding="utf-8") as settings_file:
            app_settings = json.load(settings_file)
        configured_list = app_settings.get("pricingSync", {}).get("requireBodyPartServiceIds", [])
        normalized: set[int] = set()
        for item in configured_list:
            sid = _safe_int(item)
            if sid is not None:
                normalized.add(sid)
        if normalized:
            configured_ids = normalized
    except Exception as settings_error:
        print(f"ℹ️ Pricing sync settings fallback to defaults: {settings_error}")
    return configured_ids


def _pricing_missing_details_reply(language: str, missing: str) -> str:
    messages = {
        "service": {
            "ar": "كرمال أعطيك السعر الدقيق من السيستم، أي خدمة بدك؟ (إزالة شعر، إزالة تاتو، أو تبييض DPL)",
            "en": "To give you the exact system price, which service do you want? (Hair removal, tattoo removal, or DPL whitening)",
            "fr": "Pour vous donner le prix exact du système, quel service souhaitez-vous ? (Épilation, détatouage ou blanchiment DPL)",
            "franco": "كرمال أعطيك السعر الدقيق من السيستم، أي خدمة بدك؟ (إزالة شعر، إزالة تاتو، أو تبييض DPL)",
        },
        "body_part": {
            "ar": "تمام، بس قبل السعر الدقيق لازم أعرف أي منطقة بالجسم بدك (مثال: إبط، ذراع، ظهر، وجه...).",
            "en": "Sure, before I fetch the exact price I need the body area (for example: underarm, arms, back, face...).",
            "fr": "D'accord, avant de récupérer le prix exact j'ai besoin de la zone du corps (ex: aisselles, bras, dos, visage...).",
            "franco": "تمام، بس قبل السعر الدقيق لازم أعرف أي منطقة بالجسم بدك (مثال: إبط، ذراع، ظهر، وجه...).",
        },
        "unavailable": {
            "ar": "ما قدرت أوصل لسعر السيستم هلق. إذا فيك جرّب بعد شوي أو خبرني التفاصيل (الخدمة + المنطقة) وبرجع بتأكد فوراً.",
            "en": "I couldn't fetch the live system price right now. Please try again shortly, or share service + area and I'll recheck immediately.",
            "fr": "Je n'ai pas pu récupérer le prix en direct pour le moment. Réessayez dans un instant, ou donnez service + zone et je reverifie immédiatement.",
            "franco": "ما قدرت أوصل لسعر السيستم هلق. إذا فيك جرّب بعد شوي أو خبرني التفاصيل (الخدمة + المنطقة) وبرجع بتأكد فوراً.",
        },
    }
    lang_bucket = messages.get(missing, messages["unavailable"])
    return lang_bucket.get(language, lang_bucket["en"])


def _infer_service_id_for_pricing(user_input: str, current_gender: str, booking_state: dict[str, Any]) -> int | None:
    existing = _safe_int(booking_state.get("service_id"))
    if existing is not None:
        return existing

    text = str(user_input or "").lower()
    if any(keyword in text for keyword in ("candela", "كانديلا", "kandila", "quadro", "كوادرو", " neo", "neo ")):
        return 12 if current_gender == "female" else 1
    if any(keyword in text for keyword in ["tattoo", "وشم", "تاتو", "détatouage"]):
        return 13
    if any(
        keyword in text
        for keyword in [
            "co2",
            "scar",
            "acne scar",
            "stretch mark",
            "ندوب",
            "ندبة",
            "اثار حب الشباب",
            "علامات التمدد",
        ]
    ):
        return 2
    if any(keyword in text for keyword in ["whitening", "dpl", "تبييض", "تفتيح", "blanchiment"]):
        return 4
    if any(keyword in text for keyword in ["hair", "epilation", "إزالة الشعر", "ليزر", "شعر"]):
        if current_gender == "female":
            return 12
        return 1
    return None


def _merge_pricing_args_with_booking_state(
    function_name: str,
    function_args: dict[str, Any],
    booking_state: dict[str, Any],
    current_gender: str,
    user_input: str,
) -> None:
    if function_name not in {"create_appointment"}:
        return

    inferred_service_id = None
    if getattr(config, "BOOKING_LEGACY_INFERENCE", False):
        inferred_service_id = _infer_service_id_for_pricing(user_input, current_gender, booking_state)
    # Prefer booking_state > inferred > GPT: booking_state has API-valid IDs; GPT schema may not match backend
    state_service = _safe_int(booking_state.get("service_id"))
    state_machine = _safe_int(booking_state.get("machine_id"))
    if state_service is not None:
        function_args["service_id"] = state_service
    elif inferred_service_id is not None:
        function_args["service_id"] = inferred_service_id

    if state_machine is not None:
        function_args["machine_id"] = state_machine
    elif booking_state.get("machine_id") is not None:
        function_args["machine_id"] = booking_state.get("machine_id")

    if function_args.get("branch_id") is None and booking_state.get("branch_id") is not None:
        function_args["branch_id"] = booking_state.get("branch_id")

    incoming_body_part_ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
    if incoming_body_part_ids:
        function_args["body_part_ids"] = incoming_body_part_ids
    else:
        st_bp = booking_state.get("body_part_ids")
        st_sid = _safe_int(booking_state.get("service_id"))
        arg_sid = _safe_int(function_args.get("service_id"))
        if st_bp and _normalize_body_part_ids(st_bp):
            # Only reuse saved areas when they belong to the same service as this booking (avoid wrong IDs).
            if st_sid is None or arg_sid is None or st_sid == arg_sid:
                function_args["body_part_ids"] = booking_state.get("body_part_ids")


def _finalize_create_appointment_payload_for_api(function_args: dict[str, Any]) -> None:
    """
    Align tool args before legacy create: CRM POST uses top-level body_part_ids (PDF).
    Keeps body_part_ids and body_parts_with_sessions consistent; preserves session_number
    when the model supplied it (≠1 → legacy_create passes body_parts through to the API).
    """
    raw_bps = function_args.get("body_parts_with_sessions")
    ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
    if isinstance(raw_bps, list) and raw_bps:
        cleaned: list[dict[str, Any]] = []
        for x in raw_bps:
            if not isinstance(x, dict):
                continue
            bid = _safe_int(x.get("body_part_id") or x.get("id"))
            if bid is None or bid <= 0:
                continue
            sn = _safe_int(x.get("session_number"))
            sess_num = int(sn) if sn is not None and sn >= 1 else 1
            cleaned.append({"body_part_id": bid, "session_number": sess_num})
        if cleaned:
            function_args["body_parts_with_sessions"] = cleaned
            function_args["body_part_ids"] = [c["body_part_id"] for c in cleaned]
            return
    if ids:
        function_args["body_parts_with_sessions"] = [{"body_part_id": bid, "session_number": 1} for bid in ids]
        function_args["body_part_ids"] = list(ids)


def _remember_booking_selection(user_id: str, function_args: dict[str, Any]) -> None:
    state = config.user_booking_state[user_id]

    service_id = _safe_int(function_args.get("service_id"))
    machine_id = _safe_int(function_args.get("machine_id"))
    branch_id = _safe_int(function_args.get("branch_id"))
    body_part_ids = _normalize_body_part_ids(function_args.get("body_part_ids"))

    if service_id is not None:
        state["service_id"] = service_id
    if machine_id is not None:
        state["machine_id"] = machine_id
    if branch_id is not None:
        state["branch_id"] = branch_id
    if body_part_ids:
        state["body_part_ids"] = body_part_ids
    ds = str(function_args.get("date") or "").strip()
    if ds:
        if " " in ds or "T" in ds.lower():
            parts = ds.replace("T", " ").split()
            state["appointment_date"] = parts[0][:10]
            if len(parts) > 1:
                state["appointment_time"] = parts[1][:8]
        elif len(ds) >= 10:
            state["appointment_date"] = ds[:10]
    if function_args.get("time"):
        state["appointment_time"] = str(function_args["time"]).strip()[:16]
    try:
        from services.booking import booking_fsm as _bfsm

        if _bfsm.fsm_enabled():
            _bfsm.sync_from_flat_booking_state(user_id)
    except Exception:
        pass


def _extract_first_numeric(item: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        if key in item:
            parsed = _safe_float(item.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_label(item: dict[str, Any]) -> str:
    machine_value = item.get("machine")
    machine_name = machine_value.get("name") if isinstance(machine_value, dict) else machine_value
    candidates = [
        item.get("body_part_name"),
        item.get("body_part"),
        item.get("area_name"),
        item.get("area"),
        machine_name,
        item.get("machine_name"),
        item.get("title"),
        item.get("name"),
        item.get("service_name"),
    ]
    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return "Price"


def _extract_pricing_rows(pricing_payload: Any) -> list[dict[str, Any]]:
    if pricing_payload is None:
        return []

    candidates: list[dict[str, Any]] = []
    visited_nodes = set()

    def walk(node: Any) -> None:
        node_id = id(node)
        if node_id in visited_nodes:
            return
        visited_nodes.add(node_id)

        if isinstance(node, dict):
            candidates.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    walk(value)

    walk(pricing_payload)

    rows: list[dict[str, Any]] = []
    seen_signatures = set()

    for item in candidates:
        base_price = _extract_first_numeric(
            item,
            ["original_price", "base_price", "price_before_discount", "list_price", "price"],
        )
        final_price = _extract_first_numeric(
            item,
            ["final_price", "discounted_price", "price_after_discount", "net_price", "total_price"],
        )
        discount_amount = _extract_first_numeric(
            item,
            ["discount_amount", "discount_value", "offer_amount", "saved_amount", "total_discount"],
        )
        discount_percent = _extract_first_numeric(
            item,
            ["discount_percent", "discount_percentage", "offer_percent", "discount_rate"],
        )

        if final_price is None and base_price is not None:
            if discount_amount is not None:
                final_price = base_price - discount_amount
            elif discount_percent is not None:
                final_price = base_price * (1 - (discount_percent / 100.0))

        if base_price is None and final_price is not None:
            base_price = final_price
        if final_price is None and base_price is not None:
            final_price = base_price

        if base_price is None and final_price is None:
            continue

        if discount_amount is None and base_price is not None and final_price is not None:
            delta = base_price - final_price
            if delta > 0.009:
                discount_amount = delta

        if discount_percent is None and discount_amount is not None and base_price is not None and base_price > 0:
            discount_percent = (discount_amount / base_price) * 100.0

        label = _extract_label(item)
        signature = (
            label,
            round(base_price or 0.0, 4),
            round(final_price or 0.0, 4),
            round(discount_amount or 0.0, 4),
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        rows.append(
            {
                "label": label,
                "base_price": base_price,
                "final_price": final_price,
                "discount_amount": discount_amount,
                "discount_percent": discount_percent,
            }
        )

    return rows


def _format_amount(value: float | None) -> str:
    if value is None:
        return "0"
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 0.01:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _build_exact_pricing_reply(language: str, pricing_payload: Any) -> str:
    rows = _extract_pricing_rows(pricing_payload)
    title = {
        "ar": "💰 هيدي الأسعار الدقيقة من السيستم:",
        "en": "💰 Here is the exact system pricing:",
        "fr": "💰 Voici les prix exacts du système :",
        "franco": "💰 هيدي الأسعار الدقيقة من السيستم:",
    }.get(language, "💰 Here is the exact system pricing:")

    if not rows:
        raw_payload = json.dumps(pricing_payload, ensure_ascii=False, default=str)
        if len(raw_payload) > 900:
            raw_payload = raw_payload[:900] + "..."
        return f"{title}\n{raw_payload}"

    lines = [title]
    for row in rows:
        label = row["label"]
        final_amount = _format_amount(row["final_price"])
        base_amount = _format_amount(row["base_price"])
        discount_amount = row["discount_amount"] or 0.0
        discount_percent = row["discount_percent"] or 0.0

        if discount_amount > 0.009:
            if language in {"ar", "franco"}:
                lines.append(
                    f"- {label}: {final_amount}$ (بدل {base_amount}$، خصم {_format_amount(discount_percent)}% = {_format_amount(discount_amount)}$)"
                )
            elif language == "fr":
                lines.append(
                    f"- {label} : {final_amount}$ (au lieu de {base_amount}$, remise {_format_amount(discount_percent)}% = {_format_amount(discount_amount)}$)"
                )
            else:
                lines.append(
                    f"- {label}: {final_amount}$ (was {base_amount}$, discount {_format_amount(discount_percent)}% = {_format_amount(discount_amount)}$)"
                )
        else:
            lines.append(f"- {label}: {final_amount}$")

    return "\n".join(lines)
