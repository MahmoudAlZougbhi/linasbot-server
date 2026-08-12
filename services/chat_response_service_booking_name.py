"""Legacy GPT chat-response helpers group 7."""

from __future__ import annotations

import datetime
import re
from typing import Any

from services import api_integrations
from services.booking.resolver import match_best_body_part_row, server_may_infer_body_parts
from services.chat_response_service_booking_resolve import _resolve_body_part_ids_from_area_hint
from services.chat_response_service_constants import (
    _SUBMIT_BOOKING_TOOL_HINT_CRM_REJECT,
    _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    _normalize_body_part_ids,
    _safe_int,
)
from services.chat_response_service_gpt_parse import (
    _extract_latin_name_from_franco_booking_bundle,
    _is_placeholder_booking_customer_name,
)
from utils.datetime_utils import (
    parse_datetime_flexible,
    to_bot_tz,
)


def _extract_customer_name_from_conversation_for_booking(
    user_id: str,
    current_context_messages: list[dict] | None,
    user_input: str,
) -> str | None:
    """
    Same heuristics as create_appointment tool path (conversation scan).
    Returns None if no usable Latin / structured name found.
    """
    bundle_name = _extract_latin_name_from_franco_booking_bundle(user_input or "")
    if bundle_name:
        return bundle_name

    customer_name = None
    ctx = list(current_context_messages or [])
    for msg_entry in reversed(ctx + [{"role": "user", "content": user_input}]):
        msg_content = (msg_entry.get("content") or "").strip()
        msg_role = msg_entry.get("role")
        if not msg_content:
            continue

        if msg_role == "user":
            name_match = re.search(
                r"(?:my name is|i am|i'm|call me|انا اسمي|اسمي|اسمي هو|je\s*m['\s]?appelle|je suis|moi c'est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
                msg_content,
                re.IGNORECASE | re.UNICODE,
            )
            if name_match:
                potential_name = name_match.group(1).strip()
                booking_keywords = [
                    "book",
                    "appointment",
                    "schedule",
                    "reserve",
                    "موعد",
                    "حجز",
                    "want",
                    "need",
                    "like",
                    "please",
                    "tomorrow",
                    "today",
                    "بدي",
                    "بحب",
                    "just",
                    "an",
                    "the",
                    "a",
                    "have",
                    "get",
                ]
                if not any(keyword in potential_name.lower() for keyword in booking_keywords):
                    customer_name = potential_name
                    break

        elif msg_role == "assistant":
            name_match = re.search(
                r"(?:your name is|you are|you\'re called|اسمك|اسمك هو|ton nom est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
                msg_content,
                re.IGNORECASE | re.UNICODE,
            )
            if name_match:
                potential_name = name_match.group(1).strip()
                potential_name = re.sub(r"\s+(and|et|و|،|,|\.).*$", "", potential_name, flags=re.IGNORECASE)
                if 2 <= len(potential_name) <= 50:
                    customer_name = potential_name
                    break

        elif msg_role == "user" and not customer_name:
            words = msg_content.split()
            if 1 <= len(words) <= 4:
                if re.match(r"^[A-ZÀ-Ÿا-ي]", msg_content, re.UNICODE) and re.match(
                    r"^[A-Za-zÀ-ÿا-ي\s\-\']+$", msg_content, re.UNICODE
                ):
                    excluded_words = [
                        "yes",
                        "no",
                        "ok",
                        "okay",
                        "sure",
                        "please",
                        "thanks",
                        "hello",
                        "hi",
                        "book",
                        "appointment",
                        "schedule",
                        "tomorrow",
                        "today",
                        "now",
                        "نعم",
                        "لا",
                        "تمام",
                        "ماشي",
                        "شكرا",
                        "مرحبا",
                        "موعد",
                        "حجز",
                        "oui",
                        "non",
                        "merci",
                        "bonjour",
                        "salut",
                    ]
                    if msg_content.lower() not in excluded_words:
                        asking_for_name = False
                        for prev_msg in reversed(ctx):
                            if prev_msg.get("role") == "assistant":
                                prev_content = str(prev_msg.get("content") or "").lower()
                                if any(
                                    phrase in prev_content
                                    for phrase in [
                                        "your name",
                                        "full name",
                                        "what is your name",
                                        "may i have your name",
                                        "اسمك",
                                        "ما اسمك",
                                        "شو اسمك",
                                        "votre nom",
                                        "ton nom",
                                        "quel est votre nom",
                                    ]
                                ):
                                    asking_for_name = True
                                    break
                            if prev_msg.get("role") == "assistant":
                                break
                        if asking_for_name:
                            customer_name = msg_content.strip()
                            break

        if customer_name:
            break

    if customer_name and re.search(r"[\u0600-\u06FF]", customer_name):
        return None
    if _is_placeholder_booking_customer_name(customer_name):
        return None
    return customer_name


