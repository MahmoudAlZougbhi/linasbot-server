# services/chat_response_service.py
import asyncio
import json
import random
import config
from utils.utils import detect_language, get_system_instruction, get_openai_tools_schema
from prompt_templates import CUSTOMER_STATUS_TOKEN
from services.llm_core_service import client
from services.gender_recognition_service import get_gender_from_gpt
from services.moderation_service import check_rate_limits, get_rate_limit_response
from difflib import SequenceMatcher
import datetime
import re
from typing import Any, Dict, List, Optional

# Import all API functions from api_integrations
from services import api_integrations
from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
    detect_day_reference,
    detect_reschedule_intent,
    now_in_bot_tz,
    parse_datetime_flexible,
    resolve_relative_datetime,
    text_mentions_datetime,
)

# Import dynamic model selector for cost optimization
from services.dynamic_model_selector import select_optimal_model

# Fixed bot timezone (UTC+0200) for all booking day comparisons
BOOKING_TZ = BOT_FIXED_TZ

# Model pricing per 1M tokens (input, output) - update from OpenAI pricing page
MODEL_PRICING = {
    "gpt-5.1": {"input": 1.25, "output": 10.0},
    "gpt-5.4": {"input": 1.25, "output": 10.0},
    "gpt-5.4-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
}


def _compute_cost_from_usage(model: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Compute input_cost_usd, output_cost_usd, cost_usd from token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-5.1", {"input": 1.25, "output": 10.0}))
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    input_cost = (pt / 1_000_000) * pricing["input"]
    output_cost = (ct / 1_000_000) * pricing["output"]
    return {"input_cost_usd": round(input_cost, 6), "output_cost_usd": round(output_cost, 6), "cost_usd": round(input_cost + output_cost, 6)}


def _normalize_arabic_reply(text: str) -> str:
    """Replace Latin brand/assistant names with Arabic when reply is in Arabic (no mixing)."""
    if not text or not isinstance(text, str):
        return text
    replacements = [
        ("Marwa AI Assistant", "مروى"),
        ("Marwa", "مروى"),
        ("Lina's Laser Center", "مركز ليناز ليزر"),
        ("Lina's Laser", "ليناز ليزر"),
    ]
    for latin, arabic in replacements:
        text = text.replace(latin, arabic)
    # Catch Lina's (curly apostrophe) and standalone Laser
    text = re.sub(r"Lina['']s\s*Laser\s*Center?", "مركز ليناز ليزر", text, flags=re.IGNORECASE)
    text = re.sub(r"Lina['']s\s*Laser", "ليناز ليزر", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLaser\b", "ليزر", text, flags=re.IGNORECASE)
    return text


_custom_qa_cache = {}

PRICE_STRONG_KEYWORDS = [
    "price",
    "cost",
    "how much",
    "pricing",
    "سعر",
    "اسعار",
    "تكلفة",
    "prix",
    "coût",
    "combien",
    "tarif",
    "sa3er",
]

# Weak "how much" words are ambiguous in Franco-Arabic (e.g., "kam dawle...")
# so they should only count as price intent when clinic context is present.
PRICE_WEAK_KEYWORDS = [
    "كم",
    "قديش",
    "أديش",
    "adesh",
    "adde",
    "2adde",
    "2adesh",
    "kam",
]

CLINIC_PRICE_CONTEXT_KEYWORDS = [
    "laser",
    "ليزر",
    "جلسة",
    "جلسات",
    "service",
    "services",
    "خدمة",
    "خدمات",
    "appointment",
    "appointments",
    "موعد",
    "مواعيد",
    "booking",
    "حجز",
    "tattoo",
    "تاتو",
    "وشم",
    "dpl",
    "co2",
    "scar",
    "ندبة",
    "stretch",
    "hair",
    "شعر",
    "ليناز",
    "linas",
    "clinic",
    "عيادة",
]

OFF_TOPIC_PRICE_FALSE_POSITIVE_HINTS = [
    "president",
    "prime minister",
    "government",
    "politics",
    "country",
    "countries",
    "capital",
    "news",
    "weather",
    "bitcoin",
    "crypto",
    "دولة",
    "دول",
    "عالم",
    "رئيس",
    "سياسة",
    "طقس",
    "dawle",
    "dawlat",
    "3alam",
    "ra2is",
    "siyase",
    "siyaseh",
    "wazir",
    "ekhtara3",
    "e5tr3",
    "invented",
]

DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS = {1, 12, 13}

def validate_language_match(user_language: str, bot_response: str, detected_response_lang: str) -> tuple:
    """
    Validate bot response matches user language
    Returns: (is_valid: bool, error_message: str)
    """
    # Character patterns for each language
    patterns = {
        'ar': r'[\u0600-\u06FF]',  # Arabic
        'en': r'[a-zA-Z]',
        'fr': r'[a-zA-Z]'
    }

    # Franco should get Arabic response
    if user_language == 'franco':
        user_language = 'ar'

    # For Arabic responses, enforce Arabic script only (names included).
    # Allow URLs/emails to pass untouched when needed.
    if user_language == "ar":
        sanitized = re.sub(
            r"https?://\S+|www\.\S+|\b\S+@\S+\b",
            "",
            bot_response or "",
            flags=re.IGNORECASE,
        )
        if re.search(r"[A-Za-z]", sanitized):
            return False, "Language mismatch: Arabic response contains Latin letters."

    if user_language not in patterns:
        return True, ""  # Skip validation for unknown languages

    # Count characters matching expected language
    expected_chars = len(re.findall(patterns[user_language], bot_response))
    total_chars = len(re.sub(r'\s', '', bot_response))  # Exclude spaces

    if total_chars == 0:
        return True, ""

    match_ratio = expected_chars / total_chars

    if match_ratio < 0.7:  # 70% threshold
        return False, f"Language mismatch: {match_ratio:.1%} match (expected ≥70% {user_language})"

    return True, ""


def _contains_arabic_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(text or "")))


def looks_like_working_hours_reply(text: str) -> bool:
    """Heuristic: detect replies that are clearly about clinic hours/opening times."""
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    hours_patterns = [
        r"\bworking\s+hours\b",
        r"\bopening\s+hours\b",
        r"\bopen\s+from\b",
        r"\bclinic\s+hours\b",
        r"(?:ساعات\s*(?:العمل|الدوام)|اوقات\s*العمل|دوامنا|الدوام)",
        r"\bhoraires\b",
        r"\bouvert\b",
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE | re.UNICODE) for pattern in hours_patterns)


def is_price_related_question(text: str, booking_state: Optional[Dict[str, Any]] = None) -> bool:
    normalized = str(text or "").lower()
    if not normalized.strip():
        return False

    has_strong_price_signal = any(keyword in normalized for keyword in PRICE_STRONG_KEYWORDS)
    has_weak_price_signal = any(keyword in normalized for keyword in PRICE_WEAK_KEYWORDS)
    if not has_strong_price_signal and not has_weak_price_signal:
        return False

    has_clinic_context = any(keyword in normalized for keyword in CLINIC_PRICE_CONTEXT_KEYWORDS)
    state = booking_state or {}
    has_booking_context = any(
        [
            state.get("service_id"),
            state.get("machine_id"),
            state.get("branch_id"),
            state.get("body_part_ids"),
            state.get("last_pricing_payload"),
        ]
    )
    looks_off_topic = any(keyword in normalized for keyword in OFF_TOPIC_PRICE_FALSE_POSITIVE_HINTS)

    # Prevent false positives like "kam dawle..." from triggering pricing sync.
    if looks_off_topic and not has_clinic_context and not has_booking_context:
        return False

    if has_strong_price_signal:
        return True

    # Weak signals (kam/adde/قديش) need either clinic context or active booking context.
    return has_clinic_context or has_booking_context


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _normalize_body_part_ids(raw_value: Any) -> List[int]:
    if raw_value is None or raw_value == "":
        return []

    if isinstance(raw_value, list):
        result = []
        for item in raw_value:
            parsed = _safe_int(item)
            if parsed is not None:
                result.append(parsed)
        return result

    if isinstance(raw_value, str):
        pieces = [part.strip() for part in raw_value.split(",") if part.strip()]
        result = []
        for part in pieces:
            parsed = _safe_int(part)
            if parsed is not None:
                result.append(parsed)
        return result

    parsed_single = _safe_int(raw_value)
    return [parsed_single] if parsed_single is not None else []


def _get_body_part_required_service_ids() -> set:
    configured_ids = set(DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS)
    try:
        from storage.persistent_storage import APP_SETTINGS_FILE
        with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as settings_file:
            app_settings = json.load(settings_file)
        configured_list = app_settings.get("pricingSync", {}).get("requireBodyPartServiceIds", [])
        normalized = {_safe_int(item) for item in configured_list}
        normalized = {item for item in normalized if item is not None}
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


def _infer_service_id_for_pricing(user_input: str, current_gender: str, booking_state: Dict[str, Any]) -> Optional[int]:
    existing = _safe_int(booking_state.get("service_id"))
    if existing is not None:
        return existing

    text = str(user_input or "").lower()
    if any(keyword in text for keyword in ["tattoo", "وشم", "تاتو", "détatouage"]):
        return 13
    if any(keyword in text for keyword in ["whitening", "dpl", "تبييض", "تفتيح", "blanchiment"]):
        return 4
    if any(keyword in text for keyword in ["hair", "epilation", "إزالة الشعر", "ليزر", "شعر"]):
        if current_gender == "female":
            return 12
        return 1
    return None


def _merge_pricing_args_with_booking_state(
    function_name: str,
    function_args: Dict[str, Any],
    booking_state: Dict[str, Any],
    current_gender: str,
    user_input: str,
) -> None:
    if function_name not in {"create_appointment"}:
        return

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
    elif booking_state.get("body_part_ids"):
        function_args["body_part_ids"] = booking_state.get("body_part_ids")


def _remember_booking_selection(user_id: str, function_args: Dict[str, Any]) -> None:
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