async def _recovery_map_body_part_label_to_ids(
    service_id: int,
    machine_id: int | None,
    label: str,
) -> list[int] | None:
    """
    Auxiliary-JSON recovery only: GPT often sends body_part (e.g. mo25rah) but omits body_part_ids.
    Map via live get_body_parts + match_best_body_part_row. Independent of BOOKING_LEGACY_INFERENCE.
    """
    lab = (label or "").strip()
    if not lab:
        return None
    sid = _safe_int(service_id)
    if sid is None or sid not in LASER_HAIR_REMOVAL_SERVICE_IDS:
        return None
    r = await api_integrations.get_body_parts(service_id=sid, machine_id=machine_id)
    if not r.get("success"):
        return None
    raw = r.get("data")
    rows: list[dict] = []
    if isinstance(raw, list):
        rows = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, dict):
        inner = raw.get("data")
        if isinstance(inner, list):
            rows = [x for x in inner if isinstance(x, dict)]
    if not rows:
        return None
    bid = match_best_body_part_row(rows, lab)
    if bid is None:
        return None
    return [bid]


async def _try_recover_create_appointment_from_auxiliary_gpt_json(
    gpt_raw_content: str,
    *,
    user_id: str,
    customer_phone_clean: str | None,
    current_gender: str,
    current_preferred_lang: str,
    current_context_messages: list[dict] | None,
    user_input: str,
    body_part_required_service_ids: set,
    is_reschedule_intent: bool,
    tool_names_so_far: list[str],
) -> dict | None:
    """
    Legacy recovery disabled by architecture decision:
    booking understanding + official-ID resolution belong to the AI/tooling layer,
    while the backend only validates and executes canonical payloads.
    """
    return None


async def _coerce_body_part_ids_from_gpt_booking_args(
    booking_args: dict, service_id: int, machine_id: int | None = None
) -> list[int] | None:
    """
    GPT sometimes emits body_part_ids as a list of objects, e.g.
    [{"body_part": "dahreh", "session_number": 1}] — normalize to integer IDs for the API.
    Also accepts body_parts with string slug id, e.g. [{"id": "hands", "session_number": 1}].
    """
    raw = None
    if booking_args:
        raw = booking_args.get("body_part_ids")
        if raw is None:
            raw = booking_args.get("body_parts")
    if raw is None or not isinstance(raw, list):
        return None
    out: list[int] = []
    for item in raw:
        if item is None:
            continue
        if isinstance(item, int):
            iid = _safe_int(item)
            if iid is not None and iid > 0:
                out.append(iid)
        elif isinstance(item, dict):
            _raw_id = item.get("id")
            iid = _safe_int(item.get("body_part_id") or _raw_id)
            if iid is not None and iid > 0:
                out.append(iid)
                continue
            area = item.get("body_part") or item.get("name") or item.get("area")
            if not area and isinstance(_raw_id, str) and _raw_id.strip() and not str(_raw_id).strip().isdigit():
                area = str(_raw_id).strip()
            if area:
                if server_may_infer_body_parts():
                    resolved = await _resolve_body_part_ids_from_area_hint(str(area), service_id, machine_id)
                    if resolved:
                        out.extend(resolved)
    normalized = _normalize_body_part_ids(out)
    return normalized if normalized else None


def _sanitize_submit_booking_tool_for_model(tool_output: dict[str, Any]) -> dict[str, Any]:
    """
    Strip internal/technical strings from tool JSON before sending to the model so the assistant
    does not echo full exceptions or CRM payloads to the user.
    """
    if not isinstance(tool_output, dict):
        return tool_output
    out = dict(tool_output)
    if out.get("crm_rejection"):
        out["human_readable_reason"] = _SUBMIT_BOOKING_TOOL_HINT_CRM_REJECT
        if isinstance(out.get("api_response"), dict):
            ar = out["api_response"]
            out["api_response"] = {
                "success": ar.get("success"),
                "message": "(redacted for user-facing channel; use human_readable_reason only)",
            }
    elif out.get("error_type") == "submit_exception":
        out["human_readable_reason"] = _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL
    return out