def _extract_first_numeric(item: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for key in keys:
        if key in item:
            parsed = _safe_float(item.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_label(item: Dict[str, Any]) -> str:
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


def _extract_pricing_rows(pricing_payload: Any) -> List[Dict[str, Any]]:
    if pricing_payload is None:
        return []

    candidates: List[Dict[str, Any]] = []
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

    rows: List[Dict[str, Any]] = []
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

        if (
            discount_percent is None
            and discount_amount is not None
            and base_price is not None
            and base_price > 0
        ):
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


def _format_amount(value: Optional[float]) -> str:
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
        raw_payload = json.dumps(pricing_payload, ensure_ascii=False)
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


def _extract_json_objects(raw: str):
    """
    Extract all complete JSON objects from a string. GPT sometimes returns multiple objects:
    - First: preferred_service, preferred_branch, etc. (no action/bot_reply)
    - Second: action, bot_reply (the actual response)
    Yields (start, end) slices for each object.
    """
    s = (raw or "").strip()
    pos = 0
    while pos < len(s):
        # Find next {
        idx = s.find("{", pos)
        if idx < 0:
            break
        depth = 0
        in_string = False
        escape = False
        i = idx
        while i < len(s):
            c = s[i]
            if escape:
                escape = False
                i += 1
                continue
            if c == "\\" and in_string:
                escape = True
                i += 1
                continue
            if not in_string:
                if c == '"':
                    in_string = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        yield s[idx : i + 1]
                        pos = i + 1
                        break
            else:
                if c == '"':
                    in_string = False
            i += 1
        else:
            break


def _parse_gpt_response_json(raw: str) -> dict:
    """
    Parse GPT response that may contain multiple JSON objects. Returns the first object
    that has both action and bot_reply. GPT sometimes returns two objects:
    - First: preferred_service, preferred_branch, etc. (no action/bot_reply)
    - Second: action, bot_reply (the actual response)
    """
    for obj_str in _extract_json_objects(raw):
        try:
            parsed = json.loads(obj_str)
            if isinstance(parsed, dict) and parsed.get("action") and parsed.get("bot_reply"):
                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    raise json.JSONDecodeError("No valid JSON object with action and bot_reply found", raw, 0)


def _extract_preferred_booking_from_gpt(raw: str) -> dict:
    """
    Extract preferred_* fields from GPT response (first JSON object). Used by booking fallback
    to populate machine_id and body_part_ids when GPT returns confirmation but didn't call the tool.
    """
    out = {}
    for obj_str in _extract_json_objects(raw):
        try:
            parsed = json.loads(obj_str)
            if not isinstance(parsed, dict):
                continue
            if parsed.get("preferred_machine_id") is not None:
                out["preferred_machine_id"] = _safe_int(parsed.get("preferred_machine_id"))
            if parsed.get("preferred_area"):
                out["preferred_area"] = str(parsed.get("preferred_area", "")).strip()
            if parsed.get("preferred_service"):
                out["preferred_service"] = str(parsed.get("preferred_service", "")).strip()
            if parsed.get("preferred_branch"):
                out["preferred_branch"] = str(parsed.get("preferred_branch", "")).strip()
            if out:
                return out
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def _area_name_to_body_part_ids(area_name: str, service_id: int) -> Optional[List[int]]:
    """
    Map area name (e.g. full body, full kel shi) to body_part_ids. Uses app_settings mapping
    first, then common full-body detection. Returns None if no mapping found.
    """
    if not area_name or not str(area_name).strip():
        return None
    area_lower = str(area_name).strip().lower()
    mapping = _get_area_to_body_part_mapping()
    # Check explicit mapping first
    for key in ["full_body", "full body", "full", "full_body_laser"]:
        if key in mapping:
            ids = mapping[key]
            if isinstance(ids, list) and ids:
                return [int(x) for x in ids if _safe_int(x) is not None]
    # Full body variants - use mapping if available
    full_body_keys = ["full body", "full kel shi", "full kel chi", "جسم كامل", "كامل", "full", "full body laser"]
    if any(k in area_lower or area_lower == k for k in full_body_keys):
        return mapping.get("full_body") or mapping.get("full")
    return mapping.get(area_lower)


def _get_area_to_body_part_mapping() -> dict:
    """Load area->body_part_ids mapping from app_settings or use defaults."""
    try:
        from storage.persistent_storage import APP_SETTINGS_FILE
        with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        m = settings.get("booking", {}).get("areaToBodyPartIds", {})
        if m:
            return m
    except Exception:
        pass
    return {}


async def _fetch_customer_file_summary_for_ai(customer_phone_clean: str) -> Optional[str]:
    """
    Fetch full customer file summary for AI context: services, sessions (done + available only),
    body parts per service, payment, dates, machines. Excludes postponed sessions.
    Returns formatted summary string or None if customer not found / API error.
    """
    if not customer_phone_clean or not str(customer_phone_clean).strip():
        return None
    try:
        cust_resp = await api_integrations.get_customer_by_phone(phone=customer_phone_clean)
        if not cust_resp.get("success") or not cust_resp.get("data"):
            return None
        data = cust_resp["data"]
        customer_id = data.get("id")
        if customer_id is None:
            return None

        # Fetch sessions and payment in parallel (faster)
        sessions_resp, payment_resp = await asyncio.gather(
            api_integrations.get_customer_sessions(customer_id=customer_id),
            api_integrations.check_appointment_payment(phone=customer_phone_clean),
        )

        lines = ["**📁 CUSTOMER FILE SUMMARY (use this when answering about their treatments):**"]

        # Sessions: only done + available (exclude postponed, paused)
        INCLUDE_STATUSES = {"done", "available"}
        sessions_raw = []
        if sessions_resp.get("success") and sessions_resp.get("data"):
            sess_data = sessions_resp["data"]
            if isinstance(sess_data, list):
                sessions_raw = sess_data
            elif isinstance(sess_data, dict) and "sessions" in sess_data:
                sessions_raw = sess_data.get("sessions", [])
            elif isinstance(sess_data, dict) and "data" in sess_data:
                sessions_raw = sess_data.get("data", [])

        sessions_included = []
        for s in sessions_raw:
            status = (s.get("status") or "").strip().lower()
            if status in INCLUDE_STATUSES:
                sessions_included.append(s)

        if sessions_included:
            # Group by service
            by_service: Dict[str, List[dict]] = {}
            for s in sessions_included:
                svc = (s.get("service") or s.get("service_name") or "Unknown").strip()
                if svc not in by_service:
                    by_service[svc] = []
                by_service[svc].append(s)

            for svc_name, svc_sessions in by_service.items():
                lines.append(f"\n- **Service**: {svc_name} ({len(svc_sessions)} sessions)")
                body_parts = set()
                for s in svc_sessions:
                    bp = s.get("body_part") or s.get("body_area") or s.get("area")
                    if bp:
                        body_parts.add(str(bp).strip())
                if body_parts:
                    lines.append(f"  - Body parts: {', '.join(sorted(body_parts))}")
                for s in svc_sessions:
                    date_str = s.get("date") or s.get("appointment_date") or ""
                    machine = s.get("machine") or s.get("machine_name") or ""
                    sess_num = s.get("session_number")
                    status = s.get("status", "")
                    parts = [f"  - {status}"]
                    if date_str:
                        parts.append(f"date: {date_str}")
                    if machine:
                        parts.append(f"machine: {machine}")
                    if sess_num is not None:
                        parts.append(f"session #{sess_num}")
                    lines.append(" ".join(parts))
        else:
            lines.append("\n- No sessions (done or available) found.")

        # Payment
        if payment_resp.get("success") and payment_resp.get("data"):
            pay = payment_resp["data"]
            amount = pay.get("amount") or pay.get("paid") or pay.get("total_paid")
            if amount is not None:
                lines.append(f"\n- **Payment**: {amount}")
            status_pay = pay.get("status") or pay.get("payment_status")
            if status_pay:
                lines.append(f"- **Payment status**: {status_pay}")

        return "\n".join(lines) if len(lines) > 1 else None
    except Exception as e:
        print(f"⚠️ _fetch_customer_file_summary_for_ai failed for {customer_phone_clean}: {e}")
        return None


# user_id is the WhatsApp phone number
async def get_bot_chat_response(user_id: str, user_input: str, current_context_messages: list, current_gender: str, current_preferred_lang: str, response_language: str, is_initial_message_after_start: bool, initial_user_query_to_process: str = None, custom_knowledge_context: str = None, operational_context: str = None, last_ai_response_at: Optional[datetime.datetime] = None, user_image_base64: str = None, user_image_format: str = "jpeg") -> dict:
    user_name = config.user_names.get(user_id, "client")
    current_gender_attempts = config.gender_attempts.get(user_id, 0)

    # Extract customer phone number (without country code for API calls)
    customer_phone_full = config.user_data_whatsapp.get(user_id, {}).get('phone_number')

    # CRITICAL: Sync CRM lookup when we have phone but no known name (fixes race: defer_external
    # runs in background, so AI was called before CRM name arrived - bot asked for name when customer has file)
    _placeholder_names = {"client", "unknown", "unknown customer", "test user"}
    _name_lower = (user_name or "").strip().lower()
    _name_unknown = (
        not user_name or user_name == "client"
        or _name_lower in _placeholder_names
        or _name_lower.startswith("test user")
    )
    if customer_phone_full and _name_unknown:
        from utils.phone_utils import normalize_phone
        normalized_for_crm = normalize_phone(customer_phone_full) or (
            str(customer_phone_full).strip() if str(customer_phone_full).strip().startswith("+") else ""
        )
        if normalized_for_crm:
            try:
                from services.customer_identity_service import resolve_customer_from_external
                ext = await resolve_customer_from_external(normalized_for_crm)
                if ext.get("exists") and ext.get("name"):
                    config.user_names[user_id] = ext["name"]
                    user_name = ext["name"]
                    if user_id in config.user_data_whatsapp:
                        config.user_data_whatsapp[user_id]["crm_customer_exists"] = True
                        config.user_data_whatsapp[user_id]["customer_file_status"] = "existing_file"
                    # Also set gender from customer file so we don't ask when it's already in CRM
                    if ext.get("gender") in ("male", "female"):
                        config.user_gender[user_id] = ext["gender"]
                        config.gender_attempts[user_id] = 0
                        print(f"✅ CRM sync: loaded name '{user_name}' and gender '{ext['gender']}' for {user_id} before AI call")
                    else:
                        print(f"✅ CRM sync: loaded name '{user_name}' for {user_id} before AI call")
                elif ext.get("exists"):
                    if user_id in config.user_data_whatsapp:
                        config.user_data_whatsapp[user_id]["crm_customer_exists"] = True
                        config.user_data_whatsapp[user_id]["customer_file_status"] = "existing_file"
                    # Customer has file but no name - still try to use gender if present
                    if ext.get("gender") in ("male", "female"):
                        config.user_gender[user_id] = ext["gender"]
                        config.gender_attempts[user_id] = 0
                        print(f"✅ CRM sync: customer has file, loaded gender '{ext['gender']}' for {user_id}")
                    else:
                        print(f"✅ CRM sync: customer has file but no name in CRM for {user_id}")
            except Exception as e:
                print(f"⚠️ CRM sync lookup failed for {user_id}: {e}")
        # Use gender from config if we just loaded it from CRM (for current request)
        if config.user_gender.get(user_id) in ("male", "female"):
            current_gender = config.user_gender[user_id]
    customer_phone_clean = None
    if customer_phone_full:
        customer_phone_clean = str(customer_phone_full).replace("+", "").replace(" ", "").replace("-", "")
        if customer_phone_clean.startswith("961"):
            customer_phone_clean = customer_phone_clean[3:]  # Remove Lebanon country code
    
    # Check rate limits first
    within_limits, limit_message = await check_rate_limits(user_id, 'message')
    if not within_limits:
        return {
            "action": "rate_limit_exceeded",
            "bot_reply": get_rate_limit_response(current_preferred_lang, limit_message),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender
        }
    
    explicitly_detected_gender_from_input = None
    if user_input.strip():
        explicitly_detected_gender_from_input = await get_gender_from_gpt(user_input)
        print(f"DEBUG GPT Gender Recognition: Input '{user_input}' -> Detected as '{explicitly_detected_gender_from_input}' (for logging/debug, GPT will decide action)")

    is_reschedule_intent = detect_reschedule_intent(user_input)
    if is_reschedule_intent:
        print("🔁 Intent routing lock: reschedule/postpone intent detected.")

    # NOTE: conversation_log.jsonl is NO LONGER USED
    # Q&A matching is now handled by qa_database_service.py (API-based)
    # This happens in text_handlers.py BEFORE calling this function
    # If we reach here, it means no Q&A match was found, so proceed with GPT-4

    # Trained Q&A partial-match injection into the system prompt is intentionally disabled.
    # Exact Q&A matching still happens earlier in text_handlers.py before this GPT path.
    qa_reference_text = ""

    # Detect if this is a price-related question and load sync rules.
    # Use booking state too, so weak words like "kam" do not misfire out of context.
    booking_state_snapshot = config.user_booking_state.get(user_id, {})
    is_price_question = is_price_related_question(user_input, booking_state_snapshot)
    body_part_required_service_ids = _get_body_part_required_service_ids()

    # Get the core system instruction from utils.py, with conditional price list loading.
    # When custom_knowledge_context is provided (from dynamic retrieval), ADDITIVE to KB/Style.
    system_instruction_core = get_system_instruction(
        user_id,
        current_preferred_lang,
        qa_reference_text,
        include_price_list=is_price_question,
        custom_knowledge_context=custom_knowledge_context,
        operational_context=operational_context,
    )

    # Log which training files GPT is receiving
    print(f"📄 GPT will receive knowledge_base.txt in context")
    print(f"📄 GPT will receive style_guide.txt in context")

    if is_price_question:
        print(f"📄 GPT will receive price_list.txt in context (price-related question detected)")
    else:
        print("📄 GPT will skip price_list.txt in context (not a price-related question)")

    # Build dynamic customer context - just the VALUES, rules are in style_guide.txt
    # Treat placeholder names (Test User, Unknown, etc.) as NOT known - avoid "تست يوزر" in Arabic
    # Re-read user_name after CRM sync (may have been updated above)
    user_name = config.user_names.get(user_id, "client")
    customer_first_name = (user_name.split()[0] if user_name and user_name != "client" else user_name) if user_name else None
    _placeholder_names = {"client", "unknown", "unknown customer", "test user"}
    _name_lower = (user_name or "").strip().lower()
    name_is_known = (
        user_name
        and user_name != "client"
        and _name_lower not in _placeholder_names
        and not _name_lower.startswith("test user")
    )
    crm_customer_exists = config.user_data_whatsapp.get(user_id, {}).get("crm_customer_exists")
    current_local_time = now_in_bot_tz()
    current_date_str = current_local_time.strftime("%Y-%m-%d")
    current_time_str = current_local_time.strftime("%H:%M:%S")
    current_day_name = current_local_time.strftime("%A")

    arabic_script_policy = ""
    if response_language in ("ar", "franco"):
        arabic_script_policy = (
            "- **Arabic Script Only (NO MIXING)**: Your `bot_reply` MUST be in Arabic script only (no Latin letters at all). "
            "NEVER mix English with Arabic. BANNED in Arabic messages: 'AI Assistant', 'Marwa', 'Lina's Laser', or ANY Latin/English words. "
            "Write clinic as ليناز ليزر, assistant as مروى only. When introducing yourself: أهلاً، أنا مروى من ليناز ليزر – never 'مروى AI Assistant'.\n"
        )

    customer_name_context = (
        "NOT KNOWN - You MUST ask for their full name (see Name Capture Rules in Style Guide)"
    )
    if name_is_known:
        customer_name_context = (
            f"KNOWN - {user_name} (First name: {customer_first_name}). Do NOT ask for name again."
        )
    elif crm_customer_exists:
        customer_name_context = (
            "Customer has EXISTING FILE in CRM - do NOT ask for their name. "
            "Use respectful address (حضرتك/أستاذ/عزيزتي) without requesting name. "
            "Proceed to help with their inquiry."
        )

    arabic_addressing_policy = ""
    if response_language in ("ar", "franco"):
        if current_gender == "male":
            preferred_title = "أستاذ"
        elif current_gender == "female":
            preferred_title = "عزيزتي"
        else:
            preferred_title = "حضرتك"

        if name_is_known and not _contains_arabic_script(user_name):
            customer_name_context = (
                f"KNOWN (non-Arabic script name): {user_name}. "
                "In Arabic replies, transliterate this name to Arabic letters and include it after the respectful title."
            )

        arabic_addressing_policy = (
            "- **Arabic Addressing Rule**: Use respectful addressing in Arabic replies only:\n"
            "  - male: أستاذ\n"
            "  - female: عزيزتي\n"
            "  - unknown gender: حضرتك\n"
            "  If customer name is known, include it after the respectful title in Arabic letters.\n"
            "  Never use 'يا' followed by a transliterated name (example: يا تست).\n"
        )

    arabic_brand_policy = ""
    arabic_date_policy = ""
    if response_language in ("ar", "franco"):
        arabic_brand_policy = (
            "- **Arabic Clinic Naming Rule**: When mentioning the clinic, write exactly: ليناز ليزر (never Lina's Laser in Latin).\n"
            "- **Assistant Intro in Arabic**: Say أهلاً، أنا مروى من ليناز ليزر. NEVER write 'AI Assistant' or 'Marwa AI Assistant' – zero Latin script in Arabic messages.\n"
        )
        arabic_date_policy = (
            "- **Arabic Date/Time Rule (MANDATORY)**: When your bot_reply is in Arabic, ALL dates and times MUST be in Arabic format. "
            "Use Arabic numerals (٠١٢٣٤٥٦٧٨٩) and Arabic month names. Example: 01/04/2026 10:00 → ١ نيسان ٢٠٢٦ الساعة ١٠:٠٠ صباحاً. "
            "Months: يناير، فبراير، مارس، أبريل/نيسان، مايو، يونيو، يوليو، أغسطس، سبتمبر، أكتوبر، نوفمبر، ديسمبر (or Levantine: كانون الثاني، شباط، آذار، نيسان، أيار، حزيران، تموز، آب، أيلول، تشرين الأول، تشرين الثاني، كانون الأول). "
            "NEVER use 01/04/2026 or DD/MM/YYYY in Arabic messages – always convert to Arabic.\n"
        )

    concise_turn_policy = (
        "- **Turn-by-Turn Policy (CRITICAL)**: ONE message only. Short and focused.\n"
        "- **Response Length (MANDATORY)**: Keep bot_reply concise. Aim for ~30% shorter than a full detailed answer. "
        "Neither too long (avoid 3+ paragraphs, long numbered lists, repeated points) nor too short (keep essential info). "
        "One focused paragraph or 2–3 brief bullet points max. Cut filler and repetition.\n"
        "- Either: (a) short answer + ONE question, OR (b) ONE question to gather info.\n"
        "- For tattoo/pricing: ask first (body area? branch?) – next turn give full answer. Do NOT dump service info + availability + pricing + question all at once.\n"
        "- Do NOT send 3+ paragraphs or multiple info blocks. Compress into one focused message.\n"
    )

    # Fetch full customer file summary for AI (services, sessions done+available, body parts, payment, dates, machines)
    customer_file_summary = ""
    if customer_phone_clean:
        customer_file_summary_raw = await _fetch_customer_file_summary_for_ai(customer_phone_clean)
        if customer_file_summary_raw:
            customer_file_summary = "\n\n" + customer_file_summary_raw

    domain_scope_policy = (
        "- **Domain Scope Policy**: You only support ليناز ليزر clinic topics (services, pricing, appointments, branches, preparation).\n"
        "- If the user asks out-of-scope general knowledge/news/politics/etc., do NOT answer that question.\n"
        "- Respond with a short polite redirection to clinic-related help.\n"
    )

    # Show greeting only when: new user (no prior messages) OR inactive 12+ hours
    # Prefer Firestore last_ai_response_at (persists across restarts); fallback to in-memory
    _now = datetime.datetime.now(datetime.timezone.utc)
    _last_bot = last_ai_response_at if last_ai_response_at is not None else config.user_last_bot_response_time.get(user_id, _now)
    if _last_bot and getattr(_last_bot, 'tzinfo', None) is None:
        _last_bot = _last_bot.replace(tzinfo=datetime.timezone.utc)
    try:
        _hours_since = (_now - _last_bot).total_seconds() / 3600 if _last_bot else 0.0
    except (TypeError, AttributeError):
        _hours_since = 0.0
    _is_new = len(current_context_messages or []) == 0
    _show_greeting = _is_new or _hours_since >= 12
    if _show_greeting:
        _greeting_reason = "new user (first message)" if _is_new else "inactive 12+ hours since last contact"
    else:
        _greeting_reason = "ongoing conversation (less than 12 hours since last contact)"

    # Dynamic customer status block - provides current values for the rules defined in style_guide.txt
    dynamic_customer_context = (
        "**📋 CURRENT CUSTOMER STATUS (Use these values when applying the rules from the Style Guide):**\n"
        f"- **Show greeting**: {_show_greeting} - Reason: {_greeting_reason}. Use greeting ONLY when True (new user or inactive 12+ hours). Otherwise go straight to the answer. Do NOT repeat أهلاً أستاذ / أنا مروى in every message.\n"
        f"- **Customer Name**: {customer_name_context}\n"
        f"- **Customer Phone**: '{customer_phone_clean}' - Use this for ALL tool calls (check_next_appointment, create_appointment, update_appointment_date). Do NOT ask for phone number.\n"
        f"- **Gender**: '{current_gender}'"
        + (" - GENDER IS ALREADY KNOWN. NEVER ask for gender again!\n" if current_gender in ['male', 'female'] else " - UNKNOWN. Follow gender collection rules in Style Guide.\n")
        + f"- **Language**: YOU decide. Current hint: '{current_preferred_lang}'. Follow LANGUAGE rules: prefer Arabic when mixed; full English when all English; full French when all French.\n"
        + arabic_script_policy
        + arabic_addressing_policy
        + arabic_brand_policy
        + arabic_date_policy
        + concise_turn_policy
        + domain_scope_policy
        + f"- **current_gender_from_config**: '{current_gender}'\n"
        f"- **detected_language**: '{current_preferred_lang}'\n"
        f"- **Awaiting human handover confirmation**: {config.user_data_whatsapp.get(user_id, {}).get('awaiting_human_handover_confirmation', False)} - If True, user is replying to your transfer confirmation question. Interpret yes/no accordingly.\n"
        f"**🕐 CURRENT DATE AND TIME (UTC+0200): {current_day_name}, {current_date_str} at {current_time_str}**\n"
        f"{customer_file_summary}"
    )

    # Compact customer context for Activity Flow visibility (what Bot sends to AI about this customer)
    _file_raw = customer_file_summary.strip().lstrip("\n") if customer_file_summary else ""
    flow_customer_context_sent = (
        "=== CUSTOMER STATUS ===\n"
        f"- Name: {customer_name_context}\n"
        f"- Phone: {customer_phone_clean or '(none)'}\n"
        f"- Gender: {current_gender}\n"
        f"- Language hint: {current_preferred_lang}\n\n"
        "=== CUSTOMER FILE (services, sessions, body parts, payment, dates – done+available only) ===\n"
        + (_file_raw if _file_raw else "(No file or customer not found)")
    )

    routing_guardrail = ""
    if is_reschedule_intent:
        routing_guardrail = (
            "\n\n"
            "**🔒 INTENT ROUTING OVERRIDE:**\n"
            "- The user's latest request is to RESCHEDULE/POSTPONE an appointment.\n"
            "- This is NOT a clinic working-hours request.\n"
            "- Do NOT call `get_clinic_hours` for this message.\n"
            "- Use appointment flow only: `check_next_appointment` then `update_appointment_date` when date/time is provided.\n"
        )

    # Enforce explicit json contract whenever response_format={"type":"json_object"} is used.
    # Some OpenAI endpoints reject requests if the messages omit the word "json".
    json_output_contract = (
        "\n\nOUTPUT FORMAT (MANDATORY):\n"
        "- Reply with a valid json object only.\n"
        "- Include at least these keys: \"action\" and \"bot_reply\".\n"
        "- Do not return markdown, code fences, or extra text outside json.\n"
    )

    # Combine system instruction with dynamic context (replace token or append)
    if CUSTOMER_STATUS_TOKEN in system_instruction_core:
        system_instruction_final = (
            system_instruction_core.replace(CUSTOMER_STATUS_TOKEN, "\n\n" + dynamic_customer_context)
            + routing_guardrail
            + json_output_contract
        )
    else:
        system_instruction_final = (
            system_instruction_core
            + "\n\n"
            + dynamic_customer_context
            + routing_guardrail
            + json_output_contract
        )

    context_messages_for_ai = list(current_context_messages or [])
    context_cap = int(getattr(config, "MAX_CONTEXT_MESSAGES_IN_WINDOW", 0) or 0)
    if context_cap > 0 and len(context_messages_for_ai) > context_cap:
        context_messages_for_ai = context_messages_for_ai[-context_cap:]

    messages = [{"role": "system", "content": system_instruction_final}]
    messages.extend(context_messages_for_ai)

    # Build user message: text only, or multimodal (text + image) when image provided
    if user_image_base64:
        image_url = f"data:image/{user_image_format};base64,{user_image_base64}"
        user_content = [
            {"type": "text", "text": user_input or "المستخدم أرسل صورة."},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_input})

    # Prepare flow metadata context early so Activity Flow remains informative
    # even when GPT fails before normal metadata assembly.
    flow_context_count = len(context_messages_for_ai)
    flow_sys_len = len(system_instruction_final) if system_instruction_final else 0
    flow_ai_query_summary = (
        f"Bot sent to AI (GPT):\n"
        f"- System prompt: {flow_sys_len} chars (knowledge + style + customer context)\n"
        f"- Context messages: {flow_context_count}\n"
        f"- User query: {user_input[:400]}{'...' if len(user_input) > 400 else ''}"
    )
    if custom_knowledge_context:
        flow_ai_query_summary += (
            f"\n- Dynamic knowledge: {len(custom_knowledge_context)} chars, full content:\n"
            f"{custom_knowledge_context}"
        )
    flow_context_dump = []
    for msg in context_messages_for_ai:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))
        flow_context_dump.append(f"[{role}] {content}")
    flow_bot_sent_to_ai_full = (
        "Bot sent to AI (GPT) - FULL INPUT\n\n"
        "=== SYSTEM PROMPT ===\n"
        f"{system_instruction_final}\n\n"
        "=== CONTEXT MESSAGES ===\n"
        + ("\n".join(flow_context_dump) if flow_context_dump else "(none)")
        + "\n\n=== USER MESSAGE ===\n"
        + str(user_input)
    )
    
    gpt_raw_content = "" # Initialize gpt_raw_content here to make it accessible in except blocks

    # Main GPT model is fixed per latest routing policy.
    selected_model = "gpt-5.1"
    model_metadata = {
        "complexity": "FIXED",
        "reason": "Main flow using gpt-5.1",
    }
    print(f"🤖 Model selected: {selected_model} | Reason: {model_metadata['reason']}")

    try:
        response = await client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=0.7,
            tools=get_openai_tools_schema(),
            tool_choice="auto",
            response_format={"type": "json_object"}
        )
        
        if not response.choices:
            raise ValueError("GPT returned no choices")
        first_response_message = response.choices[0].message
        
        gpt_raw_content = first_response_message.content.strip() if first_response_message.content else ""
        print(f"GPT Raw Response (first pass): {gpt_raw_content}") 

        tool_calls = first_response_message.tool_calls

        parsed_response = {}
        latest_pricing_payload = None
        api_failure_reason = None  # Set when create_appointment or other API fails → triggers human handover

        # When GPT asks for gender (unknown), send that reply and do NOT run tool calls.
        # Otherwise a second response after tools can replace it with booking flow (date/time/branch).
        if tool_calls and current_gender == "unknown" and gpt_raw_content:
            try:
                first_parsed = _parse_gpt_response_json(gpt_raw_content)
                first_action = (first_parsed.get("action") or "").strip().lower()
                if first_action in ["ask_gender", "initial_greet_and_ask_gender"]:
                    first_parsed.setdefault("detected_language", current_preferred_lang)
                    first_parsed["current_gender_from_config"] = current_gender
                    first_parsed.setdefault("detected_gender", None)
                    first_parsed.setdefault("detected_name", None)
                    first_parsed["_flow_meta"] = {
                        "model": selected_model,
                        "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
                        "ai_query_summary": flow_ai_query_summary,
                        "bot_sent_to_ai": flow_bot_sent_to_ai_full,
                        "customer_context_sent": flow_customer_context_sent,
                    }
                    print(f"PRIORITY: First response is ask_gender (gender unknown). Skipping tool calls and sending gender question.")
                    return first_parsed
            except (json.JSONDecodeError, TypeError):
                pass

        if tool_calls:
            messages.append(first_response_message)
            tool_round_trips = []  # For Activity Flow: AI request → Bot response
            ai_first_response_with_tools = gpt_raw_content  # Save before overwrite

            # Track check_next_appointment result to auto-chain appointment_id for update_appointment_date
            check_next_appointment_result = None
            paused_appointment_lookup_cache = {}

            def normalize_phone_for_lookup(raw_phone: str) -> str:
                if not raw_phone:
                    return ""
                normalized = str(raw_phone).replace("+", "").replace(" ", "").replace("-", "")
                if normalized.startswith("961"):
                    normalized = normalized[3:]
                return normalized

            def extract_appointment_id(appointment_payload: dict):
                if not isinstance(appointment_payload, dict):
                    return None
                for key in ("appointment_id", "id", "appointmentId"):
                    value = appointment_payload.get(key)
                    if value is None:
                        continue
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        continue
                return None

            def extract_appointment_status(appointment_payload: dict) -> str:
                if not isinstance(appointment_payload, dict):
                    return ""

                raw_status = (
                    appointment_payload.get("status")
                    or appointment_payload.get("appointment_status")
                    or appointment_payload.get("appointmentStatus")
                    or appointment_payload.get("state")
                    or appointment_payload.get("appointment_state")
                )

                if isinstance(raw_status, dict):
                    raw_status = raw_status.get("name") or raw_status.get("status")

                return str(raw_status or "").strip()

            def is_paused_status(status_value: str) -> bool:
                status_normalized = str(status_value or "").strip().lower().replace("_", " ").replace("-", " ")
                return status_normalized in {
                    "pause",
                    "paused",
                    "postpone",
                    "postponed",
                    "on hold",
                    "hold",
                    "paused appointment",
                    "مؤجل",
                    "مؤجل",
                    "تاجيل",
                    "تأجيل",
                }

            def extract_check_next_appointment(response_payload: dict) -> dict:
                if not isinstance(response_payload, dict):
                    return {}
                data = response_payload.get("data")
                if isinstance(data, dict):
                    appointment_payload = data.get("appointment")
                    if isinstance(appointment_payload, dict):
                        return appointment_payload
                    # Some APIs return the appointment directly under data
                    if extract_appointment_id(data):
                        return data
                return {}

            def extract_customer_appointments(response_payload: dict) -> list:
                if not isinstance(response_payload, dict):
                    return []
                data = response_payload.get("data")
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
                if isinstance(data, dict):
                    if isinstance(data.get("appointments"), list):
                        return [item for item in data.get("appointments", []) if isinstance(item, dict)]
                    if isinstance(data.get("data"), list):
                        return [item for item in data.get("data", []) if isinstance(item, dict)]
                    appointment_payload = data.get("appointment")
                    if isinstance(appointment_payload, dict):
                        return [appointment_payload]
                    if extract_appointment_id(data):
                        return [data]
                return []

            def detect_change_request_intent(user_text: str) -> bool:
                text = str(user_text or "").strip().lower()
                if not text:
                    return False

                change_patterns = [
                    r"\b(reschedule|rescheduling|postpone|postponing|push back|move appointment|change appointment|shift appointment)\b",
                    r"\b(reporter|decaler|décaler|deplacer|déplacer|changer rendez[- ]?vous)\b",
                    r"(تأجيل|اجل|أجل|أجّل|تغيير الموعد|غير الموعد|غيّر الموعد|نقل الموعد|تبديل الموعد|موعد تاني|موعد اخر|موعد آخر)",
                    r"\b(2ajel|ajjel|ghayer el maw3ed|ghayer maw3ed|postpone el maw3ed|reschedule el maw3ed)\b",
                ]
                return any(re.search(pattern, text, re.IGNORECASE | re.UNICODE) for pattern in change_patterns)

            async def find_paused_appointment_id(phone_to_lookup: str):
                nonlocal check_next_appointment_result
                normalized_phone = normalize_phone_for_lookup(phone_to_lookup)
                if not normalized_phone:
                    return None

                if normalized_phone in paused_appointment_lookup_cache:
                    return paused_appointment_lookup_cache[normalized_phone]

                paused_appointment_id = None

                # First check the dedicated "next appointment" endpoint.
                try:
                    next_result = await api_integrations.check_next_appointment(phone=normalized_phone)
                    if isinstance(next_result, dict) and next_result.get("success"):
                        check_next_appointment_result = next_result
                        next_appointment_payload = extract_check_next_appointment(next_result)
                        if is_paused_status(extract_appointment_status(next_appointment_payload)):
                            paused_appointment_id = extract_appointment_id(next_appointment_payload)
                except Exception as pause_next_error:
                    print(f"WARNING: Paused guard check_next_appointment failed for {normalized_phone}: {pause_next_error}")

                # Fallback: scan all customer appointments for paused records.
                if not paused_appointment_id:
                    try:
                        customer_appointments = await api_integrations.get_customer_appointments(phone=normalized_phone)
                        if isinstance(customer_appointments, dict) and customer_appointments.get("success"):
                            for appointment_payload in extract_customer_appointments(customer_appointments):
                                if is_paused_status(extract_appointment_status(appointment_payload)):
                                    paused_appointment_id = extract_appointment_id(appointment_payload)
                                    if paused_appointment_id:
                                        break
                    except Exception as pause_list_error:
                        print(f"WARNING: Paused guard get_customer_appointments failed for {normalized_phone}: {pause_list_error}")

                paused_appointment_lookup_cache[normalized_phone] = paused_appointment_id
                return paused_appointment_id

            def collect_user_datetime_text(context_messages: list, latest_user_input: str) -> str:
                """
                Collect recent user text for date intent detection.
                Keeps chronology and ends with latest user input so the newest
                'today/tomorrow' intent wins over stale history.
                """
                recent_user_messages = []
                for msg in context_messages[-12:]:
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        recent_user_messages.append(content.strip())

                # Keep only the most recent few user turns to avoid stale date leakage.
                recent_user_messages = recent_user_messages[-4:]

                latest_clean = (latest_user_input or "").strip()
                if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
                    recent_user_messages.append(latest_clean)

                return " ".join(recent_user_messages).strip()

            def normalize_tool_date(function_name: str, function_args: dict, all_user_text: str) -> None:
                """
                Normalize tool date using fixed +0200 timezone and multilingual relative phrases.
                Keeps original date if parsing fails.
                """
                if "date" not in function_args:
                    return

                original_date_str = str(function_args["date"]).strip()
                if not original_date_str:
                    return

                now = now_in_bot_tz()
                dt_obj = resolve_relative_datetime(all_user_text, reference=now)
                if dt_obj:
                    print(f"DEBUG: Resolved relative datetime from user text ({function_name}): {all_user_text} -> {dt_obj}")
                else:
                    dt_obj = parse_datetime_flexible(original_date_str)
                    if not dt_obj:
                        print(f"WARNING: Could not parse tool date '{original_date_str}' for {function_name}. Keeping original.")
                        return
                    dt_obj = align_datetime_to_day_reference(dt_obj, all_user_text, reference=now)

                # If GPT provided a past year, keep intent but move to current year.
                if dt_obj.year < now.year:
                    dt_obj = dt_obj.replace(year=now.year)
                    print(f"WARNING: GPT proposed past year. Adjusted to current year: {dt_obj}")

                # Cap to 365 days ahead.
                max_allowed = now + datetime.timedelta(days=365)
                if dt_obj > max_allowed:
                    dt_obj = max_allowed.replace(second=0, microsecond=0)
                    print(f"WARNING: Date too far in future. Capped to: {dt_obj}")

                # Must stay in the future for API validation.
                if dt_obj <= now:
                    dt_obj = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
                    print(f"WARNING: Date was not in future. Adjusted to: {dt_obj}")

                function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                print(f"DEBUG: Normalized date for {function_name}: {original_date_str} -> {function_args['date']}")

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                all_user_text_for_date = collect_user_datetime_text(current_context_messages, user_input)
                user_requested_change = detect_change_request_intent(all_user_text_for_date) or is_reschedule_intent
                forced_update_appointment_id = None
                booking_state = config.user_booking_state[user_id]

                # Keep pricing args and persisted booking state in sync.
                _merge_pricing_args_with_booking_state(
                    function_name=function_name,
                    function_args=function_args,
                    booking_state=booking_state,
                    current_gender=current_gender,
                    user_input=user_input,
                )

                # SAFETY GUARD: Reschedule intent must never route to working-hours tool.
                if function_name == "get_clinic_hours" and (is_reschedule_intent or user_requested_change):
                    phone_for_reschedule = (
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or user_id
                    )
                    print(
                        f"SAFETY: Re-routing get_clinic_hours -> check_next_appointment for reschedule intent (phone={phone_for_reschedule})."
                    )
                    function_name = "check_next_appointment"
                    function_args = {"phone": phone_for_reschedule}

                # SAFETY GUARD: If a paused appointment exists and user asks to change/reschedule,
                # never allow create_appointment. Force update_appointment_date.
                if function_name == "create_appointment" and user_requested_change:
                    phone_for_pause_guard = normalize_phone_for_lookup(
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or user_id
                    )

                    # Prevent hallucinated date/time for change requests too.
                    if not text_mentions_datetime(all_user_text_for_date):
                        print("SAFETY: Change request detected without explicit date/time. Asking user for date/time.")
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "What new date and time would you like for your appointment?" if current_preferred_lang == "en" else
                                        "أكيد، شو التاريخ والوقت الجديد يلي بدك ياه لموعدك؟" if current_preferred_lang == "ar" else
                                        "Bien sûr, quelle nouvelle date et heure souhaitez-vous pour votre rendez-vous?" if current_preferred_lang == "fr" else
                                        "أكيد، shu el tarekh w el wa2et el jdid li badak yeh lal maw3ad?",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    paused_appointment_id = await find_paused_appointment_id(phone_for_pause_guard)
                    if paused_appointment_id:
                        requested_date = function_args.get("date")
                        function_name = "update_appointment_date"
                        function_args = {
                            "appointment_id": paused_appointment_id,
                            "phone": phone_for_pause_guard,
                            "date": requested_date,
                        }
                        forced_update_appointment_id = paused_appointment_id
                        print(
                            f"SAFETY: Converted create_appointment -> update_appointment_date for paused appointment_id={paused_appointment_id}"
                        )
                
                # --- NEW LOGIC: Pre-process date/time for create_appointment tool call ---
                if function_name == "create_appointment":
                    # === CRITICAL VALIDATION: Ensure user explicitly provided date/time ===
                    # GPT sometimes makes up dates - we must verify the user actually specified one
                    def user_provided_datetime(messages, user_input):
                        """Check if user explicitly mentioned date/time in multilingual text."""
                        all_user_text = collect_user_datetime_text(messages, user_input)
                        has_datetime_hint = text_mentions_datetime(all_user_text)
                        if has_datetime_hint:
                            print(f"DEBUG: Date/time hint detected in user messages: {all_user_text}")
                        return has_datetime_hint

                    # Validate that user actually provided a date/time
                    if not user_provided_datetime(current_context_messages, user_input):
                        print("ERROR: GPT attempted to book without user specifying date/time. Rejecting.")
                        # Return response asking for date/time
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "What date and time would work best for your appointment?" if current_preferred_lang == "en" else
                                        "شو التاريخ والوقت يلي بيناسبك للموعد؟" if current_preferred_lang == "ar" else
                                        "Quel jour et quelle heure vous conviendraient pour le rendez-vous?" if current_preferred_lang == "fr" else
                                        "shu el tarekh w el wa2et li byesbak lal maw3ad?",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # === CRITICAL VALIDATION: Ensure user explicitly provided branch location ===
                    def user_provided_branch(messages, user_input):
                        """Check if user explicitly mentioned a branch location in their messages."""
                        branch_patterns = [
                            # Branch names
                            r'\b(?:beirut|beyrouth|بيروت|bayrut)\b',
                            r'\b(?:manara|منارة|el manara|el-manara)\b',
                            r'\b(?:antelias|انطلياس|antilyas)\b',
                            r'\b(?:center\s*haj|haj\s*building)\b',
                            # Generic branch references with location
                            r'\b(?:branch\s+(?:1|2|one|two))\b',
                            r'\b(?:first\s+branch|second\s+branch)\b',
                            r'\b(?:main\s+branch)\b',
                        ]

                        # Check user input and recent user messages
                        all_user_text = user_input.lower()
                        for msg in messages:
                            if msg.get("role") == "user":
                                all_user_text += " " + msg.get("content", "").lower()

                        for pattern in branch_patterns:
                            if re.search(pattern, all_user_text, re.IGNORECASE):
                                print(f"DEBUG: Found branch pattern in user messages: {pattern}")
                                return True

                        return False

                    # Validate that user actually provided a branch
                    if not user_provided_branch(current_context_messages, user_input):
                        print("ERROR: GPT attempted to book without user specifying branch. Rejecting.")
                        # Return response asking for branch
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "Which branch would you prefer? We have Beirut (Manara) and Antelias (Center Haj Building)." if current_preferred_lang == "en" else
                                        "أي فرع بتفضل؟ عنا بيروت (المنارة) وأنطلياس (سنتر الحاج)." if current_preferred_lang == "ar" else
                                        "Quelle branche préférez-vous? Nous avons Beyrouth (Manara) et Antelias (Center Haj)." if current_preferred_lang == "fr" else
                                        "ayya far3 btfadel? 3anna beirut (manara) w antelias (center haj).",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # Extract customer name and phone from the conversation if not provided in tool args
                    # CRITICAL FIX: For Qiscus, user_id is room_id, NOT phone number
                    # Get actual phone number from user_data_whatsapp
                    phone_number = config.user_data_whatsapp.get(user_id, {}).get('phone_number')
                    
                    # Fallback: If no phone_number stored, check if user_id looks like a phone number
                    if not phone_number:
                        # Check if user_id looks like a phone number (starts with + and has digits)
                        if user_id.startswith('+') or (user_id.replace('+', '').replace('-', '').replace(' ', '').isdigit() and len(user_id) >= 8):
                            phone_number = user_id
                            print(f"DEBUG: Using user_id as phone_number (Meta/Dialog360 format): {phone_number}")
                        else:
                            print(f"ERROR: No phone_number found for user {user_id} and user_id doesn't look like a phone number")
                    else:
                        print(f"DEBUG: Using stored phone_number from user_data: {phone_number}")

                    # CRITICAL FIX: Priority 1 - Use collected name (protected from webhook)
                    user_data_dict = config.user_data_whatsapp.get(user_id, {})
                    customer_name = user_data_dict.get('collected_name')
                    
                    if customer_name:
                        print(f"DEBUG: Using protected collected name: {customer_name}")
                    
                    # Priority 2: Check config.user_names (might be overwritten by webhook)
                    if not customer_name:
                        customer_name = config.user_names.get(user_id)
                        # Skip if Arabic (causes API 500 errors)
                        if customer_name and re.search(r'[\u0600-\u06FF]', customer_name):
                            print(f"WARNING: Skipping Arabic name from config: {customer_name}")
                            customer_name = None
                        elif customer_name:
                            print(f"DEBUG: Using name from config.user_names: {customer_name}")
                    
                    # Priority 3: Search conversation history for Latin name
                    # Check BOTH user messages AND bot messages (GPT might have confirmed the name)
                    if not customer_name:
                        for msg_entry in reversed(current_context_messages + [{"role": "user", "content": user_input}]):
                            msg_content = msg_entry["content"].strip()
                            msg_role = msg_entry["role"]
                            
                            # Pattern 1: User explicitly states their name
                            if msg_role == "user":
                                name_match = re.search(
                                    r"(?:my name is|i am|i'm|call me|انا اسمي|اسمي|اسمي هو|je\s*m['\s]?appelle|je suis|moi c'est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
                                    msg_content,
                                    re.IGNORECASE | re.UNICODE
                                )
                                if name_match:
                                    potential_name = name_match.group(1).strip()
                                    
                                    # Validate: name should not contain booking-related words
                                    booking_keywords = [
                                        'book', 'appointment', 'schedule', 'reserve', 'موعد', 'حجز',
                                        'want', 'need', 'like', 'please', 'tomorrow', 'today', 'بدي', 'بحب',
                                        'just', 'an', 'the', 'a', 'have', 'get'
                                    ]
                                    
                                    contains_booking_word = any(
                                        keyword in potential_name.lower() 
                                        for keyword in booking_keywords
                                    )
                                    
                                    if not contains_booking_word:
                                        customer_name = potential_name
                                        print(f"DEBUG: Extracted name from user message with prefix: {customer_name}")
                                        break
                            
                            # Pattern 2: Bot confirmed the name (e.g., "Your name is John Smith")
                            elif msg_role == "assistant":
                                name_match = re.search(
                                    r'(?:your name is|you are|you\'re called|اسمك|اسمك هو|ton nom est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})',
                                    msg_content,
                                    re.IGNORECASE | re.UNICODE
                                )
                                if name_match:
                                    potential_name = name_match.group(1).strip()
                                    
                                    # Clean up any trailing punctuation or words
                                    potential_name = re.sub(r'\s+(and|et|و|،|,|\.).*$', '', potential_name, flags=re.IGNORECASE)
                                    
                                    # Validate length
                                    if 2 <= len(potential_name) <= 50:
                                        customer_name = potential_name
                                        print(f"DEBUG: Extracted name from bot confirmation: {customer_name}")
                                        break
                            
                            # Pattern 3: User provides JUST their name (2-4 words, proper capitalization)
                            # This is risky but necessary when user responds to "What is your name?"
                            elif msg_role == "user" and not customer_name:
                                # Check if this looks like a standalone name response
                                words = msg_content.split()
                                if 1 <= len(words) <= 4:
                                    # Must start with capital letter or be Arabic
                                    if (re.match(r'^[A-ZÀ-Ÿا-ي]', msg_content, re.UNICODE) and 
                                        re.match(r'^[A-Za-zÀ-ÿا-ي\s\-\']+$', msg_content, re.UNICODE)):
                                        
                                        # Exclude common words and booking terms
                                        excluded_words = [
                                            'yes', 'no', 'ok', 'okay', 'sure', 'please', 'thanks', 'hello', 'hi',
                                            'book', 'appointment', 'schedule', 'tomorrow', 'today', 'now',
                                            'نعم', 'لا', 'تمام', 'ماشي', 'شكرا', 'مرحبا', 'موعد', 'حجز',
                                            'oui', 'non', 'merci', 'bonjour', 'salut'
                                        ]
                                        
                                        if msg_content.lower() not in excluded_words:
                                            # Check if previous bot message was asking for name
                                            # Look back in conversation for name request
                                            asking_for_name = False
                                            for prev_msg in reversed(current_context_messages):
                                                if prev_msg["role"] == "assistant":
                                                    prev_content = prev_msg["content"].lower()
                                                    if any(phrase in prev_content for phrase in [
                                                        'your name', 'full name', 'what is your name', 'may i have your name',
                                                        'اسمك', 'ما اسمك', 'شو اسمك',
                                                        'votre nom', 'ton nom', 'quel est votre nom'
                                                    ]):
                                                        asking_for_name = True
                                                        break
                                                # Only check last 2 bot messages
                                                if prev_msg["role"] == "assistant":
                                                    break
                                            
                                            if asking_for_name:
                                                customer_name = msg_content.strip()
                                                print(f"DEBUG: Extracted standalone name (response to name question): {customer_name}")
                                                break
                            
                            if customer_name:
                                break
                    # === NEW PATCH: Persist detected customer name ===
                    if customer_name:
                        # Save name in runtime config
                        config.user_data_whatsapp[user_id]["user_name"] = customer_name
                        config.user_names[user_id] = customer_name

                        # Persist to Firestore asynchronously
                        try:
                            from utils.utils import save_user_name_to_firestore
                            await save_user_name_to_firestore(user_id, customer_name)
                        except Exception as e:
                            print(f"⚠️ Could not persist user name for {user_id}: {e}")


                    # Update function_args with inferred phone/name if not present
                    function_args["phone"] = phone_number # Use the extracted/stored phone number
                    
                    # Check if customer exists, if not, create them
                    customer_exists = False
                    customer_gender_for_api = current_gender # Default to current gender
                    if customer_gender_for_api == "unknown":
                        # Attempt to infer from name if needed for create_customer
                        if customer_name:
                            # This is a very basic heuristic; a dedicated service would be better
                            if current_preferred_lang == "ar" or current_preferred_lang == "franco":
                                if re.search(r'\b(ظ…ط­ظ…ظˆط¯|ظ…ط­ظ…ط¯|ط¹ظ„ظٹ|ط£ط­ظ…ط¯|ط®ط§ظ„ط¯|ط±ط¬ظ„|ط´ط¨|ط°ظƒط±)\b', customer_name, re.UNICODE):
                                    customer_gender_for_api = "male"
                                elif re.search(r'\b(ظ„ظٹظ†ط§|ظپط§ط·ظ…ط©|ظ…ط±ظٹظ…|ط³ط§ط±ط©|ط¨ظ†طھ|طµط¨ظٹط©|ط£ظ†ط«ظ‰)\b', customer_name, re.UNICODE):
                                    customer_gender_for_api = "female"
                            elif current_preferred_lang == "en":
                                if re.search(r'\b(john|paul|male|boy)\b', customer_name, re.IGNORECASE):
                                    customer_gender_for_api = "male"
                                elif re.search(r'\b(jane|mary|female|girl)\b', customer_name, re.IGNORECASE):
                                    customer_gender_for_api = "female"
                            
                        if customer_gender_for_api == "unknown":
                            customer_gender_for_api = "male" # Default to male if still unknown, adjust as clinic policy

                    # Ensure gender is in "Male" or "Female" format as required by API
                    if customer_gender_for_api:
                        customer_gender_for_api = customer_gender_for_api.capitalize() # "male" -> "Male"


                    if phone_number:
                        customer_check_response = await api_integrations.get_customer_by_phone(phone=phone_number) # NEW API call
                        if customer_check_response and customer_check_response.get("success") and customer_check_response.get("data"):
                            customer_exists = True
                            print(f"DEBUG: Customer {phone_number} found in API.")
                        else:
                            print(f"DEBUG: Customer {phone_number} not found in API. Attempting to create.")
                            if customer_name and customer_gender_for_api:
                                create_customer_response = await api_integrations.create_customer(
                                    name=customer_name, 
                                    phone=phone_number, 
                                    gender=customer_gender_for_api, # Pass as "Male" or "Female"
                                    branch_id=config.DEFAULT_BRANCH_ID # NEW: Ensure branch_id is passed for customer creation
                                )
                                if create_customer_response and create_customer_response.get("success"):
                                    customer_exists = True
                                    print(f"DEBUG: Successfully created new customer {customer_name} in API.")
                                else:
                                    print(f"ERROR: Failed to create customer {customer_name}: {create_customer_response.get('message', 'Unknown error')}")
                                    err_content = json.dumps({"success": False, "message": f"Failed to create customer: {create_customer_response.get('message', 'Unknown error')}"})
                                    tool_round_trips.append({
                                        "ai_requested": "create_customer",
                                        "args": json.dumps(function_args)[:300],
                                        "bot_returned": err_content[:600],
                                    })
                                    messages.append({
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": "create_customer_failed",
                                        "content": err_content,
                                    })
                                    # Indicate that booking failed because customer creation failed
                                    parsed_response = {
                                        "action": "ask_for_details_for_booking", # Keep asking for details or suggest human handover
                                        "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظˆط§ط¬ظ‡طھ ظ…ط´ظƒظ„ط© ظپظٹ طھط³ط¬ظٹظ„ ط¨ظٹط§ظ†ط§طھظƒ ظƒط¹ظ…ظٹظ„ ط¬ط¯ظٹط¯. ظٹط±ط¬ظ‰ ط§ظ„طھط£ظƒط¯ ظ…ظ† طµط­ط© ط§ظ„ط§ط³ظ… ظˆط±ظ‚ظ… ط§ظ„ظ‡ط§طھظپطŒ ط£ظˆ ظٹظ…ظƒظ†ظ†ظٹ طھط­ظˆظٹظ„ظƒ ظ„ظ…ظˆط¸ظپ ظ„ظ…ط³ط§ط¹ط¯طھظƒ.",
                                        "detected_language": current_preferred_lang,
                                        "detected_gender": current_gender,
                                        "current_gender_from_config": current_gender
                                    }
                                    parsed_response["_flow_meta"] = {
                                        "ai_first_response": gpt_raw_content[:1500] if gpt_raw_content else None,
                                        "tool_round_trips": tool_round_trips,
                                        "tool_calls": ["create_customer"],
                                    }
                                    return parsed_response
                            else:
                                print("WARNING: Cannot create customer, missing name or gender.")
                                # Use language-specific error messages
                                error_messages = {
                                    "ar": f"ظ„ط£طھظ…ظƒظ† ظ…ظ† ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط£ط­طھط§ط¬ ظ„ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}",
                                    "en": f"To book your appointment, I need your full name{'.' if current_gender != 'unknown' else ' and gender (male or female).'}",
                                    "fr": f"Pour rأ©server votre rendez-vous, j'ai besoin de votre nom complet{'.' if current_gender != 'unknown' else ' et votre sexe (homme ou femme).'}",
                                    "franco": f"ظ„ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط¨ط¯ظٹ ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}"
                                }
                                parsed_response = {
                                    "action": "ask_for_details_for_booking",
                                    "bot_reply": error_messages.get(current_preferred_lang, error_messages["en"]),
                                    "detected_language": current_preferred_lang,
                                    "detected_gender": current_gender,
                                    "current_gender_from_config": current_gender
                                }
                                return parsed_response
                    else:
                        print("WARNING: Cannot check or create customer, phone number not found.")
                        # This should rarely happen since phone_number = user_id (WhatsApp ID)
                        error_messages = {
                            "ar": "ط¹ط°ط±ط§ظ‹طŒ ط­ط¯ط«طھ ظ…ط´ظƒظ„ط© ظپظٹ ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… ظ‡ط§طھظپظƒ. ظٹط±ط¬ظ‰ ط§ظ„ظ…ط­ط§ظˆظ„ط© ظ…ط±ط© ط£ط®ط±ظ‰.",
                            "en": "Sorry, there was an issue verifying your phone number. Please try again.",
                            "fr": "Dأ©solأ©, il y a eu un problأ¨me pour vأ©rifier votre numأ©ro de tأ©lأ©phone. Veuillez rأ©essayer.",
                            "franco": "ط¹ط°ط±ط§ظ‹طŒ ظپظٹ ظ…ط´ظƒظ„ط© ط¨ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… طھظ„ظپظˆظ†ظƒ. ط¬ط±ط¨ ظ…ط±ط© طھط§ظ†ظٹط©."
                        }
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": error_messages.get(current_preferred_lang, error_messages["en"]),
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # Only proceed to create_appointment if customer_exists is True
                    if not customer_exists:
                        # This should ideally not be reached if previous logic is sound
                        print("ERROR: Customer not created/found, cannot proceed with appointment.")
                        parsed_response = {
                            "action": "human_handover",
                            "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظ„ط§ ظٹظ…ظƒظ†ظ†ظٹ ط¥طھظ…ط§ظ… ط§ظ„ط­ط¬ط² ط­ط§ظ„ظٹظ‹ط§. ط³ط£ظ‚ظˆظ… ط¨طھط­ظˆظٹظ„ظƒ ط¥ظ„ظ‰ ط£ط­ط¯ ظ…ظˆط¸ظپظٹظ†ط§ ظ„ظ„ظ…ط³ط§ط¹ط¯ط©.",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response


                    # NEW: Provide default values for service_id, machine_id, branch_id if missing
                    # Use .get() with a fallback to config defaults
                    function_args["service_id"] = function_args.get("service_id", config.DEFAULT_SERVICE_ID)
                    function_args["machine_id"] = function_args.get("machine_id", config.DEFAULT_MACHINE_ID)
                    function_args["branch_id"] = function_args.get("branch_id", config.DEFAULT_BRANCH_ID)
                    _remember_booking_selection(user_id, function_args)

                    selected_service_id = _safe_int(function_args.get("service_id"))
                    selected_body_part_ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
                    if selected_body_part_ids:
                        function_args["body_part_ids"] = selected_body_part_ids
                        _remember_booking_selection(user_id, function_args)
                    if (
                        selected_service_id in body_part_required_service_ids
                        and not selected_body_part_ids
                    ):
                        print("SAFETY: create_appointment called without body_part_ids for body-part-required service.")
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": _pricing_missing_details_reply(current_preferred_lang, "body_part"),
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender,
                        }
                        return parsed_response

                    # Date normalization and intent alignment (+0200)
                    normalize_tool_date(function_name, function_args, all_user_text_for_date)
                    
                    # NEW: Remove 'name' from function_args as create_appointment does not accept it directly.
                    # This resolves the `unexpected keyword argument 'name'` error.
                    if 'name' in function_args:
                        print(f"DEBUG: Removing 'name' argument '{function_args['name']}' from create_appointment call as it's not supported.")
                        del function_args['name']

                    # For hair removal/tattoo: send body_parts with session_number=1 for first session (API may require this)
                    if function_name == "create_appointment" and selected_body_part_ids and selected_service_id in body_part_required_service_ids:
                        function_args["body_parts_with_sessions"] = [{"body_part_id": bp_id, "session_number": 1} for bp_id in selected_body_part_ids]

                if function_name == "update_appointment_date":
                    if user_requested_change and not text_mentions_datetime(all_user_text_for_date):
                        print("SAFETY: update_appointment_date requested without explicit date/time. Asking user for new date/time.")
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "Sure, what new date and time would you like for your appointment?" if current_preferred_lang == "en" else
                                        "أكيد، شو التاريخ والوقت الجديد يلي بدك ياه لموعدك؟" if current_preferred_lang == "ar" else
                                        "Bien sûr, quelle nouvelle date et heure souhaitez-vous pour votre rendez-vous?" if current_preferred_lang == "fr" else
                                        "أكيد، shu el tarekh w el wa2et el jdid li badak yeh lal maw3ad?",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    phone_for_pause_guard = normalize_phone_for_lookup(
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or user_id
                    )

                    if user_requested_change and phone_for_pause_guard:
                        paused_appointment_id = await find_paused_appointment_id(phone_for_pause_guard)
                        if paused_appointment_id and function_args.get("appointment_id") != paused_appointment_id:
                            print(
                                f"SAFETY: Overriding update_appointment_date appointment_id with paused appointment_id={paused_appointment_id}"
                            )
                            function_args["appointment_id"] = paused_appointment_id
                            forced_update_appointment_id = paused_appointment_id

                    if phone_for_pause_guard and not function_args.get("phone"):
                        function_args["phone"] = phone_for_pause_guard

                    normalize_tool_date(function_name, function_args, all_user_text_for_date)

                # --- FIX: Auto-chain appointment_id from check_next_appointment to update_appointment_date ---
                # When GPT calls both tools together, it can't know the real appointment_id until check_next_appointment returns.
                # This code automatically uses the correct appointment_id from the check result.
                if function_name == "update_appointment_date" and check_next_appointment_result and not forced_update_appointment_id:
                    actual_appointment_id = extract_appointment_id(extract_check_next_appointment(check_next_appointment_result))
                    if actual_appointment_id:
                        gpt_provided_id = function_args.get("appointment_id")
                        if gpt_provided_id != actual_appointment_id:
                            print(f"DEBUG: Auto-chaining appointment_id: GPT provided {gpt_provided_id}, actual is {actual_appointment_id}")
                            function_args["appointment_id"] = actual_appointment_id
                        else:
                            print(f"DEBUG: appointment_id already correct: {actual_appointment_id}")

                _remember_booking_selection(user_id, function_args)

                # Special tool: GPT requests knowledge retrieval - bot runs selector, returns content to GPT
                if function_name == "retrieve_relevant_knowledge":
                    user_msg = function_args.get("user_message", user_input)
                    try:
                        from services.dynamic_retrieval_service import (
                            is_dynamic_retrieval_available,
                            select_files_llm,
                            _load_content_by_ids,
                            _get_default_general_and_style,
                            _ensure_style_included,
                        )
                        if is_dynamic_retrieval_available():
                            result = await select_files_llm(user_msg)
                            action = result.get("action", "fallback_to_general")
                            files = result.get("files", [])
                            if action == "ask_clarification":
                                tool_output = {"action": "ask_clarification", "content": "", "message": "User message needs clarification. Ask the user which service they mean (hair removal, tattoo, whitening, etc.)."}
                            elif files:
                                merged, has_style = _load_content_by_ids(files)
                                merged = _ensure_style_included(merged, has_style) if merged else _get_default_general_and_style()
                                tool_output = {"action": "normal", "content": merged or "", "files_loaded": files}
                            else:
                                merged = _get_default_general_and_style()
                                merged = _ensure_style_included(merged, False)
                                tool_output = {"action": "fallback_to_general", "content": merged or ""}
                        else:
                            tool_output = {"action": "fallback_to_general", "content": config.CORE_KNOWLEDGE_BASE or ""}
                        tool_content = json.dumps(tool_output)
                        tool_round_trips.append({"ai_requested": function_name, "args": json.dumps(function_args)[:300], "bot_returned": (tool_content[:600] + "...") if len(tool_content) > 600 else tool_content})
                        messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": tool_content})
                    except Exception as kr_e:
                        print(f"⚠️ retrieve_relevant_knowledge error: {kr_e}")
                        err_content = json.dumps({"success": False, "content": "", "message": str(kr_e)})
                        tool_round_trips.append({"ai_requested": function_name, "args": json.dumps(function_args)[:300], "bot_returned": err_content[:600]})
                        messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": err_content})
                elif hasattr(api_integrations, function_name) and callable(getattr(api_integrations, function_name)):
                    function_to_call = getattr(api_integrations, function_name)
                    print(f"DEBUG: Executing tool: {function_name} with args: {function_args}")

                    try:
                        tool_output = await function_to_call(**function_args)
                        print(f"DEBUG: Tool output for {function_name}: {tool_output}")

                        # Store check_next_appointment result for auto-chaining appointment_id
                        if function_name == "check_next_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            check_next_appointment_result = tool_output
                            print(f"DEBUG: Stored check_next_appointment result for auto-chaining")

                        # Store machine_id to booking_state when get_machines returns and user said Candela/Neo/Quadro
                        if function_name == "get_machines" and isinstance(tool_output, dict) and tool_output.get("success"):
                            data = tool_output.get("data", [])
                            all_txt = (all_user_text_for_date or user_input or "").lower()
                            machine_keywords = [
                                ("candela", "كانديلا", "candila"),
                                ("neo", "نيو"),
                                ("quadro", "كوادرو"),
                            ]
                            for kw_en, *rest in machine_keywords:
                                kw_ar = rest[0] if rest else ""
                                kw_alt = rest[1] if len(rest) > 1 else ""
                                if kw_en in all_txt or (kw_ar and kw_ar in (user_input or "")) or kw_alt in all_txt:
                                    for m in data if isinstance(data, list) else []:
                                        name = (m.get("name") or "").strip().lower()
                                        if name and kw_en in name:
                                            if user_id not in config.user_booking_state:
                                                config.user_booking_state[user_id] = {}
                                            config.user_booking_state[user_id]["machine_id"] = _safe_int(m.get("id"))
                                            break
                                    break

                        # 📊 ANALYTICS: Track service when appointment is created
                        if function_name == "create_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            from services.analytics_events import analytics

                            # Get service and machine names from API response
                            raw_data_payload = tool_output.get("data", {})
                            if isinstance(raw_data_payload, dict):
                                appointment_data = raw_data_payload.get("appointment") or {}
                                pricing_from_appointment = (
                                    raw_data_payload.get("pricing")
                                    or appointment_data.get("pricing")
                                    or appointment_data.get("price_details")
                                )
                            else:
                                appointment_data = {}
                                pricing_from_appointment = None
                            if pricing_from_appointment:
                                latest_pricing_payload = pricing_from_appointment
                                config.user_booking_state[user_id]["last_pricing_payload"] = pricing_from_appointment
                                print("💰 Synced pricing payload captured from create_appointment")
                            service_info = appointment_data.get("service") or {}
                            service_name = service_info.get("name", "unknown_service") if isinstance(service_info, dict) else str(service_info)
                            machine_info = appointment_data.get("machine")
                            # Handle machine being either a string or a dict
                            machine_name = machine_info.get("name", "unassigned") if isinstance(machine_info, dict) else (str(machine_info) if machine_info else "unassigned")

                            print(f"📊 Analytics: Service tracked from appointment - {service_name}, Machine: {machine_name}")
                            
                            # Log appointment booking
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="booked",
                                messages_count=len(current_context_messages)
                            )
                            print(f"📊 Analytics: Appointment booked - {service_name}")
                        elif function_name == "create_appointment" and isinstance(tool_output, dict) and not tool_output.get("success"):
                            err_msg = (tool_output or {}).get("message", "Unknown error")
                            api_failure_reason = f"create_appointment_tool_failed: {err_msg}"
                            print(f"create_appointment tool: API failed: {err_msg}")
                        
                        # 📊 ANALYTICS: Track appointment reschedule
                        elif function_name == "update_appointment_date" and isinstance(tool_output, dict) and tool_output.get("success"):
                            from services.analytics_events import analytics
                            
                            # Get service from appointment data if available
                            appointment_data = tool_output.get("data", {})
                            service_id = appointment_data.get("service_id")
                            
                            service_map = {
                                1: "laser_hair_removal",
                                2: "tattoo_removal",
                                3: "co2_laser",
                                4: "skin_whitening",
                                5: "botox",
                                6: "fillers"
                            }
                            service_name = service_map.get(service_id, "unknown_service") if service_id else "unknown_service"
                            
                            # Log appointment reschedule
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="rescheduled",
                                messages_count=0
                            )
                            print(f"📊 Analytics: Appointment rescheduled - {service_name}")
                        
                        tool_content = json.dumps(tool_output)
                        tool_round_trips.append({
                            "ai_requested": function_name,
                            "args": json.dumps(function_args)[:300],
                            "bot_returned": (tool_content[:600] + "...") if len(tool_content) > 600 else tool_content,
                        })
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": tool_content,
                            }
                        )
                    except Exception as tool_e:
                        api_failure_reason = f"tool_execution_error:{function_name}: {tool_e}"
                        print(f"â‌Œ ERROR executing tool {function_name}: {tool_e}")
                        err_content = json.dumps({"success": False, "message": f"Error executing tool: {tool_e}"})
                        tool_round_trips.append({
                            "ai_requested": function_name,
                            "args": json.dumps(function_args)[:300],
                            "bot_returned": err_content[:600],
                        })
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": err_content,
                            }
                        )
                else:
                    api_failure_reason = f"tool_not_found:{function_name}"
                    print(f"â‌Œ ERROR: Tool function '{function_name}' not found in api_integrations.")
                    err_content = json.dumps({"success": False, "message": f"Tool function '{function_name}' not implemented."})
                    tool_round_trips.append({
                        "ai_requested": function_name,
                        "args": json.dumps(function_args)[:300],
                        "bot_returned": err_content[:600],
                    })
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": err_content,
                        }
                    )

            second_response = await client.chat.completions.create(
                model="gpt-5.4-mini",
                messages=messages,
                response_format={"type": "json_object"}
            )
            if not second_response.choices:
                raise ValueError("GPT returned no choices (after tool call)")
            gpt_raw_content = second_response.choices[0].message.content.strip() if second_response.choices[0].message.content else ""
            print(f"GPT Raw Response (after tool call): {gpt_raw_content}")

            parsed_response = _parse_gpt_response_json(gpt_raw_content)
        else:
            parsed_response = _parse_gpt_response_json(gpt_raw_content)

        # AI decides language - use AI's detected_language from response, fallback to pre-detected
        bot_reply = parsed_response.get("bot_reply", "")
        ai_detected = parsed_response.get("detected_language")
        detected_language = ai_detected if ai_detected in ("ar", "en", "fr", "franco") else current_preferred_lang
        parsed_response['detected_language'] = detected_language
        print(f"🌐 AI detected language: {detected_language}")

        # Sanitize: when replying in Arabic/franco, replace Latin brand names with Arabic (no mixing)
        if detected_language in ("ar", "franco") and bot_reply:
            bot_reply = _normalize_arabic_reply(bot_reply)
            parsed_response["bot_reply"] = bot_reply

        # Ensure current_gender_from_config in the output reflects the *actual* config value
        # This is critical for GPT to "see" the current state of the bot's knowledge about gender.
        parsed_response['current_gender_from_config'] = current_gender

        # Respect AI decision: do not override action/bot_reply here.
        # We only normalize metadata fields above (detected_language/current_gender_from_config).

        # We allow GPT to detect gender and signal it, but also check for explicit detection for robustness
        # This part ensures that if our local gender recognition service detects a strong gender, it's reflected
        # in the output, potentially overriding GPT's 'null' or 'unknown' if it was less confident.
        if explicitly_detected_gender_from_input and explicitly_detected_gender_from_input in ["male", "female"]:
            parsed_response['detected_gender'] = explicitly_detected_gender_from_input
        elif 'detected_gender' in parsed_response and parsed_response['detected_gender'] not in ["male", "female"]:
            # If GPT returned something like 'unknown' or 'null' for detected_gender, set it to None
            parsed_response['detected_gender'] = None 
        
        if "action" not in parsed_response or "bot_reply" not in parsed_response:
            raise ValueError("GPT response missing required fields (action or bot_reply)")

        # Flow logging metadata for dashboard transparency (detailed for Activity Flow)
        tool_names = [tc.function.name for tc in tool_calls] if tool_calls else []

        # Fallback: when AI returns action create_appointment, confirm_booking_details, OR answer_question with
        # booking-confirmation wording but never called the tool. Run create_appointment so it appears in the system.
        _bot_reply = (parsed_response.get("bot_reply") or "").strip().lower()
        _booking_confirm_phrases = ["تمّ حجز", "تم حجز", "تم تحديد الموعد", "تم تحديد موعد", "booked", "حجز موعد"]
        _says_booked = any(p in _bot_reply for p in _booking_confirm_phrases)
        _run_booking_fallback = (
            (parsed_response.get("action") in ("create_appointment", "confirm_booking_details")
             or (parsed_response.get("action") == "answer_question" and _says_booked))
            and "create_appointment" not in tool_names
        )
        if _run_booking_fallback:
            if user_id not in config.user_booking_state:
                config.user_booking_state[user_id] = {}
            booking_state = config.user_booking_state[user_id]
            # Extract preferred_machine_id, preferred_area from GPT's first JSON object (when it returns two objects)
            preferred = _extract_preferred_booking_from_gpt(gpt_raw_content) if gpt_raw_content else {}
            if preferred.get("preferred_machine_id") is not None:
                booking_state["machine_id"] = preferred["preferred_machine_id"]
            if preferred.get("preferred_area"):
                bp_ids = _area_name_to_body_part_ids(preferred["preferred_area"], _safe_int(booking_state.get("service_id")) or 12)
                if bp_ids:
                    booking_state["body_part_ids"] = bp_ids
            # If get_machines was called and user said Candela, extract machine_id from tool result
            try:
                _tr = tool_round_trips
            except NameError:
                _tr = []
            for tr in _tr:
                if tr.get("ai_requested") == "get_machines":
                    try:
                        ret = json.loads(tr.get("bot_returned", "{}"))
                        data = ret.get("data", [])
                        user_lower = (user_input or "").strip().lower()
                        for m in data if isinstance(data, list) else []:
                            name = (m.get("name") or "").strip().lower()
                            if name and ("candela" in user_lower or "كانديلا" in (user_input or "") or "candila" in user_lower) and "candela" in name:
                                booking_state["machine_id"] = _safe_int(m.get("id"))
                                break
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break
            phone = (
                config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                or customer_phone_clean
                or (user_id if (user_id and (user_id.startswith("+") or user_id.replace("+", "").replace("-", "").replace(" ", "").isdigit())) else None)
            )
            if phone:
                # Collect user text for date parsing (same logic as in-tool path)
                recent_user = []
                for msg in (current_context_messages or [])[-12:]:
                    if msg.get("role") == "user" and msg.get("content"):
                        recent_user.append(str(msg.get("content", "")).strip())
                recent_user = recent_user[-4:]
                if (user_input or "").strip() and (not recent_user or recent_user[-1] != (user_input or "").strip()):
                    recent_user.append((user_input or "").strip())
                all_user_text = " ".join(recent_user).strip()
                # Infer branch from conversation when not in booking_state
                if _safe_int(booking_state.get("branch_id")) is None:
                    if any(x in all_user_text.lower() for x in ["beirut", "بيروت", "beyrouth"]):
                        booking_state["branch_id"] = 1
                    elif any(x in all_user_text.lower() for x in ["antelias", "أنطلياس"]):
                        booking_state["branch_id"] = 2
                # Resolve machine_id from get_machines when user said Candela/Neo/Quadro but we don't have it yet
                if _safe_int(booking_state.get("machine_id")) is None:
                    all_lower = all_user_text.lower()
                    machine_keywords = [
                        ("candela", "كانديلا", "candila"),
                        ("neo", "نيو"),
                        ("quadro", "كوادرو"),
                    ]
                    for kw_en, kw_ar, kw_alt in machine_keywords:
                        if kw_en in all_lower or (kw_ar and kw_ar in (user_input or "")) or kw_alt in all_lower:
                            try:
                                machines_resp = await api_integrations.get_machines()
                                if machines_resp.get("success") and machines_resp.get("data"):
                                    for m in machines_resp["data"]:
                                        name = (m.get("name") or "").strip().lower()
                                        if name and kw_en in name:
                                            booking_state["machine_id"] = _safe_int(m.get("id"))
                                            break
                            except Exception as e:
                                print(f"Fallback get_machines for {kw_en}: {e}")
                            break
                # Resolve body_part_ids from preferred_area when missing
                if not _normalize_body_part_ids(booking_state.get("body_part_ids")) and preferred.get("preferred_area"):
                    svc_id = _safe_int(booking_state.get("service_id")) or _infer_service_id_for_pricing(user_input, current_gender, booking_state) or 12
                    bp_ids = _area_name_to_body_part_ids(preferred["preferred_area"], svc_id)
                    if not bp_ids:
                        # Try get_body_parts API: "full body" -> all body part IDs
                        area_lower = (preferred["preferred_area"] or "").strip().lower()
                        full_keys = ["full body", "full kel shi", "full kel chi", "جسم كامل", "كامل", "full"]
                        if any(k in area_lower or area_lower == k for k in full_keys):
                            try:
                                bp_resp = await api_integrations.get_body_parts(service_id=svc_id)
                                if bp_resp.get("success") and bp_resp.get("data"):
                                    bp_ids = [x for x in (_safe_int(item.get("id")) for item in bp_resp["data"]) if x is not None]
                            except Exception as e:
                                print(f"Fallback get_body_parts: {e}")
                    if bp_ids:
                        booking_state["body_part_ids"] = bp_ids
                if text_mentions_datetime(all_user_text):
                    now = now_in_bot_tz()
                    dt_obj = resolve_relative_datetime(all_user_text, reference=now)
                    # Fallback: "bokra" alone may not match resolve_relative_datetime; use detect_day_reference
                    if dt_obj is None and detect_day_reference(all_user_text) == "tomorrow":
                        # Try to extract hour (se3a 9, 9am, etc.) or default to 9:00
                        hour, minute = 9, 0
                        _h9 = re.search(r"(?:se3a|saa|ساعة|hour)\s*(\d{1,2})", all_user_text, re.I)
                        if _h9:
                            hour = min(23, max(0, int(_h9.group(1) or 9)))
                        _h2 = re.search(r"\b(\d{1,2})\s*(?:am|pm|صباحا|مساء|صبح)", all_user_text, re.I)
                        if _h2:
                            hour = min(23, max(0, int(_h2.group(1) or 9)))
                        tomorrow = (now + datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                        dt_obj = tomorrow
                    if dt_obj:
                        if dt_obj <= now:
                            dt_obj = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
                        max_allowed = now + datetime.timedelta(days=365)
                        if dt_obj > max_allowed:
                            dt_obj = max_allowed.replace(second=0, microsecond=0)
                        date_str = dt_obj.astimezone(BOOKING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                        service_id = _safe_int(booking_state.get("service_id")) or _infer_service_id_for_pricing(user_input, current_gender, booking_state) or config.DEFAULT_SERVICE_ID
                        machine_id = _safe_int(booking_state.get("machine_id")) or config.DEFAULT_MACHINE_ID
                        branch_id = _safe_int(booking_state.get("branch_id")) or config.DEFAULT_BRANCH_ID
                        body_part_ids = _normalize_body_part_ids(booking_state.get("body_part_ids")) or None
                        # BLOCK: Hair removal (1,12) and tattoo (13) REQUIRE body_part_ids. Do NOT create without them.
                        if service_id in body_part_required_service_ids and not body_part_ids:
                            _ar = "كرمال نثبّت الموعد على السيستم، لازم نعرف أي منطقة بالجسم بدك (مثلاً: جسم كامل، أرجل، باكيني، وجه...)."
                            _en = "To save the appointment on the system, I need to know which body area(s) you want (e.g. full body, legs, bikini, face...)."
                            parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
                        else:
                            customer_exists = False
                            cust_resp = await api_integrations.get_customer_by_phone(phone=phone)
                            if cust_resp and cust_resp.get("success") and cust_resp.get("data"):
                                customer_exists = True
                            if not customer_exists:
                                customer_name = config.user_names.get(user_id) or config.user_data_whatsapp.get(user_id, {}).get("collected_name")
                                if not customer_name or re.search(r"[\u0600-\u06FF]", customer_name or ""):
                                    customer_name = "Customer"
                                gender_cap = (current_gender or "male").capitalize()
                                create_cust = await api_integrations.create_customer(
                                    name=customer_name, phone=phone, gender=gender_cap, branch_id=config.DEFAULT_BRANCH_ID
                                )
                                if create_cust and create_cust.get("success"):
                                    customer_exists = True
                            if customer_exists:
                                try:
                                    # For hair removal/tattoo: send body_parts with session_number=1 for first session
                                    body_parts_with_sessions = None
                                    if body_part_ids and service_id in body_part_required_service_ids:
                                        body_parts_with_sessions = [{"body_part_id": bp_id, "session_number": 1} for bp_id in body_part_ids]
                                    result = await api_integrations.create_appointment(
                                        phone=phone,
                                        service_id=service_id,
                                        machine_id=machine_id,
                                        branch_id=branch_id,
                                        date=date_str,
                                        body_part_ids=body_part_ids if not body_parts_with_sessions else None,
                                        body_parts_with_sessions=body_parts_with_sessions,
                                    )
                                    if result and result.get("success"):
                                        _ar = "تم حجز موعدك بنجاح. رح تصلك تأكيدات من الفرع."
                                        _en = "Your appointment has been booked successfully. You will receive confirmation from the branch."
                                        parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
                                        print("create_appointment fallback: booking succeeded.")
                                    else:
                                        err_msg = (result or {}).get("message", "Unknown error")
                                        api_failure_reason = f"create_appointment_failed: {err_msg}"
                                        _ar = "عفواً، ما قدرنا نكمل الحجز. جرّب مرة تانية أو تواصل مع الفرع."
                                        _en = "Sorry, we couldn't complete the booking. Please try again or contact the branch."
                                        parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
                                        print(f"create_appointment fallback: API failed: {err_msg}")
                                except Exception as e:
                                    api_failure_reason = f"create_appointment_exception: {e}"
                                    print(f"create_appointment fallback error: {e}")
                                    _ar = "حدث خطأ أثناء الحجز. جرّب لاحقاً أو تواصل مع الفرع."
                                    _en = "An error occurred while booking. Please try again later or contact the branch."
                                    parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
                            else:
                                _ar = "لإتمام الحجز نحتاج اسمك الكامل. ممكن تخبرني شو اسمك؟"
                                _en = "To complete the booking we need your full name. What is your name?"
                                parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
                    else:
                        _ar = "لإتمام الحجز خبرني التاريخ والوقت (مثلاً خميس الساعة ١ بعد الظهر)."
                        _en = "To complete the booking please tell me the date and time (e.g. Thursday 1pm)."
                        parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
            else:
                _ar = "لإتمام الحجز نحتاج رقم هاتفك. تواصل معنا عبر الواتساب من الرقم اللي بدك تحجز فيه."
                _en = "To complete the booking we need your phone number. Please contact us from the number you want to book with."
                parsed_response["bot_reply"] = _ar if current_preferred_lang in ("ar", "franco") else _en
        # Token usage: when tool calls exist, sum BOTH first and second API call usage (second_response alone misses first call's output)
        first_usage = getattr(response, "usage", None) if tool_calls else None
        usage = (getattr(second_response, "usage", None) if tool_calls else getattr(response, "usage", None))
        if tool_calls and first_usage and usage:
            pt1 = getattr(first_usage, "prompt_tokens", 0) or 0
            ct1 = getattr(first_usage, "completion_tokens", 0) or 0
            pt2 = getattr(usage, "prompt_tokens", 0) or 0
            ct2 = getattr(usage, "completion_tokens", 0) or 0
            prompt_tokens_val = pt1 + pt2
            completion_tokens_val = ct1 + ct2
            cost1 = _compute_cost_from_usage(selected_model, pt1, ct1)
            cost2 = _compute_cost_from_usage("gpt-5.4-mini", pt2, ct2)
            tokens_val = prompt_tokens_val + completion_tokens_val
            cost_info = {
                "input_cost_usd": round((cost1.get("input_cost_usd", 0) or 0) + (cost2.get("input_cost_usd", 0) or 0), 6),
                "output_cost_usd": round((cost1.get("output_cost_usd", 0) or 0) + (cost2.get("output_cost_usd", 0) or 0), 6),
                "cost_usd": round((cost1.get("cost_usd", 0) or 0) + (cost2.get("cost_usd", 0) or 0), 6),
            }
        else:
            tokens_val = (usage.total_tokens or (getattr(usage, "prompt_tokens", 0) or 0) + (getattr(usage, "completion_tokens", 0) or 0)) if usage else None
            prompt_tokens_val = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens_val = getattr(usage, "completion_tokens", None) if usage else None
            cost_info = _compute_cost_from_usage(selected_model, prompt_tokens_val or 0, completion_tokens_val or 0) if (prompt_tokens_val is not None or completion_tokens_val is not None) else {}
        flow_meta = {
            "model": selected_model,
            "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
            "ai_query_summary": flow_ai_query_summary,
            "bot_sent_to_ai": flow_bot_sent_to_ai_full,
            "customer_context_sent": flow_customer_context_sent,
            "tool_calls": tool_names if tool_names else None,
            "tokens": tokens_val,
            "prompt_tokens": prompt_tokens_val,
            "completion_tokens": completion_tokens_val,
            **cost_info,
        }
        if api_failure_reason:
            flow_meta["error"] = api_failure_reason
        if tool_calls and tool_round_trips:
            flow_meta["ai_first_response"] = ai_first_response_with_tools[:1500] if ai_first_response_with_tools else None
            flow_meta["tool_round_trips"] = tool_round_trips
        parsed_response["_flow_meta"] = flow_meta

        if cost_info:
            print(f"💰 GPT usage: input={prompt_tokens_val} tokens (${cost_info.get('input_cost_usd', 0):.6f}) | output={completion_tokens_val} tokens (${cost_info.get('output_cost_usd', 0):.6f}) | total=${cost_info.get('cost_usd', 0):.6f}")

        # ============================================================
        # PRICING: Use selector files only (no system API)
        # Prices come from ADDITIONAL RELEVANT CONTEXT (selector-retrieved files).
        # ============================================================
        _USE_SYSTEM_API_FOR_PRICING = False  # Set True to revert to get_pricing_details API
        if _USE_SYSTEM_API_FOR_PRICING and is_price_question:
            booking_state = config.user_booking_state[user_id]
            pricing_payload_to_send = latest_pricing_payload
            service_id_for_sync = _safe_int(booking_state.get("service_id"))
            if service_id_for_sync is None:
                inferred_service = _infer_service_id_for_pricing(user_input, current_gender, booking_state)
                if inferred_service is not None:
                    booking_state["service_id"] = inferred_service
                    service_id_for_sync = inferred_service

            if pricing_payload_to_send is None:
                selected_body_parts = _normalize_body_part_ids(booking_state.get("body_part_ids"))

                if service_id_for_sync is None:
                    parsed_response["action"] = "ask_for_details_for_booking"
                    parsed_response["bot_reply"] = _pricing_missing_details_reply(current_preferred_lang, "service")
                elif service_id_for_sync in body_part_required_service_ids and not selected_body_parts:
                    parsed_response["action"] = "ask_for_details_for_booking"
                    parsed_response["bot_reply"] = _pricing_missing_details_reply(current_preferred_lang, "body_part")
                else:
                    pricing_call_args = {"service_id": service_id_for_sync}
                    machine_id_for_sync = _safe_int(booking_state.get("machine_id"))
                    branch_id_for_sync = _safe_int(booking_state.get("branch_id"))
                    if machine_id_for_sync is not None:
                        pricing_call_args["machine_id"] = machine_id_for_sync
                    if selected_body_parts:
                        pricing_call_args["body_part_ids"] = selected_body_parts
                    if branch_id_for_sync is not None:
                        pricing_call_args["branch_id"] = branch_id_for_sync

                    try:
                        pricing_result = await api_integrations.get_pricing_details(**pricing_call_args)
                        if isinstance(pricing_result, dict) and pricing_result.get("success"):
                            pricing_payload_to_send = pricing_result.get("data")
                            booking_state["last_pricing_payload"] = pricing_payload_to_send
                            _remember_booking_selection(user_id, pricing_call_args)
                        else:
                            parsed_response["action"] = "ask_for_details_for_booking"
                            parsed_response["bot_reply"] = _pricing_missing_details_reply(current_preferred_lang, "unavailable")
                    except Exception as pricing_sync_error:
                        print(f"⚠️ Pricing sync fetch failed: {pricing_sync_error}")
                        parsed_response["action"] = "ask_for_details_for_booking"
                        parsed_response["bot_reply"] = _pricing_missing_details_reply(current_preferred_lang, "unavailable")

            if pricing_payload_to_send is not None:
                parsed_response["action"] = "answer_question"
                parsed_response["bot_reply"] = _build_exact_pricing_reply(
                    current_preferred_lang,
                    pricing_payload_to_send,
                )

        # AI-PRIMARY: Bot sends AI reply as-is. No language validation/rewrite.
        return parsed_response
    except json.JSONDecodeError as e:
        print(f"â‌Œ JSON Decode Error from GPT chat response: {e}. Raw content: {gpt_raw_content}")
        # NEW: Try to parse a potential plain text reply if JSON fails
        generic_error_by_lang = {
            "ar": "عذراً، صار خطأ تقني وأنا عم عالج طلبك. جرّب مرة ثانية بعد شوي أو تواصل معنا مباشرة.",
            "en": "Sorry, I encountered a technical issue while understanding your request. Please try again shortly or contact our staff directly.",
            "fr": "Désolé, j'ai rencontré un problème technique en traitant votre demande. Veuillez réessayer dans un instant ou contacter notre équipe.",
            "franco": "عذراً، صار خطأ تقني وأنا عم عالج طلبك. جرّب مرة ثانية بعد شوي أو تواصل معنا مباشرة.",
        }
        fallback_bot_reply = (
            gpt_raw_content
            if gpt_raw_content
            else generic_error_by_lang.get(current_preferred_lang, generic_error_by_lang["en"])
        )
        return {
            "action": "unknown_query", 
            "bot_reply": fallback_bot_reply, 
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender, # Pass the actual gender from config
            "_flow_meta": {
                "model": selected_model,
                "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
                "ai_query_summary": flow_ai_query_summary,
                "bot_sent_to_ai": flow_bot_sent_to_ai_full,
                "customer_context_sent": flow_customer_context_sent,
                "error": f"json_decode_error: {e}",
            },
        }
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ ERROR in get_bot_chat_response from GPT: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"   Full traceback:")
        traceback.print_exc()
        print(f"{'='*80}\n")
        generic_error_by_lang = {
            "ar": "عذراً، صار خطأ وأنا عم عالج طلبك حالياً. جرّب مرة ثانية أو تواصل معنا مباشرة.",
            "en": "Sorry, I encountered an issue understanding your request at the moment. Please try again or contact our staff directly.",
            "fr": "Désolé, j'ai rencontré un problème en traitant votre demande. Veuillez réessayer ou contacter notre équipe.",
            "franco": "عذراً، صار خطأ وأنا عم عالج طلبك حالياً. جرّب مرة ثانية أو تواصل معنا مباشرة.",
        }
        return {
            "action": "unknown_query",
            "bot_reply": generic_error_by_lang.get(current_preferred_lang, generic_error_by_lang["en"]),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender, # Pass the actual gender from config
            "_flow_meta": {
                "model": selected_model,
                "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
                "ai_query_summary": flow_ai_query_summary,
                "bot_sent_to_ai": flow_bot_sent_to_ai_full,
                "customer_context_sent": flow_customer_context_sent,
                "error": f"{type(e).__name__}: {e}",
            },
        }