def _missing_body_part_booking_prompt(service_id: int | None, lang: str) -> str:
    """Ask for body area in wording that matches the service (tattoo vs hair vs other)."""
    sid = _safe_int(service_id)
    if sid in LASER_HAIR_REMOVAL_SERVICE_IDS:
        ar = (
            "كرمال نثبّت الموعد على السيستم، لازم نحدّد منطقة الجسم بنفس الاسم اللي بالقائمة "
            "(مثلاً: إبط، ظهر، وجه…). ما في داعي لرقم تقني من عندك — إذا حابب، قلّي المنطقة بالعربي أو الفرانكو "
            "وبقلّك الاسم الظاهر بالنظام، أو منقدر نمرّق على الخيارات سوا."
        )
        en = "To save the appointment on the system, I need to know which body area(s) you want (e.g. full body, legs, bikini, face...)."
        fr = "Pour enregistrer le rendez-vous, j’ai besoin de savoir quelle(s) zone(s) du corps (ex. corps entier, jambes, maillot, visage...)."
    elif sid == 13:
        ar = (
            "كرمال نثبّت موعد إزالة الوشم على السيستم، لازم نعرف مكان الوشم بالجسم تقريباً "
            "(مثلاً: معصم، ذراع، ظهر، رقبة…) وأبعاده تقريباً بالسنتيمتر (العرض × الارتفاع)."
        )
        en = (
            "To book laser tattoo removal, I need the body area (e.g. wrist, arm, back, neck) and "
            "the approximate size in cm (width × height)."
        )
        fr = (
            "Pour réserver le détatouage au laser, j’ai besoin de la zone du corps "
            "et de la taille approximative en cm (largeur × hauteur)."
        )
    elif sid in (2, 11):
        ar = "كرمال نثبّت الموعد على السيستم، لازم نعرف أي منطقة بالجسم بدّك نعالجها بالليزر (مثلاً: وجه، بطن، منطقة التمدد...)."
        en = "To save the appointment, I need to know which body area to treat with the laser (e.g. face, abdomen, stretch-mark area...)."
        fr = "Pour enregistrer le rendez-vous, j’ai besoin de la zone du corps à traiter au laser (ex. visage, abdomen, vergetures...)."
    elif sid in (4, 5, 14):
        ar = "كرمال نثبّت الموعد على السيستم، لازم نعرف أي منطقة بالجسم بدّك تفتيحها (مثلاً: إبط، ركبة، أكواع...)."
        en = "To save the appointment, I need to know which body area you want to lighten (e.g. underarms, knees, elbows...)."
        fr = "Pour enregistrer le rendez-vous, j’ai besoin de la zone à éclaircir (ex. aisselles, genoux, coudes...)."
    else:
        ar = "كرمال نثبّت الموعد على السيستم، لازم نعرف أي منطقة بالجسم نخصّصها للموعد."
        en = "To save the appointment, I need to know which body area to book."
        fr = "Pour enregistrer le rendez-vous, j’ai besoin de la zone du corps concernée."
    if lang == "fr":
        return fr
    if lang in ("ar", "franco"):
        return ar
    return en


def _service_hint_to_service_id(val: Any) -> int | None:
    if val is None:
        return None
    sid = _safe_int(val)
    if sid is not None:
        return sid
    s = str(val).strip().lower()
    if any(x in s for x in ("tattoo", "وشم", "تاتو", "détatouage")):
        return 13
    if any(x in s for x in ("whiten", "dpl", "تبييض", "تفتيح", "blanch")):
        return 4
    if any(x in s for x in ("co2", "scar", "stretch", "ندوب", "ندبة")):
        return 2
    return None


def _branch_hint_to_branch_id(val: Any) -> int | None:
    if val is None:
        return None
    bid = _safe_int(val)
    if bid is not None:
        return bid
    s = str(val).strip().lower()
    if any(x in s for x in ("beirut", "بيروت", "beyrouth", "manara")):
        return 1
    if any(x in s for x in ("antelias", "أنطلياس", "انطلياس")):
        return 2
    return None


def _datetime_from_gpt_booking_args(booking_args: dict) -> datetime.datetime | None:
    """Build an aware datetime from GPT-emitted date + optional time fields."""
    if not booking_args:
        return None
    d = booking_args.get("date")
    if d is None or not str(d).strip():
        return None
    ds = str(d).strip()
    t = booking_args.get("time")
    if t is not None and str(t).strip() != "":
        ts = str(t).strip()
        if ":" in ts:
            combined = f"{ds} {ts}" if len(ts) >= 8 else f"{ds} {ts}:00"
        elif ts.isdigit():
            h = int(ts)
            combined = f"{ds} {h:02d}:00:00"
        else:
            combined = f"{ds} {ts}"
    else:
        combined = ds
    parsed = parse_datetime_flexible(combined)
    if parsed is None:
        return None
    return to_bot_tz(parsed)
