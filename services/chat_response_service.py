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
from typing import Any, Dict, List, Optional, Tuple

# Import all API functions from api_integrations
from services import api_integrations
from services.booking.resolver import match_best_body_part_row, server_may_infer_body_parts
from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
    detect_existing_appointment_edit_intent,
    datetime_from_ai_date_components,
    detect_appointment_inquiry_intent,
    detect_bulk_reschedule_all_intent,
    detect_last_weekday_intent_from_user_text,
    detect_reschedule_intent,
    format_clinic_calendar_anchor,
    next_future_datetime_matching_weekday,
    now_in_bot_tz,
    parse_datetime_flexible,
    to_bot_tz,
)
from utils.appointment_slot_rules import (
    extract_appointment_booking_fields,
    find_appointment_row_in_check_next_payload,
    parse_normalized_api_datetime,
    validate_booking_slot,
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

ORCHESTRATION_MODEL = "gpt-5.1"
FINAL_RESPONSE_MODEL = "gpt-5.4-mini"


def _compute_cost_from_usage(model: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Compute input_cost_usd, output_cost_usd, cost_usd from token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-5.1", {"input": 1.25, "output": 10.0}))
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    input_cost = (pt / 1_000_000) * pricing["input"]
    output_cost = (ct / 1_000_000) * pricing["output"]
    return {"input_cost_usd": round(input_cost, 6), "output_cost_usd": round(output_cost, 6), "cost_usd": round(input_cost + output_cost, 6)}


_TOOL_ROUND_ARGS_MAX = 48_000
_TOOL_ROUND_RESPONSE_MAX = 48_000


def _record_tool_round_trip(
    function_name: str,
    function_args: Any,
    tool_content: str,
    parsed_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Activity-flow record: full JSON args + backend response for dashboard (no 300-char clip).
    Adds backend_execution summary when tool returns structured booking/validation JSON.
    """
    try:
        args_str = json.dumps(function_args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        args_str = str(function_args)
    if len(args_str) > _TOOL_ROUND_ARGS_MAX:
        args_str = args_str[:_TOOL_ROUND_ARGS_MAX] + "…[truncated]"
    out = tool_content or ""
    if len(out) > _TOOL_ROUND_RESPONSE_MAX:
        out = out[:_TOOL_ROUND_RESPONSE_MAX] + "…[truncated]"
    rec: Dict[str, Any] = {
        "ai_requested": function_name,
        "args": args_str,
        "bot_returned": out,
    }
    po = parsed_output
    if po is None and out:
        try:
            po = json.loads(out)
        except (json.JSONDecodeError, TypeError):
            po = None
    if isinstance(po, dict):
        summ = {
            "success": po.get("success"),
            "error_type": po.get("error_type"),
            "code": po.get("code"),
            "status": po.get("status"),
            "repair_attempt": po.get("repair_attempt"),
            "max_repair_attempts": po.get("max_repair_attempts"),
            "booking_flow_state": po.get("booking_flow_state"),
            "handover_to_human": po.get("handover_to_human"),
            "handover_reason": po.get("handover_reason"),
            "missing_fields": po.get("missing_fields"),
            "invalid_fields": po.get("invalid_fields"),
            "conflicting_fields": po.get("conflicting_fields"),
            "human_readable_reason": po.get("human_readable_reason"),
            "message": po.get("message"),
            "activity_trace": po.get("activity_trace"),
            "slot_validation": po.get("slot_validation"),
            "crm_rejection": po.get("crm_rejection"),
            "ambiguities": po.get("ambiguities"),
        }
        ar = po.get("api_response")
        if isinstance(ar, dict) and ar:
            msg = ar.get("message")
            summ["api_response_summary"] = {
                "success": ar.get("success"),
                "message": (str(msg)[:4000] if msg is not None else None),
            }
        rec["backend_execution"] = {k: v for k, v in summ.items() if v is not None}
    return rec


def _clinic_holiday_calendar_block(user_id: str, current_local_time: datetime.datetime) -> str:
    """Inject branch holiday / closure rules from dashboard Settings into the system prompt."""
    try:
        from services.clinic_holidays_service import build_clinic_holiday_block_for_prompt

        return build_clinic_holiday_block_for_prompt(user_id, current_local_time)
    except Exception as e:
        print(f"WARNING: clinic holiday block: {e}")
        return ""


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


def _extract_appointment_id_from_check_response(response: dict) -> Optional[int]:
    """Extract appointment_id from check_next_appointment API response."""
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        apt = data.get("appointment")
        if isinstance(apt, dict):
            for key in ("appointment_id", "id", "appointmentId"):
                v = apt.get(key)
                if v is not None:
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        pass
        for key in ("appointment_id", "id", "appointmentId"):
            v = data.get(key)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
    return None


def _extract_customer_appointments_list(response_payload: dict) -> list:
    """Normalize get_customer_appointments API payload to a list of appointment dicts."""
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
        for key in ("appointment_id", "id", "appointmentId"):
            if data.get(key) is not None:
                return [data]
    return []


_EXCLUDED_RESCHEDULE_SUMMARY_STATUSES = frozenset(
    {"done", "completed", "cancelled", "canceled", "missed", "no_show", "noshow"}
)

_PAUSED_LIKE_STATUS_NORMALIZED = frozenset(
    {
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
)


def _normalize_appointment_status_token(status_val: str) -> str:
    return str(status_val or "").strip().lower().replace("_", " ").replace("-", " ")


def _is_paused_like_appointment_status(status_val: str) -> bool:
    """True when CRM row is paused/on-hold/postponed (not the same as Available/active)."""
    return _normalize_appointment_status_token(status_val) in _PAUSED_LIKE_STATUS_NORMALIZED


def _appointment_row_status_lower(apt: dict) -> str:
    return str(apt.get("status") or "").strip().lower()


def _reschedule_row_kind_tag(apt: dict) -> str:
    st = str(apt.get("status") or "")
    if _is_paused_like_appointment_status(st):
        return "PAUSED"
    sl = _appointment_row_status_lower(apt)
    if sl == "available" or sl.startswith("available"):
        return "AVAILABLE"
    return "ACTIVE"


def _filter_appointments_for_reschedule_overview(appointments: List[dict]) -> List[dict]:
    """Prefer rows that are not clearly finished/cancelled when listing choices for reschedule."""
    kept = [a for a in appointments if _appointment_row_status_lower(a) not in _EXCLUDED_RESCHEDULE_SUMMARY_STATUSES]
    return kept if len(kept) >= 2 else list(appointments)


def _format_appointment_row_for_reschedule_hint(idx: int, apt: dict) -> str:
    """One CRM row for prompts: emphasize appointment_id + service/branch/datetime/machine/areas/price from JSON only."""
    aid = apt.get("appointment_id") or apt.get("id") or apt.get("appointmentId")
    d0 = apt.get("date") or apt.get("appointment_date") or apt.get("start_date") or ""
    t0 = apt.get("time") or apt.get("start_time") or apt.get("appointment_time") or ""
    svc = apt.get("service") or apt.get("service_name") or ""
    if isinstance(svc, dict):
        svc = (svc.get("name") or svc.get("title") or "").strip()
    br = apt.get("branch") or apt.get("branch_name") or ""
    if isinstance(br, dict):
        br = (br.get("name") or "").strip()
    st = apt.get("status") or ""
    mach = apt.get("machine") or apt.get("machine_name") or ""
    if isinstance(mach, dict):
        mach = (mach.get("name") or mach.get("title") or "").strip()
    bits: List[str] = []
    if aid is not None:
        bits.append(f"appointment_id={aid}")
    else:
        bits.append(f"line={idx}")
    if d0:
        bits.append(f"date={d0}")
    if t0:
        bits.append(f"time={t0}")
    if svc:
        bits.append(f"service={svc}")
    if br:
        bits.append(f"branch={br}")
    if mach:
        bits.append(f"machine={mach}")

    bp_raw = apt.get("body_parts") or apt.get("areas") or apt.get("body_part")
    area_labels: List[str] = []
    if isinstance(bp_raw, list):
        for it in bp_raw[:8]:
            if isinstance(it, dict):
                nm = it.get("name") or it.get("body_part") or it.get("title") or it.get("part")
                if nm:
                    area_labels.append(str(nm).strip())
            elif it is not None:
                s = str(it).strip()
                if s:
                    area_labels.append(s)
    elif isinstance(bp_raw, str) and bp_raw.strip():
        area_labels.append(bp_raw.strip())
    if area_labels:
        bits.append("areas=" + ", ".join(area_labels[:6]))

    price_set = False
    for pk in ("total", "price", "amount"):
        v = apt.get(pk)
        if v is not None and str(v).strip():
            bits.append(f"{pk}={v}")
            price_set = True
            break
    if not price_set:
        pr = apt.get("pricing")
        if isinstance(pr, dict):
            for pk in ("total", "price", "amount"):
                v = pr.get(pk)
                if v is not None and str(v).strip():
                    bits.append(f"pricing.{pk}={v}")
                    break

    if st:
        bits.append(f"status={st}")
    return f"{idx}. [{_reschedule_row_kind_tag(apt)}] " + " | ".join(bits)


async def _build_multi_appointment_reschedule_hint(phone_clean: str) -> str:
    """
    If the customer has 2+ appointment rows and asks to reschedule, give the model a concrete list
    so it asks which slot to move instead of guessing.
    """
    if not phone_clean or not str(phone_clean).strip():
        return ""
    try:
        resp = await api_integrations.get_customer_appointments(phone=phone_clean)
    except Exception as ex:
        print(f"WARNING: get_customer_appointments for reschedule hint failed: {ex}")
        return ""
    if not isinstance(resp, dict) or not resp.get("success"):
        return ""
    raw = _extract_customer_appointments_list(resp)
    if len(raw) < 2:
        return ""
    rows = _filter_appointments_for_reschedule_overview(raw)
    if len(rows) < 2:
        rows = raw
    max_lines = 10
    lines = [_format_appointment_row_for_reschedule_hint(i + 1, rows[i]) for i in range(min(len(rows), max_lines))]
    if len(rows) > max_lines:
        lines.append(f"... +{len(rows) - max_lines} more in system")
    body = "\n".join(f"  - {ln}" for ln in lines)
    has_paused = any(_is_paused_like_appointment_status(str(a.get("status") or "")) for a in rows)
    has_non_paused = any(
        not _is_paused_like_appointment_status(str(a.get("status") or ""))
        and _appointment_row_status_lower(a) not in _EXCLUDED_RESCHEDULE_SUMMARY_STATUSES
        for a in rows
    )
    mixed_pause_and_active = has_paused and has_non_paused
    mix_block = ""
    if mixed_pause_and_active:
        mix_block = (
            "\n**⏸️ PAUSED vs ✅ AVAILABLE/ACTIVE (same customer):**\n"
            "- They have **both** paused/on-hold rows and **Available/active** upcoming rows—often **different services**. "
            "You MUST confirm **which row** they mean — **prefer asking for `appointment_id` (رقم الموعد في النظام)** shown on each line, or line number 1/2/3 matching your list — before any reschedule tool.\n"
            "- **FORBIDDEN:** Do **NOT** call **`pause_appointment`** to «تأجيل» or move to another day—that tool only **puts** a slot on hold without a new calendar time. "
            "**Postpone / new day / إخراج من البوز بتاريخ جديد** = **`update_appointment_date`** with structured `date` (+ `calendar_day_intent` / `date_components` when needed) on the correct `appointment_id`.\n"
            "- **PAUSED row:** Take the new date/time then call **`update_appointment_date`** on **that paused row's id**. The server may also call the CRM **resume** endpoint after a successful date update so status becomes **Available**—check tool JSON `resume_appointment` (success vs failed vs skipped). In `bot_reply`, if resume succeeded, say the موعد صار فعّال/متاح بالوقت الجديد; if resume failed or skipped but date update succeeded, say الوقت اتعدّل وإذا لسا ظاهر موقوف يتأكد الاستقبال.\n"
            "- **Resume without changing date/time:** If the user only wants the paused row back as active/Available at the **same slot**, call **`resume_appointment`** on that paused row's id.\n"
            "- **AVAILABLE / ACTIVE row:** Normal upcoming booking—reschedule only with **`update_appointment_date`**.\n"
        )
    return (
        "\n**🔁 MULTIPLE APPOINTMENTS ON FILE (reschedule — do not guess):**\n"
        f"This customer has **at least {len(rows)}** relevant appointment row(s). Tags: [PAUSED] vs [AVAILABLE]/[ACTIVE]. Lines:\n{body}\n"
        f"{mix_block}"
        "- If the latest user message does **not** clearly identify **which** appointment to move, list **each row on its own line** with: "
        "**`appointment_id`**, date/time, service, branch, machine/device, body areas/parts, **price/total only if present in JSON** (never invent prices), status. "
        "Then ask **one** question: e.g. «ابعتلي رقم الموعد (appointment_id) اللي بدك ترجّعو/تعدّلو» or Franco «ابعتيلي الـ id تبع الموعد» — they may also answer with the **line number** (1/2/3) matching your list.\n"
        "- After they specify the **`appointment_id`** (or the line number maps to that id), call **`update_appointment_date`** with that **`appointment_id`**, structured **`date`** (and phone). Pass the same facts the user confirmed; **never** assume «the next appointment» or pick arbitrarily.\n"
        "- **Never** use **`pause_appointment`** as a shortcut for postponing; only if they explicitly ask to **hold without a new date**.\n"
    )


async def _build_live_crm_appointments_snapshot(phone_clean: str) -> str:
    """
    Inject current get_customer_appointments rows into the system prompt so listing answers
    (emtan mw3de, paused slots, etc.) cannot be invented or merged from chat memory.
    """
    if not phone_clean or not str(phone_clean).strip():
        return ""
    try:
        resp = await api_integrations.get_customer_appointments(phone=phone_clean)
    except Exception as ex:
        print(f"WARNING: live CRM snapshot get_customer_appointments failed: {ex}")
        return (
            "\n\n**LIVE CRM APPOINTMENT SNAPSHOT:** unavailable (API error). "
            "You MUST still call `check_next_appointment` this turn; do not list appointments from memory alone.\n"
        )
    if not isinstance(resp, dict) or not resp.get("success"):
        return (
            "\n\n**LIVE CRM APPOINTMENT SNAPSHOT:** API returned unsuccessful. "
            "You MUST call `check_next_appointment` this turn; do not invent rows.\n"
        )
    raw = _extract_customer_appointments_list(resp)
    if not raw:
        return (
            "\n\n**LIVE CRM APPOINTMENT SNAPSHOT:** empty — no rows for this phone on this endpoint. "
            "Still call `check_next_appointment` once; answer honestly if still empty.\n"
        )
    rows = _filter_appointments_for_reschedule_overview(raw)
    if not rows:
        rows = raw[:30]
    max_lines = 25
    display = rows[:max_lines]
    lines = [_format_appointment_row_for_reschedule_hint(i + 1, display[i]) for i in range(len(display))]
    body = "\n".join(f"  - {ln}" for ln in lines)
    more = ""
    if len(rows) > max_lines:
        more = f"\n  - ... +{len(rows) - max_lines} more row(s) truncated here — call `check_next_appointment` for full tool JSON.\n"
    return (
        "\n\n**LIVE CRM APPOINTMENT SNAPSHOT (authoritative for this request):**\n"
        f"- **Listed row count: {len(display)}** (of {len(rows)} relevant). "
        "Your `bot_reply` must use **one bullet per row below** — same count; do not merge several `appointment_id`s into one line. "
        "Each line must include **`appointment_id`** plus service, branch, date/time, machine, areas, price (only if shown below).\n"
        f"{body}{more}"
        "- Also call `check_next_appointment` when rules require it; if tool JSON disagrees, prefer the **tool** result.\n"
    )


async def _count_live_reschedule_row_total(phone_clean: str) -> int:
    """How many CRM rows we surface for reschedule/listing (same filter as LIVE snapshot)."""
    if not phone_clean or not str(phone_clean).strip():
        return 0
    try:
        resp = await api_integrations.get_customer_appointments(phone=phone_clean)
    except Exception:
        return 0
    if not isinstance(resp, dict) or not resp.get("success"):
        return 0
    raw = _extract_customer_appointments_list(resp)
    if not raw:
        return 0
    rows = _filter_appointments_for_reschedule_overview(raw)
    if not rows:
        rows = raw[:50]
    return len(rows)


def _bot_reply_claims_bulk_all_appointments_updated(bot_reply: str) -> bool:
    """Model implies every appointment row was updated (common hallucination after bulk user ask)."""
    br = (bot_reply or "").strip()
    if not br:
        return False
    if "تم تعديل كل" in br or "تمّ تعديل كل" in br:
        return True
    if "كل المواعيد" in br and any(x in br for x in ("تم تعديل", "تمّ تعديل", "صاروا", "صارت", "تم نقل", "نقلت")):
        return True
    if "كلهم" in br and any(x in br for x in ("تم تعديل", "تمّ تعديل", "صاروا", "صارت", "تم نقل", "نقلت", "صار")):
        return True
    if "السبعة" in br and ("تم تعديل" in br or "تمّ تعديل" in br):
        return True
    if "مواعيدك صاروا كلهم" in br or "موعداتك صاروا كلهم" in br:
        return True
    if "صاروا كلهم" in br or "كلهم صاروا" in br:
        return True
    return False


def _user_message_is_acknowledgment_only(text: str) -> bool:
    """True for ok/تمام/yes and similar short replies that cannot carry new booking args."""
    raw = (text or "").strip()
    if not raw:
        return True
    t = raw.lower()
    t = re.sub(r"[^\w\s\u0600-\u06FF]", "", t).strip()
    if not t:
        return True
    ack = {
        "ok",
        "okay",
        "oki",
        "oke",
        "oky",
        "kk",
        "k",
        "yes",
        "yeah",
        "yep",
        "ya",
        "sure",
        "fine",
        "deal",
        "alright",
        "tamam",
        "تمام",
        "mashi",
        "mashy",
        "mashe",
        "mache",
        "naam",
        "نعم",
        "na3am",
        "eh",
        "eih",
        "ay",
        "اي",
        "ايه",
        "ah",
        "ahh",
        "تم",
        "حسنا",
        "حسناً",
        "طيب",
        "ماشي",
        "اوكي",
        "merci",
        "thanks",
        "thankyou",
        "thx",
    }
    if t in ack:
        return True
    t_spaced = " ".join(t.split())
    if t_spaced in {"go ahead", "no problem", "all good", "sounds good"}:
        return True
    if len(t) <= 3 and t in {"ok", "kk", "k", "تم", "اي", "eh"}:
        return True
    return False


def _operational_context_promises_imminent_appointment_update(ctx: Optional[str]) -> bool:
    """Last bot line said it will update/reschedule (but tools may not have run yet)."""
    if not ctx or not str(ctx).strip():
        return False
    c = str(ctx)
    c_low = c.lower()
    needles_ar = (
        "رح أعدّل",
        "رح اعدل",
        "رح أعدل",
        "رح نعدّل",
        "سأعدّل",
        "سوف أعدّل",
        "رح أغيّر",
        "رح اغير",
        "رح غيّر",
        "رح بدّل",
        "رح ضيف",
        "رح شيل",
    )
    needles_en = (
        "will update your appointment",
        "will reschedule",
        "i will move your appointment",
        "going to update your appointment",
        "will edit your appointment",
        "will change the machine",
        "will update the body parts",
    )
    return any(n in c for n in needles_ar) or any(n in c_low for n in needles_en)


def _user_intent_resume_paused_appointment(user_text: str) -> bool:
    """True when the user is trying to re-activate a paused row / set a new date on paused (not move an active slot)."""
    t = (user_text or "").strip().lower()
    if not t:
        return False
    if re.search(
        r"موقوف|موقف|الموقوف|المعلّق|المعلق|من\s*البوز|البوز|طلع.*موقوف|شيل.*موقوف|فك.*موقوف|"
        r"إخراج.*موقوف|رجع.*موعد|ارجع.*موعد|يرجع.*موعد|رجع.*يجي.*(?:على|ع)\s*موعد|"
        r"يرجع.*يجي.*(?:على|ع)\s*موعد|كمّل.*جلس|كمل.*جلس|كمّل.*موعد|كمل.*موعد|تكمل",
        t,
        re.I,
    ):
        return True
    if re.search(
        r"\b(pause|paused|mw2of|mwouf|mwou2af|boz)\b.*(\bmw3ad|appointment)|"
        r"(\bmw3ad|appointment).*\b(pause|paused|mw2of|boz)\b|"
        r"\b(kmel|kammel|kml)\b.*(\bmw3ad|pause|boz|mw2of)|"
        r"\b(rod|rj3|rje3)\b.*(\bavailable|\bavail|\bmw3ad)|"
        r"\b(available|avail)\b.*(\bboz|\bpause|mw2of)|"
        r"\b(rj3|rje3|rja3)\b.{0,10}\b(yje|yeje|iji|yiji|ji)\b.{0,20}\b(3a|3al|aal|al)\b.{0,8}\b(mw3ad|maw3ad|mou3ad)\b",
        t,
        re.I,
    ):
        return True
    return False


def _bot_reply_claims_pause_lifted_or_resumed(bot_reply: str) -> bool:
    """bot_reply asserts the paused appointment was cleared / re-scheduled / became active."""
    br = (bot_reply or "").strip().lower()
    if not br:
        return False
    needles = (
        "انشال من البوز",
        "طلعنا من البوز",
        "طلع من البوز",
        "شلنا من البوز",
        "شيلنا من البوز",
        "مو بقى موقوف",
        "ما بقى موقوف",
        "رجّعنا الموعد",
        "رجعنا الموعد",
        "صار موعدك متاح",
        "خلص من الموقوف",
        "no longer paused",
        "lifted from pause",
        "removed from pause",
        "reactivated your appointment",
    )
    if any(n in br for n in needles):
        return True
    if ("تم" in br or "تمّ" in br) and ("موقوف" in br or "البوز" in br or "paused" in br):
        return True
    if "available" in br and ("pause" in br or "paused" in br or "موقوف" in br):
        return True
    return False


def _arabic_indic_digits_to_ascii(text: str) -> str:
    if not text:
        return ""
    return text.translate(
        str.maketrans(
            "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
            "01234567890123456789",
        )
    )


def _appointment_numeric_id(apt: Optional[dict]) -> Optional[int]:
    if not isinstance(apt, dict):
        return None
    for key in ("appointment_id", "id", "appointmentId"):
        v = apt.get(key)
        if v is None or v == "":
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _customer_appointments_embedded_in_payload(payload: dict) -> List[dict]:
    """check_next_appointment enriched shape: data.customer_appointments."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        ca = data.get("customer_appointments")
        if isinstance(ca, list) and ca:
            return [x for x in ca if isinstance(x, dict)]
    return []


def _ordered_paused_appointments_from_snapshot(payload: Optional[dict]) -> List[dict]:
    """Stable CRM order: paused rows only, deduped by id (check_next enrich or get_customer_appointments)."""
    if not isinstance(payload, dict):
        return []
    rows = _customer_appointments_embedded_in_payload(payload)
    if not rows:
        rows = _extract_customer_appointments_list(payload)
    rows = _filter_appointments_for_reschedule_overview(rows)
    out: List[dict] = []
    seen: set = set()
    for apt in rows:
        st = str(apt.get("status") or apt.get("appointment_status") or "")
        if not _is_paused_like_appointment_status(st):
            continue
        aid = _appointment_numeric_id(apt)
        if aid is None or aid in seen:
            continue
        seen.add(aid)
        out.append(apt)
    return out


def _resolve_user_chosen_paused_appointment_id(user_text: str, paused_ids: List[int]) -> Optional[int]:
    """
    After the bot listed paused rows 1..N, map the user's reply to the CRM appointment_id.
    Avoids treating '3' inside a long datetime sentence as a list index (length + pattern guards).
    """
    if not user_text or not paused_ids:
        return None
    n = len(paused_ids)
    t_raw = user_text.strip()
    t = _arabic_indic_digits_to_ascii(t_raw)

    for aid in sorted(set(paused_ids), reverse=True):
        if re.search(rf"(?<!\d){int(aid)}(?!\d)", t):
            return int(aid)

    m2 = re.search(
        r"(?:رقم|number|#|اختر|اختار|choice|option|n\s*)\s*(\d{1,2})\b",
        t,
        re.I,
    )
    if m2:
        idx = int(m2.group(1))
        if 1 <= idx <= n:
            return paused_ids[idx - 1]

    m1 = re.match(r"^[\s#]*(\d{1,2})[\s.):،,-]*$", t)
    if m1 and len(t) <= 22:
        idx = int(m1.group(1))
        if 1 <= idx <= n:
            return paused_ids[idx - 1]

    return None


def _bot_reply_claims_completed_appointment_update(bot_reply: str) -> bool:
    br = (bot_reply or "").strip().lower()
    if "تم تثبيت تعديل" in br or "تمّ تثبيت تعديل" in br:
        return True
    if "تم تثبيت طلبك" in br and ("تعديل" in br or "موعد" in br):
        return True
    if "تم تأكيد التعديل" in br or "تم تأكيد تعديل" in br:
        return True
    if "appointment has been updated" in br or "appointment has been rescheduled" in br:
        return True
    if "تم تحديث الموعد" in br or "تم نقل الموعد" in br:
        return True
    return False


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

# All bookable laser services must send body_part_ids + session_number on create.
# Hair removal (1, 12) is the only family where the customer chooses the device (Neo/Quadro/Candela/…).
DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS = {1, 2, 4, 5, 11, 12, 13, 14}
LASER_HAIR_REMOVAL_SERVICE_IDS = {1, 12}
# get_machines IDs that are laser-hair devices (Quadro, Trio, NEO, Candela) — not Pico/tattoo/DPL.
# If GPT sends service_id 13 (tattoo) with one of these, it is almost always a hair booking misfire.
HAIR_REMOVAL_MACHINE_IDS = frozenset({9, 10, 13, 15})

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
            if item is None:
                continue
            if isinstance(item, dict):
                iid = _safe_int(item.get("body_part_id") or item.get("id"))
                if iid is not None and iid > 0:
                    result.append(iid)
                continue
            parsed = _safe_int(item)
            if parsed is not None and parsed > 0:
                result.append(parsed)
        return result

    if isinstance(raw_value, str):
        pieces = [part.strip() for part in raw_value.split(",") if part.strip()]
        result = []
        for part in pieces:
            parsed = _safe_int(part)
            if parsed is not None and parsed > 0:
                result.append(parsed)
        return result

    parsed_single = _safe_int(raw_value)
    return [parsed_single] if parsed_single is not None and parsed_single > 0 else []


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
    if any(
        keyword in text
        for keyword in ("candela", "كانديلا", "kandila", "quadro", "كوادرو", "trio", " neo", "neo ")
    ):
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
    function_args: Dict[str, Any],
    booking_state: Dict[str, Any],
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


def _finalize_create_appointment_payload_for_api(function_args: Dict[str, Any]) -> None:
    """
    Align tool args before legacy create: CRM POST uses top-level body_part_ids (PDF).
    Keeps body_part_ids and body_parts_with_sessions consistent; preserves session_number
    when the model supplied it (≠1 → legacy_create passes body_parts through to the API).
    """
    raw_bps = function_args.get("body_parts_with_sessions")
    ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
    if isinstance(raw_bps, list) and raw_bps:
        cleaned: List[Dict[str, Any]] = []
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
        function_args["body_parts_with_sessions"] = [
            {"body_part_id": bid, "session_number": 1} for bid in ids
        ]
        function_args["body_part_ids"] = list(ids)


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


def _dedupe_bot_reply_text(text: str) -> str:
    """
    Models sometimes echo the same user-visible text twice, or concatenate two identical JSON blobs
    inside bot_reply. Collapse so WhatsApp users see a single message.
    """
    s = (text or "").strip()
    if not s:
        return s
    n = len(s)
    if n >= 24 and n % 2 == 0 and s[: n // 2] == s[n // 2 :]:
        return s[: n // 2].strip()
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    if len(lines) == 2 and lines[0] == lines[1]:
        return lines[0]
    if s.startswith("{") and '"action"' in s:
        parts = list(_extract_json_objects(s))
        if len(parts) >= 2:
            try:
                d0 = json.loads(parts[0])
                d1 = json.loads(parts[1])
                if isinstance(d0, dict) and isinstance(d1, dict):
                    b0 = (d0.get("bot_reply") or "").strip()
                    b1 = (d1.get("bot_reply") or "").strip()
                    if b0 and b0 == b1:
                        return b0
                    if b0:
                        return b0
            except (json.JSONDecodeError, TypeError):
                pass
    return s


def _parse_gpt_response_json(raw: str) -> dict:
    """
    Parse GPT response that may contain multiple JSON objects. Returns the first object
    that has both action and bot_reply. GPT sometimes returns two objects:
    - First: preferred_service, preferred_branch, etc. (no action/bot_reply)
    - Second: action, bot_reply (the actual response)
    It may also emit the same JSON object twice; duplicates are collapsed.
    """
    matches: List[Dict[str, Any]] = []
    for obj_str in _extract_json_objects(raw):
        try:
            parsed = json.loads(obj_str)
            # Require action + bot_reply key; allow empty bot_reply (models sometimes emit "" with a tool blob above).
            if (
                isinstance(parsed, dict)
                and parsed.get("action") is not None
                and "bot_reply" in parsed
            ):
                br = _dedupe_bot_reply_text(str(parsed.get("bot_reply") or ""))
                if not (br or "").strip():
                    br = (
                        "عذراً، لم يُكتمل نص الرد تلقائياً. جرّب مرة ثانية أو تواصل مع الفرع."
                    )
                parsed = {**parsed, "bot_reply": br}
                matches.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue
    if not matches:
        raise json.JSONDecodeError("No valid JSON object with action and bot_reply found", raw, 0)
    if len(matches) == 1:
        return matches[0]
    sigs = [json.dumps(m, sort_keys=True, ensure_ascii=False, default=str) for m in matches]
    if len(set(sigs)) == 1:
        return matches[0]
    return matches[0]


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


def _extract_booking_args_from_gpt_raw(raw: str) -> dict:
    """
    Parse tool-style JSON blobs emitted before the action JSON (e.g. date/time/service/machine)
    when the model confirms booking in text but does not call create_appointment.
    """
    out: Dict[str, Any] = {}
    for obj_str in _extract_json_objects(raw or ""):
        try:
            parsed = json.loads(obj_str)
            if not isinstance(parsed, dict):
                continue
            if parsed.get("action") is not None and "bot_reply" in parsed:
                continue
            for k in (
                "date",
                "time",
                "machine_id",
                "service_id",
                "service",
                "branch",
                "branch_id",
                "body_part",
                "body_part_text",
                "phone",
                "body_part_ids",
                "body_parts",
                "date_components",
                "calendar_day_intent",
                "customer_phone",
                "detected_name",
                "customer_name",
                "execute_booking",
                "gender",
            ):
                if k in parsed and parsed[k] is not None:
                    out[k] = parsed[k]
        except (json.JSONDecodeError, TypeError):
            continue
    if not out.get("body_part") and out.get("body_part_text"):
        out["body_part"] = str(out.get("body_part_text") or "").strip()
    # GPT often splits clock into separate "time" — recovery normalize expects one "date" string.
    if out.get("date") is not None and out.get("time"):
        ds = str(out["date"]).strip()
        ts = str(out["time"]).strip()
        if ds and ts and "T" not in ds and not re.search(r"\b\d{1,2}:\d{2}\b", ds):
            out["date"] = f"{ds} {ts}".strip()
        out.pop("time", None)
    return out


def _detect_change_request_intent(user_text: str) -> bool:
    text = str(user_text or "").strip().lower()
    if not text:
        return False
    change_patterns = [
        r"\b(reschedule|rescheduling|postpone|postponing|push back|move appointment|change appointment|shift appointment)\b",
        r"\b(reporter|decaler|décaler|deplacer|déplacer|changer rendez[- ]?vous)\b",
        r"(تأجيل|اجل|أجل|أجّل|تغيير الموعد|غير الموعد|غيّر الموعد|نقل الموعد|تبديل الموعد|موعد تاني|موعد اخر|موعد آخر)",
        r"\b(2ajel|ajjel|ghayer el maw3ed|ghayer maw3ed|postpone el maw3ed|reschedule el maw3ed)\b",
    ]
    return any(re.search(pattern, text, re.IGNORECASE | re.UNICODE) for pattern in change_patterns) or (
        detect_existing_appointment_edit_intent(text)
    )


def _collect_recent_user_text_for_change_intent(
    context_messages: Optional[List[dict]], latest_user_input: str, max_parts: int = 15
) -> str:
    parts: List[str] = []
    for msg in (context_messages or [])[-24:]:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    latest_clean = (latest_user_input or "").strip()
    if latest_clean and (not parts or parts[-1] != latest_clean):
        parts.append(latest_clean)
    return " ".join(parts[-max_parts:]).strip()


def _normalize_booking_date_for_tool_args(function_args: dict) -> Tuple[bool, Optional[str]]:
    """
    Same rules as inline normalize_tool_date for create/update, without touching api_failure_reason.
    Mutates function_args (pops calendar_day_intent, date_components); sets date API string.
    Returns (ok: bool, error_code: Optional[str]).
    """
    if not function_args.get("date") and not function_args.get("date_components"):
        return False, "booking_date_missing_field"
    original_date_str = str(function_args.get("date") or "").strip()
    now = now_in_bot_tz()
    ai_day_raw = function_args.pop("calendar_day_intent", None)
    dc_raw = function_args.pop("date_components", None)
    forced_day_ref = None
    if isinstance(ai_day_raw, str) and ai_day_raw.strip().lower() in ("today", "tomorrow"):
        forced_day_ref = ai_day_raw.strip().lower()

    dt_obj = datetime_from_ai_date_components(dc_raw)
    if dt_obj is not None:
        pass
    else:
        if not original_date_str:
            return False, "booking_structured_date_invalid"
        dt_obj = parse_datetime_flexible(original_date_str)
        if not dt_obj:
            return False, "booking_date_parse_failed"
        if forced_day_ref in ("today", "tomorrow"):
            dt_obj = align_datetime_to_day_reference(dt_obj, forced_day_ref, reference=now)

    if dt_obj.year < now.year:
        dt_obj = dt_obj.replace(year=now.year)

    max_allowed = now + datetime.timedelta(days=365)
    if dt_obj > max_allowed:
        return False, "booking_date_out_of_window"
    if dt_obj <= now:
        return False, "booking_date_in_past_or_now"

    function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return True, None


def _bot_reply_claims_completed_booking(bot_reply: str) -> bool:
    """True if the assistant text tells the user a NEW booking was completed (CRM must have confirmed)."""
    br = (bot_reply or "").strip().lower()
    if not br:
        return False
    # Keep in sync with the booking_claimed_without_* guard below. Models vary wording
    # (e.g. «صار الحجز مُثبت») — all must be caught to avoid false «booked» without tools.
    return any(
        x in br
        for x in (
            "تم تثبيت",
            "تمّ تثبيت",
            "تم حجز",
            "تمّ حجز",
            "صار الحجز",
            "صار موعدك",
            "الحجز مُثبت",
            "الحجز مثبت",
            "حجز مُثبت",
            "حجز مثبت",
            "تم تأكيد الحجز",
            "تمّ تأكيد الحجز",
            "تأكيد حجزك",
            "حجزك تم",
            "تم حجزك",
            "booked successfully",
            "appointment has been booked",
            "your appointment is confirmed",
            "appointment is confirmed",
        )
    )


def _parse_tool_round_bot_returned_local(bot_returned: str):
    if not bot_returned or not isinstance(bot_returned, str):
        return None
    try:
        return json.loads(bot_returned)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_submit_booking_failure_details(tool_round_trips: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the last submit_booking_intent failure with structured details for loop guard logs."""
    last_detail: Optional[Dict[str, Any]] = None
    for tr in tool_round_trips or []:
        name = str(tr.get("ai_requested") or "").strip()
        if name != "submit_booking_intent":
            continue
        bot_returned = _parse_tool_round_bot_returned_local(tr.get("bot_returned") or "")
        if not isinstance(bot_returned, dict) or bot_returned.get("success") is True:
            continue
        last_detail = {
            "tool_name": name,
            "error_type": bot_returned.get("error_type"),
            "human_readable_reason": bot_returned.get("human_readable_reason"),
            "missing_fields": bot_returned.get("missing_fields") or [],
            "invalid_fields": bot_returned.get("invalid_fields") or {},
            "conflicting_fields": bot_returned.get("conflicting_fields") or {},
            "normalized_values": bot_returned.get("normalized_values") or {},
            "activity_trace": bot_returned.get("activity_trace") or {},
            "tool_args": tr.get("args"),
            "backend_execution": tr.get("backend_execution") or {},
        }
    return last_detail


def _resolve_branch_id_from_leak(leaked: dict) -> Optional[int]:
    bid = _safe_int(leaked.get("branch_id"))
    if bid in (1, 2):
        return bid
    br = str(leaked.get("branch") or "").strip().lower()
    if "beirut" in br or "بيروت" in br:
        return 1
    if "antelias" in br or "انطلياس" in br or "antaliyas" in br:
        return 2
    return None


def _infer_service_id_from_leak(leaked: dict, current_gender: str) -> int:
    sid = _safe_int(leaked.get("service_id"))
    mid = _safe_int(leaked.get("machine_id"))
    if sid == 13 and mid is not None and mid in HAIR_REMOVAL_MACHINE_IDS:
        return 12 if current_gender == "female" else 1
    if sid is not None:
        return sid
    hint_sid = _service_hint_to_service_id(leaked.get("service"))
    if hint_sid is not None:
        return hint_sid
    svc = str(leaked.get("service") or "").strip().lower()
    if "hair" in svc or "شعر" in svc or "laser hair" in svc:
        return 12 if current_gender == "female" else 1
    return int(config.DEFAULT_SERVICE_ID or 1)


def _fix_misassigned_tattoo_service_for_hair_booking(
    function_args: Dict[str, Any],
    current_gender: str,
    user_input: str,
    context_messages: Optional[List[dict]],
) -> None:
    """
    GPT often confuses tattoo service_id (13) with NEO machine id (13) or sends 13 + Candela/Quadro.
    If the chosen machine is a hair device or the thread clearly mentions hair/Candela/underarm, remap to 1/12.
    """
    sid = _safe_int(function_args.get("service_id"))
    if sid != 13:
        return
    if current_gender not in ("male", "female"):
        return
    mid = _safe_int(function_args.get("machine_id"))
    blob = (user_input or "").lower()
    for msg in (context_messages or [])[-24:]:
        if isinstance(msg.get("content"), str):
            blob += " " + msg["content"].lower()
    hair_thread = any(
        t in blob
        for t in (
            "candela",
            "كانديلا",
            "kandila",
            "quadro",
            "كوادرو",
            " neo",
            "neo ",
            "niyo",
            "trio",
            "ليزر شعر",
            "إزالة شعر",
            "ازالة شعر",
            "ta7t el bat",
            "taht el bat",
            "t7t el bat",
            "تحت الإبط",
            "تحت الابط",
            "mw3ad",
            "maw3ad",
            "حجز",
            "موعد",
        )
    )
    tattoo_thread = any(t in blob for t in ("tattoo", "وشم", "تاتو", "détatouage", "detatouage"))
    if mid in HAIR_REMOVAL_MACHINE_IDS or (hair_thread and not tattoo_thread):
        new_sid = 12 if current_gender == "female" else 1
        print(
            f"DEBUG: Corrected service_id 13 → {new_sid} (hair booking; machine_id={mid}, hair_thread={hair_thread})"
        )
        function_args["service_id"] = new_sid


def _recent_booking_context_blob(context_messages: Optional[List[dict]], user_input: str, last_n: int = 24) -> str:
    parts: List[str] = []
    if user_input and str(user_input).strip():
        parts.append(str(user_input))
    for msg in (context_messages or [])[-last_n:]:
        c = msg.get("content")
        if isinstance(c, str) and c.strip():
            parts.append(c)
    return " ".join(parts)


async def _try_infer_body_part_ids_from_conversation(
    service_id: int,
    user_input: str,
    context_messages: Optional[List[dict]],
    machine_id: Optional[int] = None,
) -> Optional[List[int]]:
    """When GPT omitted valid IDs but the user already named an area (e.g. underarm / ta7t el bat)."""
    if not server_may_infer_body_parts():
        return None
    if _safe_int(service_id) not in LASER_HAIR_REMOVAL_SERVICE_IDS:
        return None
    blob = _recent_booking_context_blob(context_messages, user_input).lower()
    if not blob.strip():
        return None
    compact = re.sub(r"[\s_\-]+", "", blob)
    underarm_franco = any(
        t in blob
        for t in (
            "ta7t el bat",
            "taht el bat",
            "t7t el bat",
            "7t el bat",
            "ta7t l bat",
            "ta7t elbet",
        )
    )
    underarm_ar = "ابط" in blob or "إبط" in blob or "اباط" in blob
    # "under arms", "under arm", "underarms" → compact contains underarm
    underarm_en = (
        "underarm" in compact
        or "armpit" in blob
        or "arm pit" in blob
        or "aisselle" in blob
        or "axilla" in blob
    )
    if underarm_franco or underarm_ar or underarm_en:
        for hint in ("underarm", "إبط", "ابط", "armpit"):
            resolved = await _resolve_body_part_ids_from_area_hint(
                hint, service_id, machine_id
            )
            if resolved:
                return resolved
    legs_ctx = (
        any(t in compact for t in ("ejren", "ejrin", "ejeren", "sa2en", "s2en", "se2en"))
        or any(t in blob for t in ("رجلين", "رجل", "ساق", "ساقين"))
        or re.search(r"\blegs?\b", blob) is not None
    )
    if legs_ctx:
        resolved = await _resolve_body_part_ids_from_area_hint(
            blob[:500], service_id, machine_id
        )
        if resolved:
            return resolved
    return None


def _is_placeholder_booking_customer_name(name: Optional[str]) -> bool:
    if not name or not str(name).strip():
        return True
    n = str(name).strip().lower()
    placeholders = {
        "client",
        "unknown",
        "unknown customer",
        "test user",
        "guest",
        "user",
        "customer",
        "new user",
        "anonymous",
        "not known",
        "n/a",
        "na",
    }
    if n in placeholders:
        return True
    if n.startswith("test user"):
        return True
    return False


def _extract_latin_name_from_franco_booking_bundle(text: str) -> Optional[str]:
    """
    Infer Latin customer name from Franco one-liners like:
    se3a 3 bilal bilal bilal esm
    Also scans [User clarified: ...] blocks when the main query is a stub.
    """
    if not text or not str(text).strip():
        return None
    chunks: List[str] = []
    for m in re.finditer(r"\[User clarified:\s*(.+?)\]", text, flags=re.IGNORECASE | re.DOTALL):
        inner = (m.group(1) or "").strip()
        if inner:
            chunks.append(inner.split("\n")[0].strip())
    tail = str(text).strip().split("\n")[0].strip()
    if tail and tail not in chunks:
        chunks.append(tail)

    noise_tokens = {
        "se3a",
        "sa3a",
        "s3a",
        "seaa",
        "saa",
        "so3a",
        "wa2t",
        "wakt",
        "waket",
        "please",
        "pls",
        "ok",
        "okay",
        "eh",
        "ah",
        "mw3ad",
        "mwede",
        "mw3ede",
        "maw3ad",
        "mawede",
        "7ajez",
        "hajez",
        "bede",
        "bade",
        "bedi",
        "tanen",
        "tenen",
        "tunun",
        "beirut",
        "beyrouth",
        "antelias",
        "antaliyas",
        "kifak",
        "kifek",
        "hi",
        "hey",
        "hello",
    }

    for raw in chunks:
        line = raw.strip()
        line = re.sub(
            r"\b(esm|esmi|esme|ism|isme|ismi|name)\b\.?$",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()
        if not line:
            continue
        tokens = line.split()
        latin_words: List[str] = []
        for t in tokens:
            tl = re.sub(r"^[^\w]+|[^\w]+$", "", t, flags=re.UNICODE)
            if not tl:
                continue
            low = tl.lower()
            if low in noise_tokens:
                continue
            if tl.isdigit():
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", tl):
                continue
            if re.search(r"[\u0600-\u06FF]", tl):
                continue
            if len(low) < 2:
                continue
            if not re.fullmatch(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)?", tl):
                continue
            latin_words.append(tl)
        if not latin_words:
            continue
        lows = [w.lower() for w in latin_words]
        if len(set(lows)) == 1:
            cand = latin_words[0][:1].upper() + latin_words[0][1:].lower() if latin_words[0] else ""
        else:
            cand = " ".join(w[:1].upper() + w[1:].lower() if w else "" for w in latin_words)
        cand = cand.strip()
        if 2 <= len(cand) <= 80 and not _is_placeholder_booking_customer_name(cand):
            return cand
    return None


def _apply_inferred_name_from_user_bundle(
    user_id: str,
    user_input: str,
    parsed_response: Dict[str, Any],
) -> None:
    """Backfill detected_name + session name when GPT missed Franco time+name bundles."""
    inferred = _extract_latin_name_from_franco_booking_bundle(user_input or "")
    if not inferred:
        return
    existing = (parsed_response.get("detected_name") or "").strip()
    if not existing:
        parsed_response["detected_name"] = inferred
    try:
        ud = config.user_data_whatsapp.setdefault(user_id, {})
        if not (str(ud.get("collected_name") or "")).strip():
            ud["collected_name"] = inferred
        config.user_names[user_id] = inferred
    except Exception as persist_e:
        print(f"⚠️ inferred name persist (bundle): {persist_e}")


def _prune_redundant_booking_questions_when_name_from_bundle(
    user_input: str,
    parsed_response: Dict[str, Any],
) -> None:
    """
    If the user already bundled time + Latin name (Franco) but the model still asks for
    name / which Monday, strip those lines from bot_reply (Arabic-only; no Latin in reply).
    """
    if not _extract_latin_name_from_franco_booking_bundle(user_input or ""):
        return
    if (parsed_response.get("action") or "").strip().lower() != "ask_for_details_for_booking":
        return
    br = (parsed_response.get("bot_reply") or "").strip()
    if not br:
        return
    br2 = re.sub(
        r"(?m)^[^\n]*[١1]\)\s*[^\n]*(الاسم|اللاتين|الهوية|متل\s+الهوية)[^\n]*\n?",
        "",
        br,
    )
    br2 = re.sub(
        r"(?m)^[^\n]*[٢2]\)\s*[^\n]*(أي نهار|أي يوم)[^\n]*(تنين|إثنين|اثنين|الإثنين|الاثنين)[^\n]*\n?",
        "",
        br2,
    )
    br2 = re.sub(r"\n{3,}", "\n\n", br2).strip()
    if br2 == br:
        return
    still_numbered = bool(re.search(r"(?m)^\s*[١٢٣123][\).]", br2))
    if not still_numbered and (
        len(re.sub(r"\s+", "", br2)) < 20
        or re.search(r"(شغلتين|سؤالين|أسألك)", br2)
    ):
        parsed_response["bot_reply"] = (
            "تمام أستاذ 🌷 تم تسجيل اسمك والوقت اللي ذكرتهما من رسالتك؛ منتابع لإكمال الحجز."
        )
    else:
        parsed_response["bot_reply"] = br2


def _extract_customer_name_from_conversation_for_booking(
    user_id: str,
    current_context_messages: Optional[List[dict]],
    user_input: str,
) -> Optional[str]:
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
    machine_id: Optional[int],
    label: str,
) -> Optional[List[int]]:
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
    rows: List[dict] = []
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
    customer_phone_clean: Optional[str],
    current_gender: str,
    current_preferred_lang: str,
    current_context_messages: Optional[List[dict]],
    user_input: str,
    body_part_required_service_ids: set,
    is_reschedule_intent: bool,
    tool_names_so_far: List[str],
) -> Optional[dict]:
    """
    Legacy recovery disabled by architecture decision:
    booking understanding + official-ID resolution belong to the AI/tooling layer,
    while the backend only validates and executes canonical payloads.
    """
    return None


async def _coerce_body_part_ids_from_gpt_booking_args(
    booking_args: dict, service_id: int, machine_id: Optional[int] = None
) -> Optional[List[int]]:
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
    out: List[int] = []
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
                    resolved = await _resolve_body_part_ids_from_area_hint(
                        str(area), service_id, machine_id
                    )
                    if resolved:
                        out.extend(resolved)
    normalized = _normalize_body_part_ids(out)
    return normalized if normalized else None


# Shown to the model in tool JSON on submit_booking_intent failure — never raw stack traces.
_SUBMIT_BOOKING_TOOL_HINT_TECHNICAL = (
    "A temporary technical error occurred while contacting the booking system. "
    "Do NOT show stack traces, exception text, HTTP bodies, or internal codes to the user. "
    "Reply in the user's language in one short message: apologize briefly, say the booking could not "
    "be completed right now, and ask whether they prefer another day or another time (or to try again shortly). "
    "Do not claim the appointment was booked."
)
_SUBMIT_BOOKING_TOOL_HINT_CRM_REJECT = (
    "The clinic calendar did not confirm this exact slot (it may be unavailable or blocked). "
    "Do NOT paste raw API messages, JSON, or field names to the user. "
    "Reply in the user's language in one short message: apologize softly and ask them to choose "
    "another day or another time. When they answer, call submit_booking_intent again with the updated choice. "
    "Do not claim the appointment was booked."
)


def _sanitize_submit_booking_tool_for_model(tool_output: Dict[str, Any]) -> Dict[str, Any]:
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


def _missing_body_part_booking_prompt(service_id: Optional[int], lang: str) -> str:
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


def _service_hint_to_service_id(val: Any) -> Optional[int]:
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


def _branch_hint_to_branch_id(val: Any) -> Optional[int]:
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


def _datetime_from_gpt_booking_args(booking_args: dict) -> Optional[datetime.datetime]:
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


async def _resolve_body_part_ids_from_area_hint(
    area_hint: str, service_id: int, machine_id: Optional[int] = None
) -> Optional[List[int]]:
    """Resolve body_part_ids when only a human-readable area (e.g. back) is known."""
    if not server_may_infer_body_parts():
        return None
    if not area_hint or not str(area_hint).strip():
        return None
    static_ids = _area_name_to_body_part_ids(area_hint, service_id)
    if static_ids:
        return static_ids
    al = area_hint.strip().lower()
    al_compact = re.sub(r"[\s_\-]+", "", al)
    needle_terms = ("back", "ظهر", "ضهر", "dahr", "dahre", "عمود فقري")
    hand_terms = ("hand", "hands", "eideh", "eide", "يد", "اليد", "معصم", "wrist", "forearm", "arm")
    try:
        bp_resp = await api_integrations.get_body_parts(
            service_id=service_id, machine_id=machine_id
        )
        if not bp_resp.get("success") or not isinstance(bp_resp.get("data"), list):
            return None
        underarm_hint = (
            "underarm" in al_compact
            or "armpit" in al
            or "aisselle" in al
            or "axilla" in al
            or "ابط" in area_hint
            or "إبط" in area_hint
        )
        if underarm_hint:
            for item in bp_resp["data"]:
                name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
                if not name:
                    continue
                if any(
                    u in name
                    for u in ("underarm", "armpit", "ابط", "إبط", "aisselle", "axilla")
                ):
                    bid = _safe_int(item.get("id"))
                    if bid is not None and bid > 0:
                        return [bid]
        if al in hand_terms or any(t in al for t in ("eideh", "eide", "hand", "hands", "wrist", "معصم", "forearm")):
            for item in bp_resp["data"]:
                name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
                if not name:
                    continue
                if any(h in name for h in ("hand", "يد", "معصم", "wrist", "forearm", "arm", "ذراع")):
                    bid = _safe_int(item.get("id"))
                    if bid is not None:
                        return [bid]
        for item in bp_resp["data"]:
            name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
            if not name:
                continue
            if any(term in name for term in needle_terms):
                bid = _safe_int(item.get("id"))
                return [bid] if bid is not None else None
        bid = match_best_body_part_row(bp_resp["data"], area_hint)
        if bid is not None:
            return [bid]
    except Exception as ex:
        print(f"_resolve_body_part_ids_from_area_hint: {ex}")
    return None


def _user_explicitly_requests_machine_change(text: Optional[str]) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return False
    return any(
        token in s
        for token in (
            "machine",
            "device",
            "جهاز",
            "الماكينة",
            "المكنة",
            "neo",
            "candela",
            "quadro",
            "trio",
            "نيو",
            "كانديلا",
            "كوادرو",
            "تريو",
        )
    )


async def _resolve_machine_for_booking(
    service_id: Optional[int],
    candidate: Optional[int],
    preferred_existing_machine_id: Optional[int] = None,
) -> int:
    """
    Only laser hair removal (1, 12) uses the customer's machine choice from get_machines.
    Tattoo, CO2, whitening, etc. have a fixed device on the backend — ignore wrong GPT picks
    and map by machine name from the API list.
    """
    sid = _safe_int(service_id)
    cand = _safe_int(candidate)
    preferred_existing = _safe_int(preferred_existing_machine_id)
    fallback = _safe_int(getattr(config, "DEFAULT_MACHINE_ID", None))
    if fallback is None:
        fallback = 1

    def _first_non_none(*values: Optional[int]) -> Optional[int]:
        for value in values:
            if value is not None:
                return value
        return None

    if sid in LASER_HAIR_REMOVAL_SERVICE_IDS:
        try:
            resp = await api_integrations.get_machines()
            if resp.get("success") and isinstance(resp.get("data"), list):
                hair_ids: List[int] = []
                for machine in resp["data"]:
                    mid = _safe_int(machine.get("id"))
                    name = str(machine.get("name") or "").strip().lower()
                    if mid is None:
                        continue
                    if mid in HAIR_REMOVAL_MACHINE_IDS or any(
                        kw in name for kw in ("neo", "candela", "quadro", "trio")
                    ):
                        hair_ids.append(mid)
                hair_allowed = set(hair_ids)
                for choice in (cand, preferred_existing, fallback):
                    if choice is not None and choice in hair_allowed:
                        return choice
                if hair_ids:
                    return hair_ids[0]
        except Exception as ex:
            print(f"_resolve_machine_for_booking: {ex}")
        for choice in (cand, preferred_existing, fallback):
            if choice is not None and choice in HAIR_REMOVAL_MACHINE_IDS:
                return choice
        return _first_non_none(preferred_existing, cand, fallback)
    try:
        resp = await api_integrations.get_machines()
        if not resp.get("success") or not isinstance(resp.get("data"), list):
            return _first_non_none(cand, preferred_existing, fallback)
        machines = resp["data"]
        allowed_ids = {_safe_int(m.get("id")) for m in machines}
        allowed_ids.discard(None)

        def nm(m: dict) -> str:
            return (m.get("name") or "").strip().lower()

        def first_id(pred) -> Optional[int]:
            for m in machines:
                if pred(nm(m)):
                    mid = _safe_int(m.get("id"))
                    if mid is not None:
                        return mid
            return None

        if cand is not None and cand in allowed_ids:
            return cand
        if preferred_existing is not None and preferred_existing in allowed_ids:
            return preferred_existing

        if sid == 13:
            mid = first_id(lambda n: "pico" in n)
            if mid is not None:
                return mid
            mid = first_id(lambda n: "tattoo" in n or "وشم" in n)
            if mid is not None:
                return mid
        if sid in (2, 11):
            mid = first_id(lambda n: "co2" in n)
            if mid is not None:
                return mid
        if sid in (4, 5, 14):
            mid = first_id(lambda n: "dpl" in n)
            if mid is not None:
                return mid
            mid = first_id(lambda n: "trio" in n and "hair" not in n)
            if mid is not None:
                return mid
    except Exception as ex:
        print(f"_resolve_machine_for_booking: {ex}")
    return _first_non_none(preferred_existing, cand, fallback)


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
                        if ext.get("external_id"):
                            config.user_data_whatsapp[user_id]["crm_customer_id"] = ext["external_id"]
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
                        if ext.get("external_id"):
                            config.user_data_whatsapp[user_id]["crm_customer_id"] = ext["external_id"]
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

    # Authoritative server profile (after CRM sync) — booking FSM + prompts must not re-ask these
    user_name = config.user_names.get(user_id, "client")
    _placeholder_names_profile = {"client", "unknown", "unknown customer", "test user"}
    _name_lower_profile = (user_name or "").strip().lower()
    name_is_known = (
        user_name
        and user_name != "client"
        and _name_lower_profile not in _placeholder_names_profile
        and not _name_lower_profile.startswith("test user")
    )
    crm_customer_exists = config.user_data_whatsapp.get(user_id, {}).get("crm_customer_exists")
    crm_customer_id = config.user_data_whatsapp.get(user_id, {}).get("crm_customer_id")

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
    is_appointment_inquiry_intent = detect_appointment_inquiry_intent(user_input)
    is_bulk_reschedule_all_intent = detect_bulk_reschedule_all_intent(user_input)
    is_existing_appointment_edit_intent = detect_existing_appointment_edit_intent(user_input)
    if is_reschedule_intent:
        print("🔁 Intent routing lock: reschedule/postpone intent detected.")
    if is_appointment_inquiry_intent:
        print("📅 Intent routing: appointment status / listing inquiry detected.")
    if is_bulk_reschedule_all_intent:
        print("🔁 Intent routing: bulk reschedule ALL rows requested.")
    if is_existing_appointment_edit_intent:
        print("🛠️ Intent routing: existing appointment edit detected.")

    booking_fsm_prompt_block = ""
    try:
        from services.booking import booking_fsm as _booking_fsm_mod

        if _booking_fsm_mod.fsm_enabled():
            if not (
                is_reschedule_intent
                or is_appointment_inquiry_intent
                or is_bulk_reschedule_all_intent
                or is_existing_appointment_edit_intent
            ):
                _booking_fsm_mod.maybe_enter_booking_mode(user_id, user_input)
            _booking_fsm_mod.maybe_exit_booking_mode(user_id, user_input)
            _booking_fsm_mod.sync_from_flat_booking_state(user_id)
            _booking_fsm_mod.set_session_context(
                user_id,
                current_gender,
                customer_phone_clean or "",
                customer_display_name=(user_name if name_is_known else None),
                crm_customer_file=bool(crm_customer_exists),
                customer_id=str(crm_customer_id).strip() if crm_customer_id else None,
            )
            if explicitly_detected_gender_from_input in ("male", "female"):
                _booking_fsm_mod.lock_gender_from_user_message(
                    user_id, explicitly_detected_gender_from_input
                )
            _booking_fsm_mod.infer_body_area_from_user_message(user_id, user_input)
            _booking_fsm_mod.apply_heuristic_confirmation(user_id, user_input)
            booking_fsm_prompt_block = _booking_fsm_mod.build_prompt_block(user_id, current_gender)
            if booking_fsm_prompt_block:
                _fsm_snap = config.user_booking_state[user_id].get("booking_fsm") or {}
                _g_fs = _fsm_snap.get("customer_gender") or current_gender
                _ok_fc, _miss_fc = _booking_fsm_mod.fields_complete(_fsm_snap, _g_fs)
                _nxt_fc = _booking_fsm_mod.first_missing_field_for_user_chat(
                    _fsm_snap, _g_fs, user_id
                )
                _can_ex, _gr = _booking_fsm_mod.can_execute_submit(user_id, current_gender)
                _booking_fsm_mod.record_decision_log(
                    user_id,
                    phase="pre_gpt",
                    next_field=_nxt_fc,
                    gate=_gr or ("ready" if _can_ex else "blocked"),
                    extracted={"user_message_excerpt": (user_input or "")[:240]},
                )
                try:
                    _u_act = _booking_fsm_mod.build_unified_booking_snapshot(
                        user_id,
                        current_gender,
                        customer_exists=bool(crm_customer_exists),
                        customer_id=str(crm_customer_id).strip() if crm_customer_id else None,
                        name_is_known=bool(name_is_known),
                        crm_data_used=bool(_fsm_snap.get("crm_profile_applied")),
                    )
                    print(
                        "[BOOKING_ACTIVITY] "
                        + json.dumps(_u_act, ensure_ascii=False, default=str)[:12000]
                    )
                except Exception as _ba_e:
                    print(f"⚠️ BOOKING_ACTIVITY log: {_ba_e}")
    except Exception as _fsm_init_e:
        print(f"⚠️ booking_fsm pre-gpt: {_fsm_init_e}")

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
    # user_name, name_is_known, crm_customer_exists: set after CRM sync (see block above)
    customer_first_name = (user_name.split()[0] if user_name and user_name != "client" else user_name) if user_name else None
    _placeholder_names = {"client", "unknown", "unknown customer", "test user"}
    _name_lower = (user_name or "").strip().lower()
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
        "- **Exception — multiple CRM appointments:** If you must list several rows for the user to choose (reschedule / resume pause), use **one compact line per row** "
        "(appointment_id + date/time + service + branch + machine + areas + price only if in JSON), then **one** question asking for **`appointment_id`** or line number.\n"
        "- **Do NOT** ask for booking details (body part, machine, service, size, branch, date, time, name) unless the user is "
        "**booking** or **needs a price that depends on missing data**. On general questions, answer directly without pushing extra questions.\n"
        "- When booking/pricing needs more data: ask **only missing** fields (body part, machine only for hair removal, service, size for tattoo, branch, date, time). Never re-ask known facts.\n"
        "- After confirming a slot or total price: state clearly **when**, **what service/area**, and **cost** if relevant.\n"
        "- Do NOT dump service info + availability + pricing + multiple questions in one message unless the user explicitly asked for that depth.\n"
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
        f"- **customer_exists (CRM file)**: {bool(crm_customer_exists)} — **customer_id**: "
        f"{crm_customer_id if crm_customer_id else '—'}\n"
        "- **Profile lock (server)**: The name, phone, and gender lines below are loaded from the live system each turn. "
        "Do **not** ask the user to repeat them when this block already shows a known name, known gender (male/female), or an existing CRM file.\n"
        f"- **Show greeting**: {_show_greeting} - Reason: {_greeting_reason}. Use greeting ONLY when True (new user or inactive 12+ hours). Otherwise go straight to the answer. Do NOT repeat أهلاً أستاذ / أنا مروى in every message.\n"
        f"- **Customer Name**: {customer_name_context}\n"
        f"- **Customer Phone**: '{customer_phone_clean}' - Use this for ALL tool calls (check_next_appointment, submit_booking_intent, create_appointment if ever used, update_appointment_date). Do NOT ask for phone number.\n"
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
        f"**📅 CALENDAR ANCHOR (do not guess today/tomorrow; use this):** {format_clinic_calendar_anchor(current_local_time)}\n"
        f"{_clinic_holiday_calendar_block(user_id, current_local_time)}"
        f"{customer_file_summary}"
        + ((f"\n\n{booking_fsm_prompt_block}") if booking_fsm_prompt_block else "")
    )

    # Compact customer context for Activity Flow visibility (what Bot sends to AI about this customer)
    _file_raw = customer_file_summary.strip().lstrip("\n") if customer_file_summary else ""
    flow_customer_context_sent = (
        "=== CUSTOMER STATUS ===\n"
        f"- customer_exists: {bool(crm_customer_exists)}\n"
        f"- customer_id: {crm_customer_id or '(none)'}\n"
        f"- Name: {customer_name_context}\n"
        f"- Phone: {customer_phone_clean or '(none)'}\n"
        f"- Gender: {current_gender}\n"
        f"- Language hint: {current_preferred_lang}\n\n"
        "=== CUSTOMER FILE (services, sessions, body parts, payment, dates – done+available only) ===\n"
        + (_file_raw if _file_raw else "(No file or customer not found)")
    )

    reschedule_multi_hint = ""
    if is_reschedule_intent and customer_phone_clean:
        reschedule_multi_hint = await _build_multi_appointment_reschedule_hint(customer_phone_clean)

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
        if reschedule_multi_hint:
            routing_guardrail += reschedule_multi_hint

    if is_existing_appointment_edit_intent:
        routing_guardrail += (
            "\n\n"
            "**🛠️ EXISTING APPOINTMENT EDIT (THIS MESSAGE):**\n"
            "- The user wants to modify an already booked appointment (for example: change machine/device, add/remove body areas, switch service, or change branch).\n"
            "- This is **NOT** a new booking flow. Do **NOT** ask full booking questions again if the appointment row already exists in CRM.\n"
            "- Do **NOT** use `submit_booking_intent` or `create_appointment` for this request.\n"
            "- First identify the correct existing row with `check_next_appointment`; if several rows exist, ask for `appointment_id` or the line number only.\n"
            "- Then use **`edit_appointment`** for machine/body-part/service/branch edits. Use **`update_appointment_date`** only when the change is date/time only.\n"
            "- Reuse the current appointment facts from CRM and ask only for the single missing detail needed to complete the edit.\n"
        )

    if is_appointment_inquiry_intent and customer_phone_clean:
        routing_guardrail += (
            "\n\n"
            "**📅 APPOINTMENT STATUS / LISTING (THIS MESSAGE — MANDATORY):**\n"
            "- The user is asking **when** their appointment is, **what** is on file, or to **list** bookings (including paused / موقوف) — e.g. Franco «emtan mw3de», Arabic «موعدي إمتى», English «when is my appointment», «sho hene el mw3id el wa2fe», etc.\n"
            "- A **LIVE CRM APPOINTMENT SNAPSHOT** block is appended below this prompt with the current rows — **ground your list on it** (correct row count and ids). You **MUST** still call **`check_next_appointment`** this turn with the customer phone from context.\n"
            "- The tool response is enriched with **`customer_appointments`**: list **every** row returned. **One line per row**, each with **`appointment_id`**, date & time, service, branch, machine if present, body areas if present, price/total **only if JSON has it**.\n"
            "- **Never merge** several paused or active rows into one vague line (e.g. do not collapse multiple men's hair rows into «مرتين بنفس الوقت» unless the API literally returns a single row). If there are 5 paused lines, show **5** lines.\n"
            "- Clearly separate **active/upcoming** vs **paused** using the **status** field from JSON — do not guess.\n"
            "- If they need to **choose one** row to change: ask for **`appointment_id`** (رقم الموعد) or the line number matching your list.\n"
        )

    if is_bulk_reschedule_all_intent and customer_phone_clean:
        routing_guardrail += (
            "\n\n"
            "**🔁 BULK RESCHEDULE — ALL LISTED ROWS (THIS MESSAGE):**\n"
            "- The user asked to move **every** relevant appointment (often all paused lines) to the **same** new date/time (e.g. Franco «3mlon kelon», «kelon bokra», Arabic «كلهم»).\n"
            "- You MUST call **`update_appointment_date` once per distinct `appointment_id`** from the **LIVE CRM APPOINTMENT SNAPSHOT** (several tool calls in **this** turn).\n"
            "- **Forbidden:** Saying «تم تعديل كل المواعيد» / «صاروا كلهم» / «كلهم ببكرا» unless **each** of those tool calls returned **success** in this request.\n"
            "- If you only updated one row, say so honestly and offer to continue with the remaining ids — never claim all seven (or «الكل») are done.\n"
        )

    # Enforce explicit json contract whenever response_format={"type":"json_object"} is used.
    # Some OpenAI endpoints reject requests if the messages omit the word "json".
    json_output_contract = (
        "\n\nOUTPUT FORMAT (MANDATORY):\n"
        "- Reply with a valid json object only.\n"
        "- Include at least these keys: \"action\" and \"bot_reply\".\n"
        "- Optional: \"booking_fsm_patch\" — object with any of: service_id, branch_id, machine_id, body_part_ids, "
        "appointment_date (YYYY-MM-DD), appointment_time (HH:MM), confirmed_booking (true only after explicit user yes to final summary).\n"
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

    # Steer the model when the user only confirms after we promised an appointment update (Ok/deal/تمام…).
    if not user_image_base64 and _user_message_is_acknowledgment_only(user_input):
        _pend_update = _operational_context_promises_imminent_appointment_update(operational_context)
        if not _pend_update:
            for _msg in reversed(current_context_messages or []):
                if _msg.get("role") == "assistant":
                    _pend_update = _operational_context_promises_imminent_appointment_update(
                        str(_msg.get("content") or "")
                    )
                    break
        if _pend_update:
            system_instruction_final += (
                "\n\n**⚡ PENDING-OPERATION CONFIRMATION (THIS TURN ONLY):**\n"
                "- The user's latest message is only a short **yes / ok / proceed** style confirmation.\n"
                "- Your previous assistant turn (or thread context) already committed to **updating or rescheduling** an appointment.\n"
                "- **Interpret** their reply as authorization to **execute that same operation now**.\n"
                "- You MUST call the real tools in this response: `check_next_appointment` if you still need `appointment_id`, then use **`update_appointment_date`** for date/time-only changes or **`edit_appointment`** for machine/body-part/service/branch changes already agreed in the conversation. Do **not** claim the update is done in `bot_reply` unless the real update tool actually succeeded in this request.\n"
            )

    # Authoritative CRM rows in-system so «emtan mw3de» / multi-paused listings cannot be hallucinated or merged.
    if (
        is_appointment_inquiry_intent
        or is_reschedule_intent
        or is_existing_appointment_edit_intent
    ) and customer_phone_clean:
        _live_snap = await _build_live_crm_appointments_snapshot(customer_phone_clean)
        if _live_snap:
            system_instruction_final += _live_snap

    context_messages_for_ai = list(current_context_messages or [])
    context_cap = int(getattr(config, "MAX_CONTEXT_MESSAGES_IN_WINDOW", 0) or 0)
    if context_cap > 0 and len(context_messages_for_ai) > context_cap:
        context_messages_for_ai = context_messages_for_ai[-context_cap:]

    if len(context_messages_for_ai) < 4:
        system_instruction_final += (
            "\n\n**THREAD LENGTH NOTE:** CONTEXT MESSAGES below may be short (e.g. testing without full Firestore history). "
            "Use CUSTOMER STATUS and any «Last message we sent to the user» line from operational context. "
            "Short replies such as «eh» / «إيه» / «نعم» usually confirm the last bot question—continue booking/pricing, do not reset to a generic greeting.\n"
        )

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

    # Stage split: keep orchestration/tool-routing on 5.1; final user-facing response after tools on 5.4-mini.
    selected_model = ORCHESTRATION_MODEL
    model_metadata = {
        "complexity": "FIXED",
        "reason": f"Planning/tool-routing on {ORCHESTRATION_MODEL}",
    }
    print(f"🤖 Model selected: {selected_model} | Reason: {model_metadata['reason']}")

    try:
        final_response_model_used = selected_model
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
        api_failure_reason = None  # Set when create_appointment/other API fails → flow_meta.error → human handover (submit_booking_intent uses sanitized tool hints + AI reply, no raw exceptions)
        update_appointment_date_success_count = 0  # Successful date/edit updates this turn (bulk guard)
        pause_resume_success_count = 0  # Successful pause-lift actions (date update auto-resume or direct resume_appointment)
        tool_round_trips: List[Dict[str, Any]] = []
        ai_first_response_with_tools = ""
        recovered_create_appointment_ok = False

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
            tool_round_trips.clear()
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
                return _is_paused_like_appointment_status(str(status_value or ""))

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
                return _extract_customer_appointments_list(response_payload)

            def detect_change_request_intent(user_text: str) -> bool:
                text = str(user_text or "").strip().lower()
                if not text:
                    return False

                change_patterns = [
                    r"\b(reschedule|rescheduling|postpone|postponing|push back|move appointment|change appointment|shift appointment)\b",
                    r"\b(resume|reactivate|bring back|continue)\b.{0,30}\b(appointment|slot)\b",
                    r"\b(reporter|decaler|décaler|deplacer|déplacer|changer rendez[- ]?vous)\b",
                    r"(تأجيل|اجل|أجل|أجّل|تغيير الموعد|غير الموعد|غيّر الموعد|نقل الموعد|تبديل الموعد|موعد تاني|موعد اخر|موعد آخر)",
                    r"(?:رج[ّ]?ع|ارجع|يرجع|كم[ّ]?ل|كمل|فك|شيل).{0,35}(?:الموعد|موعدي|موعد|الموقوف|موقوف|البوز)",
                    r"(?:رج[ّ]?ع|ارجع|يرجع).{0,12}(?:يجي|جي).{0,24}(?:على|ع)\s*(?:الموعد|موعدي|موعد)",
                    r"\b(2ajel|ajjel|ghayer el maw3ed|ghayer maw3ed|postpone el maw3ed|reschedule el maw3ed)\b",
                    r"\b(rj+3|rje3|rja3|rod|rudd|kamm?el|kmel|fokk|fok|shil)\b.{0,30}\b(mw3ad|maw3ad|mou3ad|boz|pause|paused)\b",
                    r"\b(rj+3|rje3|rja3)\b.{0,10}\b(yje|yeje|iji|yiji|ji)\b.{0,20}\b(3a|3al|aal|al)\b.{0,8}\b(mw3ad|maw3ad|mou3ad)\b",
                ]
                return any(re.search(pattern, text, re.IGNORECASE | re.UNICODE) for pattern in change_patterns) or (
                    detect_existing_appointment_edit_intent(text)
                )

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

            async def list_paused_appointment_ids(phone_to_lookup: str) -> list:
                normalized_phone = normalize_phone_for_lookup(phone_to_lookup)
                if not normalized_phone:
                    return []
                out: list = []
                try:
                    customer_appointments = await api_integrations.get_customer_appointments(
                        phone=normalized_phone
                    )
                    if isinstance(customer_appointments, dict) and customer_appointments.get("success"):
                        for appointment_payload in extract_customer_appointments(customer_appointments):
                            if is_paused_status(extract_appointment_status(appointment_payload)):
                                aid = extract_appointment_id(appointment_payload)
                                if aid is not None:
                                    try:
                                        out.append(int(aid))
                                    except (TypeError, ValueError):
                                        pass
                except Exception as list_p_e:
                    print(f"WARNING: list_paused_appointment_ids failed: {list_p_e}")
                return out

            def collect_user_datetime_text(context_messages: list, latest_user_input: str) -> str:
                """
                Collect recent user text for date intent detection.
                Keeps chronology and ends with latest user input so the newest
                'today/tomorrow' intent wins over stale history.
                """
                recent_user_messages = []
                for msg in context_messages[-24:]:
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        recent_user_messages.append(content.strip())

                # Keep recent user turns (wider window: weekday + id-only replies stay linked).
                recent_user_messages = recent_user_messages[-30:]

                latest_clean = (latest_user_input or "").strip()
                if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
                    recent_user_messages.append(latest_clean)

                return " ".join(recent_user_messages).strip()

            def collect_recent_user_only_schedule_text(
                context_messages: list, latest_user_input: str, max_user_messages: int = 40
            ) -> str:
                """User messages only (no assistant lists) — for weekday intent when user sends id-only reply."""
                recent_user_messages = []
                for msg in context_messages[-100:]:
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        recent_user_messages.append(content.strip())
                recent_user_messages = recent_user_messages[-max_user_messages:]
                latest_clean = (latest_user_input or "").strip()
                if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
                    recent_user_messages.append(latest_clean)
                return " ".join(recent_user_messages).strip()

            def normalize_tool_date(
                function_name: str,
                function_args: dict,
                *,
                user_input_for_date: Optional[str] = None,
                context_messages_for_date: Optional[list] = None,
            ) -> bool:
                """
                Build API datetime from AI tool arguments only (date_components, date string,
                calendar_day_intent). Does not parse user chat text. False → handover (flow_meta.error).
                """
                nonlocal api_failure_reason
                if "date" not in function_args:
                    api_failure_reason = "booking_date_missing_field"
                    return False

                original_date_str = str(function_args.get("date") or "").strip()
                now = now_in_bot_tz()
                ai_day_raw = function_args.pop("calendar_day_intent", None)
                dc_raw = function_args.pop("date_components", None)
                forced_day_ref = None
                if isinstance(ai_day_raw, str) and ai_day_raw.strip().lower() in ("today", "tomorrow"):
                    forced_day_ref = ai_day_raw.strip().lower()

                dt_obj = datetime_from_ai_date_components(dc_raw)
                if dt_obj is not None:
                    print(f"DEBUG: Using date_components for {function_name}: {dc_raw} -> {dt_obj}")
                else:
                    if not original_date_str:
                        print(f"WARNING: {function_name}: missing date_components and empty date string.")
                        api_failure_reason = "booking_structured_date_invalid"
                        return False
                    dt_obj = parse_datetime_flexible(original_date_str)
                    if not dt_obj:
                        print(f"WARNING: Could not parse AI date '{original_date_str}' for {function_name}.")
                        api_failure_reason = "booking_date_parse_failed"
                        return False
                    if forced_day_ref in ("today", "tomorrow"):
                        dt_obj = align_datetime_to_day_reference(dt_obj, forced_day_ref, reference=now)

                # Reschedule: user named a weekday then sent only appointment_id — model often keeps the old slot's day and changes hour only.
                if (
                    function_name in ("update_appointment_date", "edit_appointment")
                    and user_input_for_date is not None
                    and context_messages_for_date is not None
                ):
                    uid = (user_input_for_date or "").strip()
                    if re.fullmatch(r"\d{4,7}", uid):
                        u_sched = collect_recent_user_only_schedule_text(
                            context_messages_for_date, user_input_for_date, max_user_messages=40
                        )
                        tw = detect_last_weekday_intent_from_user_text(u_sched)
                        if tw is not None and dt_obj.weekday() != tw:
                            adjusted = next_future_datetime_matching_weekday(
                                now, tw, dt_obj.hour, dt_obj.minute
                            )
                            if adjusted is not None:
                                print(
                                    f"SAFETY: update_appointment_date weekday align {dt_obj} -> {adjusted} "
                                    f"(user id-only; thread weekday={tw})"
                                )
                                dt_obj = adjusted

                if dt_obj.year < now.year:
                    dt_obj = dt_obj.replace(year=now.year)
                    print(f"WARNING: AI date year adjusted to current year: {dt_obj}")

                max_allowed = now + datetime.timedelta(days=365)
                if dt_obj > max_allowed:
                    print(f"WARNING: AI date beyond allowed window: {dt_obj}")
                    api_failure_reason = "booking_date_out_of_window"
                    return False
                if dt_obj <= now:
                    print(f"WARNING: AI date not strictly in the future: {dt_obj} (now={now})")
                    api_failure_reason = "booking_date_in_past_or_now"
                    return False

                function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"DEBUG: Normalized date for {function_name}: {original_date_str or dc_raw} -> {function_args['date']}"
                )
                return True

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                all_user_text_for_date = collect_user_datetime_text(current_context_messages, user_input)
                user_requested_change = detect_change_request_intent(all_user_text_for_date) or is_reschedule_intent
                forced_update_appointment_id = None
                booking_state = config.user_booking_state[user_id]

                if function_name == "pause_appointment":
                    print("SAFETY: Blocking pause_appointment tool call; AI pause is disabled.")
                    err_content = json.dumps(
                        {
                            "success": False,
                            "message": "pause_appointment_disabled_for_ai",
                            "hint_for_model": (
                                "Do not pause appointments. For paused rows that should become active again, "
                                "use check_next_appointment and then update_appointment_date or update_paused_appointment "
                                "so the backend can restore Available status."
                            ),
                        },
                        ensure_ascii=False,
                    )
                    tool_outputs.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": err_content,
                        }
                    )
                    continue

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

                # SAFETY GUARD: If the canonical *next* appointment is paused/postponed and the user
                # asks to change/reschedule, never allow create_appointment — force update on that row.
                # Do NOT use an older paused record when the API's "next" slot is an active booking (e.g. Available).
                if function_name == "create_appointment" and user_requested_change:
                    phone_for_pause_guard = normalize_phone_for_lookup(
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or user_id
                    )

                    paused_appointment_id = await find_paused_appointment_id(phone_for_pause_guard)
                    _next_pl_create = (
                        extract_check_next_appointment(check_next_appointment_result)
                        if check_next_appointment_result
                        else {}
                    )
                    _next_id_create = extract_appointment_id(_next_pl_create)
                    _next_st_create = extract_appointment_status(_next_pl_create)
                    if (
                        paused_appointment_id
                        and _next_id_create is not None
                        and _next_id_create == paused_appointment_id
                        and is_paused_status(_next_st_create)
                    ):
                        requested_date = function_args.get("date")
                        function_name = "update_appointment_date"
                        function_args = {
                            "appointment_id": paused_appointment_id,
                            "phone": phone_for_pause_guard,
                            "date": requested_date,
                        }
                        forced_update_appointment_id = paused_appointment_id
                        print(
                            f"SAFETY: Converted create_appointment -> update_appointment_date for paused NEXT appointment_id={paused_appointment_id}"
                        )
                
                # --- create_appointment: structured tool args only (no user-text booking inference) ---
                if function_name == "create_appointment":
                    _fix_misassigned_tattoo_service_for_hair_booking(
                        function_args,
                        current_gender,
                        user_input,
                        current_context_messages,
                    )
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
                                    tool_round_trips.append(
                                        _record_tool_round_trip("create_customer", function_args, err_content, None)
                                    )
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


                    _legacy_inf = getattr(config, "BOOKING_LEGACY_INFERENCE", False)
                    if _legacy_inf:
                        # Legacy: default ids + area-name coercion + conversation inference for body parts
                        function_args["service_id"] = function_args.get("service_id", config.DEFAULT_SERVICE_ID)
                        function_args["machine_id"] = function_args.get("machine_id", config.DEFAULT_MACHINE_ID)
                        function_args["branch_id"] = function_args.get("branch_id", config.DEFAULT_BRANCH_ID)
                        _remember_booking_selection(user_id, function_args)

                    selected_service_id = _safe_int(function_args.get("service_id"))
                    function_args["machine_id"] = await _resolve_machine_for_booking(
                        selected_service_id, _safe_int(function_args.get("machine_id"))
                    )
                    _remember_booking_selection(user_id, function_args)

                    if _legacy_inf:
                        sid_for_coerce = (
                            selected_service_id
                            if selected_service_id is not None
                            else _safe_int(config.DEFAULT_SERVICE_ID)
                        )
                        coerced_bp = await _coerce_body_part_ids_from_gpt_booking_args(
                            function_args,
                            sid_for_coerce if sid_for_coerce is not None else 1,
                            _safe_int(function_args.get("machine_id")),
                        )
                        if coerced_bp:
                            function_args["body_part_ids"] = coerced_bp
                            _remember_booking_selection(user_id, function_args)

                    # If the model passed body_parts_with_sessions, normalize and align body_part_ids.
                    bps_raw = function_args.get("body_parts_with_sessions")
                    if isinstance(bps_raw, list) and bps_raw:
                        cleaned_sessions: List[Dict[str, Any]] = []
                        for item in bps_raw:
                            if not isinstance(item, dict):
                                continue
                            bid = _safe_int(item.get("body_part_id") or item.get("id"))
                            if bid is None or bid <= 0:
                                continue
                            sn = _safe_int(item.get("session_number"))
                            sess_num = int(sn) if sn is not None and sn >= 1 else 1
                            cleaned_sessions.append({"body_part_id": bid, "session_number": sess_num})
                        if cleaned_sessions:
                            function_args["body_parts_with_sessions"] = cleaned_sessions
                            function_args["body_part_ids"] = [x["body_part_id"] for x in cleaned_sessions]
                            _remember_booking_selection(user_id, function_args)

                    selected_body_part_ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
                    if selected_body_part_ids:
                        function_args["body_part_ids"] = selected_body_part_ids
                        _remember_booking_selection(user_id, function_args)
                    elif _legacy_inf and selected_service_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
                        inferred_bp = await _try_infer_body_part_ids_from_conversation(
                            selected_service_id,
                            user_input,
                            current_context_messages,
                            _safe_int(function_args.get("machine_id")),
                        )
                        if inferred_bp:
                            function_args["body_part_ids"] = inferred_bp
                            selected_body_part_ids = inferred_bp
                            _remember_booking_selection(user_id, function_args)
                    if (
                        selected_service_id in body_part_required_service_ids
                        and not selected_body_part_ids
                    ):
                        print("SAFETY: create_appointment missing body_part_ids — handover (no user-text fallback).")
                        return {
                            "action": "human_handover",
                            "handover_degree": "high",
                            "bot_reply": "عذراً، ما قدرنا نكمل الحجز آلياً. رح نوصلك لواحد من فريقنا يكمّل معك 🙏"
                            if current_preferred_lang in ("ar", "franco")
                            else "Sorry, we could not complete booking automatically. A team member will assist you shortly.",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender,
                            "escalation_reason": "frustration_detected",
                            "_flow_meta": {"error": "create_appointment_missing_body_part_ids"},
                        }

                    if _safe_int(function_args.get("branch_id")) not in (1, 2):
                        api_failure_reason = "invalid_branch_id"
                        err_content = json.dumps(
                            {
                                "success": False,
                                "message": "branch_id must be 1 (Beirut) or 2 (Antelias) in tool args.",
                            }
                        )
                        tool_round_trips.append(
                            _record_tool_round_trip(function_name, function_args, err_content, None)
                        )
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": err_content,
                            }
                        )
                        continue

                    if not normalize_tool_date(
                        function_name,
                        function_args,
                        user_input_for_date=user_input,
                        context_messages_for_date=current_context_messages,
                    ):
                        err_content = json.dumps(
                            {
                                "success": False,
                                "message": "Booking date validation failed; structured date/date_components required from AI.",
                            }
                        )
                        tool_round_trips.append(
                            _record_tool_round_trip(function_name, function_args, err_content, None)
                        )
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": err_content,
                            }
                        )
                        continue
                    
                    # NEW: Remove 'name' from function_args as create_appointment does not accept it directly.
                    # This resolves the `unexpected keyword argument 'name'` error.
                    if 'name' in function_args:
                        print(f"DEBUG: Removing 'name' argument '{function_args['name']}' from create_appointment call as it's not supported.")
                        del function_args['name']

                if function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment", "resume_appointment"):
                    phone_for_pause_guard = normalize_phone_for_lookup(
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or user_id
                    )

                    if user_requested_change and phone_for_pause_guard:
                        paused_appointment_id = await find_paused_appointment_id(phone_for_pause_guard)
                        _next_pl_upd = (
                            extract_check_next_appointment(check_next_appointment_result)
                            if check_next_appointment_result
                            else {}
                        )
                        _next_id_upd = extract_appointment_id(_next_pl_upd)
                        _next_st_upd = extract_appointment_status(_next_pl_upd)
                        # Only force paused id when the system's NEXT row is that paused appointment.
                        # If next is Active/Available, rescheduling must target that id — not an older paused record.
                        if (
                            paused_appointment_id
                            and check_next_appointment_result
                            and _next_id_upd is not None
                            and _next_id_upd == paused_appointment_id
                            and is_paused_status(_next_st_upd)
                        ):
                            try:
                                gpt_aid_int = int(function_args.get("appointment_id"))
                            except (TypeError, ValueError):
                                gpt_aid_int = None
                            if gpt_aid_int != paused_appointment_id:
                                print(
                                    f"SAFETY: Overriding {function_name} appointment_id with paused NEXT appointment_id={paused_appointment_id}"
                                )
                                function_args["appointment_id"] = paused_appointment_id
                                forced_update_appointment_id = paused_appointment_id

                    # When "next" from check_next is an active/Available row but the file has exactly ONE
                    # paused row and the user wording is "resume / lift from pause", the model often chains
                    # appointment_id to the active row — CRM then never moves the paused row.
                    if (
                        user_requested_change
                        and phone_for_pause_guard
                        and not forced_update_appointment_id
                        and _user_intent_resume_paused_appointment(user_input)
                    ):
                        paused_rows = await list_paused_appointment_ids(phone_for_pause_guard)
                        if len(paused_rows) == 1:
                            single_paused = paused_rows[0]
                            _next_pl_mix = (
                                extract_check_next_appointment(check_next_appointment_result)
                                if check_next_appointment_result
                                else {}
                            )
                            _next_id_mix = extract_appointment_id(_next_pl_mix)
                            _next_st_mix = extract_appointment_status(_next_pl_mix)
                            if _next_id_mix is not None and not is_paused_status(_next_st_mix):
                                try:
                                    gpt_aid_mix = (
                                        int(function_args.get("appointment_id"))
                                        if function_args.get("appointment_id") is not None
                                        and str(function_args.get("appointment_id")).strip() != ""
                                        else None
                                    )
                                except (TypeError, ValueError):
                                    gpt_aid_mix = None
                                if gpt_aid_mix is None or gpt_aid_mix == _next_id_mix:
                                    print(
                                        f"SAFETY: Next appointment is active id={_next_id_mix} but user resumes "
                                        f"single paused id={single_paused} — overriding {function_name}"
                                    )
                                    function_args["appointment_id"] = single_paused
                                    forced_update_appointment_id = single_paused

                    # Many paused rows: user picks "3" / "رقم 5" / pastes CRM id — model often passes wrong id or chains "next".
                    # Do not require user_requested_change: a lone "3" after a numbered list is not detected as reschedule text.
                    if phone_for_pause_guard and not forced_update_appointment_id:
                        paused_order = _ordered_paused_appointments_from_snapshot(
                            check_next_appointment_result
                        )
                        if len(paused_order) < 2:
                            try:
                                ph = normalize_phone_for_lookup(phone_for_pause_guard) or phone_for_pause_guard
                                fresh_apts = await api_integrations.get_customer_appointments(phone=ph)
                                if isinstance(fresh_apts, dict) and fresh_apts.get("success"):
                                    paused_order = _ordered_paused_appointments_from_snapshot(fresh_apts)
                            except Exception as multi_pause_e:
                                print(
                                    f"WARNING: multi-paused pick: get_customer_appointments refresh failed: {multi_pause_e}"
                                )
                        if len(paused_order) >= 2:
                            pids = [_appointment_numeric_id(r) for r in paused_order]
                            pids = [x for x in pids if x is not None]
                            chosen_pid = _resolve_user_chosen_paused_appointment_id(user_input, pids)
                            if chosen_pid is not None:
                                try:
                                    gpt_aid_pick = (
                                        int(function_args.get("appointment_id"))
                                        if function_args.get("appointment_id") is not None
                                        and str(function_args.get("appointment_id")).strip() != ""
                                        else None
                                    )
                                except (TypeError, ValueError):
                                    gpt_aid_pick = None
                                if gpt_aid_pick is None or gpt_aid_pick != chosen_pid:
                                    print(
                                        f"SAFETY: {len(pids)} paused rows: user choice -> appointment_id={chosen_pid} "
                                        f"(gpt had {gpt_aid_pick})"
                                    )
                                    function_args["appointment_id"] = chosen_pid
                                    forced_update_appointment_id = chosen_pid

                    if phone_for_pause_guard and not function_args.get("phone"):
                        function_args["phone"] = phone_for_pause_guard

                    # Direct resume must never auto-chain to an active next appointment id.
                    if (
                        function_name == "resume_appointment"
                        and check_next_appointment_result
                        and not forced_update_appointment_id
                    ):
                        _next_pl_resume = extract_check_next_appointment(check_next_appointment_result)
                        _next_id_resume = extract_appointment_id(_next_pl_resume)
                        _next_st_resume = extract_appointment_status(_next_pl_resume)
                        if _next_id_resume is not None and is_paused_status(_next_st_resume):
                            try:
                                gpt_aid_resume = (
                                    int(function_args.get("appointment_id"))
                                    if function_args.get("appointment_id") is not None
                                    and str(function_args.get("appointment_id")).strip() != ""
                                    else None
                                )
                            except (TypeError, ValueError):
                                gpt_aid_resume = None
                            if gpt_aid_resume is None:
                                print(
                                    f"DEBUG: Auto-chaining paused NEXT appointment_id for resume -> {_next_id_resume}"
                                )
                                function_args["appointment_id"] = _next_id_resume
                                forced_update_appointment_id = _next_id_resume

                    aid_for_machine = _safe_int(function_args.get("appointment_id"))
                    machine_row = (
                        find_appointment_row_in_check_next_payload(
                            check_next_appointment_result, aid_for_machine
                        )
                        if aid_for_machine is not None and check_next_appointment_result
                        else None
                    )
                    row_service_id = row_branch_id = row_machine_id = None
                    if machine_row is not None:
                        row_service_id, row_branch_id, row_machine_id = (
                            extract_appointment_booking_fields(machine_row)
                        )
                    requested_machine_change = _user_explicitly_requests_machine_change(
                        all_user_text_for_date
                    )
                    arg_machine_id = _safe_int(function_args.get("machine_id"))
                    if arg_machine_id is not None and not requested_machine_change:
                        print(
                            "SAFETY: Removing unrequested machine_id from appointment update "
                            f"(appointment_id={aid_for_machine}, machine_id={arg_machine_id})"
                        )
                        function_args.pop("machine_id", None)
                    elif arg_machine_id is not None:
                        resolved_machine_id = await _resolve_machine_for_booking(
                            _safe_int(function_args.get("service_id")) or row_service_id,
                            arg_machine_id,
                            preferred_existing_machine_id=row_machine_id,
                        )
                        if resolved_machine_id is not None:
                            function_args["machine_id"] = resolved_machine_id
                        else:
                            function_args.pop("machine_id", None)

                    requires_date = (
                        function_name == "update_appointment_date"
                        or (function_name == "update_paused_appointment" and "date" in function_args)
                        or (function_name == "edit_appointment" and "date" in function_args)
                    )
                    if requires_date:
                        if not normalize_tool_date(
                            function_name,
                            function_args,
                            user_input_for_date=user_input,
                            context_messages_for_date=current_context_messages,
                        ):
                            err_content = json.dumps(
                                {
                                    "success": False,
                                    "message": "Reschedule date validation failed; structured date/date_components required from AI.",
                                }
                            )
                            tool_round_trips.append(
                                _record_tool_round_trip(function_name, function_args, err_content, None)
                            )
                            messages.append(
                                {
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": err_content,
                                }
                            )
                            continue

                # --- Auto-chain appointment_id from check_next when GPT omitted it ---
                # If GPT already set appointment_id (e.g. user picked from a multi-appointment list), do not overwrite.
                if function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment") and check_next_appointment_result and not forced_update_appointment_id:
                    actual_appointment_id = extract_appointment_id(extract_check_next_appointment(check_next_appointment_result))
                    if actual_appointment_id:
                        gpt_raw = function_args.get("appointment_id")
                        try:
                            gpt_provided_id = int(gpt_raw) if gpt_raw is not None and gpt_raw != "" else None
                        except (TypeError, ValueError):
                            gpt_provided_id = None
                        if gpt_provided_id is None:
                            print(f"DEBUG: Auto-chaining appointment_id (missing) -> {actual_appointment_id}")
                            function_args["appointment_id"] = actual_appointment_id
                        elif gpt_provided_id != actual_appointment_id:
                            print(
                                f"DEBUG: Keeping GPT appointment_id={gpt_provided_id} (check_next next id={actual_appointment_id})"
                            )
                        else:
                            print(f"DEBUG: appointment_id already correct: {actual_appointment_id}")

                # Reject day/time that violate clinic rules (service + gender + branch + device) before CRM.
                if function_name in ("create_appointment", "update_appointment_date", "update_paused_appointment", "edit_appointment"):
                    date_s = function_args.get("date")
                    dt_local = None
                    if isinstance(date_s, str) and date_s.strip():
                        dt_local = parse_normalized_api_datetime(date_s.strip(), BOOKING_TZ)
                    if dt_local is not None:
                        sid = bid = None
                        mid: Optional[int] = None
                        if function_name == "create_appointment":
                            sid = _safe_int(function_args.get("service_id"))
                            bid = _safe_int(function_args.get("branch_id"))
                            mid = _safe_int(function_args.get("machine_id"))
                        elif function_name == "edit_appointment":
                            aid = _safe_int(function_args.get("appointment_id"))
                            row = find_appointment_row_in_check_next_payload(
                                check_next_appointment_result, aid
                            )
                            if row is not None:
                                sid, bid, mid = extract_appointment_booking_fields(row)
                            else:
                                sid = _safe_int(function_args.get("service_id"))
                                bid = _safe_int(function_args.get("branch_id"))
                                mid = _safe_int(function_args.get("machine_id"))
                        else:
                            aid = _safe_int(function_args.get("appointment_id"))
                            row = find_appointment_row_in_check_next_payload(
                                check_next_appointment_result, aid
                            )
                            if row is not None:
                                sid, bid, mid = extract_appointment_booking_fields(row)
                            else:
                                print(
                                    "DEBUG: slot_validation skipped update_appointment_date "
                                    f"(no CRM row for appointment_id={aid})"
                                )
                        if sid is not None and bid is not None:
                            vr = validate_booking_slot(
                                dt_local=dt_local,
                                service_id=sid,
                                branch_id=bid,
                                machine_id=mid,
                                gender_raw=current_gender,
                            )
                            if not vr.get("ok"):
                                sv = vr.get("slot_validation") or {}
                                err_content = json.dumps(
                                    {
                                        "success": False,
                                        "message": sv.get(
                                            "explanation_en",
                                            "This day/time is not available for the selected service, branch, and gender.",
                                        ),
                                        "slot_validation": sv,
                                    }
                                )
                                tool_round_trips.append(
                                    _record_tool_round_trip(function_name, function_args, err_content, None)
                                )
                                messages.append(
                                    {
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": function_name,
                                        "content": err_content,
                                    }
                                )
                                continue

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
                        tool_content = json.dumps(tool_output, default=str)
                        tool_round_trips.append(
                            _record_tool_round_trip(function_name, function_args, tool_content, None)
                        )
                        messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": tool_content})
                    except Exception as kr_e:
                        print(f"⚠️ retrieve_relevant_knowledge error: {kr_e}")
                        err_content = json.dumps({"success": False, "content": "", "message": str(kr_e)})
                        tool_round_trips.append(
                            _record_tool_round_trip(function_name, function_args, err_content, None)
                        )
                        messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": err_content})
                elif function_name == "submit_booking_intent":
                    from services.booking.intent_pipeline import handle_submit_booking_intent
                    from services.booking.schemas import validation_error_response
                    from services.booking.booking_fsm import (
                        can_execute_submit,
                        fsm_enabled as _fsm_gate_enabled,
                        human_gate_message,
                        mark_booking_completed,
                        parse_gate_reason,
                    )

                    _sb_phone = (
                        function_args.get("phone")
                        or customer_phone_clean
                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                        or ""
                    )
                    _ok_submit, _gate_reason = can_execute_submit(user_id, current_gender)
                    if _fsm_gate_enabled() and not _ok_submit:
                        _mf = parse_gate_reason(_gate_reason or "")
                        tool_output = validation_error_response(
                            missing_fields=_mf,
                            human_readable_reason=human_gate_message(_gate_reason or "", current_preferred_lang),
                            activity_trace={
                                "failure_stage": "booking_fsm_gate",
                                "execution_phase": "pre_execution",
                                "detail": _gate_reason,
                                "pipeline_phase": "submit_booking_intent_blocked",
                            },
                        )
                    else:
                        try:
                            tool_output = await handle_submit_booking_intent(
                                user_id=user_id,
                                phone=str(_sb_phone).strip(),
                                current_gender=current_gender,
                                user_input=user_input,
                                function_args=function_args,
                            )
                        except Exception as _sb_exc:
                            print(f"ERROR: submit_booking_intent raised: {_sb_exc}")
                            tool_output = {
                                "success": False,
                                "error_type": "submit_exception",
                                "human_readable_reason": _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL,
                                "activity_trace": {
                                    "failure_stage": "submit_exception",
                                    "detail": f"{type(_sb_exc).__name__}: {str(_sb_exc)[:500]}",
                                    "pipeline_phase": "submit_booking_intent",
                                },
                            }
                        if (
                            isinstance(tool_output, dict)
                            and tool_output.get("success")
                            and tool_output.get("booking_flow_state") == "booked"
                        ):
                            try:
                                mark_booking_completed(user_id)
                            except Exception as _fsm_mc_e:
                                print(f"⚠️ booking_fsm mark_booking_completed: {_fsm_mc_e}")
                    _tool_for_model = (
                        _sanitize_submit_booking_tool_for_model(tool_output)
                        if isinstance(tool_output, dict)
                        else tool_output
                    )
                    tool_content = json.dumps(_tool_for_model, default=str)
                    tool_round_trips.append(
                        _record_tool_round_trip(
                            function_name,
                            function_args,
                            tool_content,
                            tool_output if isinstance(tool_output, dict) else None,
                        )
                    )
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": tool_content,
                        }
                    )
                    if isinstance(tool_output, dict) and tool_output.get("success") and tool_output.get("booking_flow_state") == "booked":
                        recovered_create_appointment_ok = True
                        try:
                            from services.analytics_events import analytics

                            api_wrapped = tool_output.get("api_response") or {}
                            raw_data_payload = api_wrapped.get("data", {})
                            appointment_data = (
                                raw_data_payload.get("appointment")
                                if isinstance(raw_data_payload, dict)
                                else {}
                            ) or {}
                            service_info = appointment_data.get("service") or {}
                            service_name = (
                                service_info.get("name", "unknown_service")
                                if isinstance(service_info, dict)
                                else str(service_info)
                            )
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="booked",
                                messages_count=len(current_context_messages or []),
                            )
                            try:
                                from services.session_rating_service import (
                                    schedule_session_rating_prompt_after_booking,
                                )

                                asyncio.create_task(schedule_session_rating_prompt_after_booking(user_id))
                            except Exception as sr_e:
                                print(f"WARNING: session rating schedule (submit_booking_intent): {sr_e}")
                        except Exception as an_sb:
                            print(f"WARNING: analytics (submit_booking_intent): {an_sb}")
                elif hasattr(api_integrations, function_name) and callable(getattr(api_integrations, function_name)):
                    function_to_call = getattr(api_integrations, function_name)
                    print(f"DEBUG: Executing tool: {function_name} with args: {function_args}")

                    try:
                        if function_name == "create_appointment":
                            _finalize_create_appointment_payload_for_api(function_args)
                            from services.booking.intent_pipeline import legacy_create_appointment_tool_output

                            tool_output = await legacy_create_appointment_tool_output(
                                user_id=user_id,
                                function_args=function_args,
                                current_gender=current_gender,
                                user_input=user_input,
                            )
                        else:
                            tool_output = await function_to_call(**function_args)
                        if (
                            function_name == "get_body_parts"
                            and isinstance(tool_output, dict)
                            and not tool_output.get("success")
                        ):
                            tool_output = dict(tool_output)
                            tool_output["hint_for_model"] = (
                                "CRM body-part list failed to load. Do NOT ask the user for 'the area name as registered in the system' "
                                "when they already described the location (e.g. neck / رقبة / ra2be). "
                                "Call submit_booking_intent with body_part set to their wording and body_part_ids empty when possible "
                                "so the server resolves IDs, or briefly apologize and offer branch contact if resolution is impossible. "
                                "Ops: Appointment API uses GET /service/data for areas (LINASLASER_SERVICE_DATA_PATH); "
                                "legacy hosts may set LINASLASER_GET_BODY_PARTS_PATH or LINASLASER_TATTOO_BODY_SYNONYMS_JSON."
                            )
                        if (
                            function_name == "update_appointment_date"
                            and isinstance(tool_output, dict)
                            and tool_output.get("success")
                        ):
                            tool_output = dict(tool_output)
                            ra = tool_output.get("resume_appointment") or {}
                            base = (
                                "This tool returned success — the Agent API accepted the new datetime (see data.old_date / new_date). "
                            )
                            if ra.get("attempted") and ra.get("success"):
                                base += (
                                    "A follow-up **resume** call also succeeded — the CRM should show the slot as active/Available "
                                    "(not Paused) in addition to the new time. Say so briefly in Arabic if bot_reply is Arabic. "
                                )
                            elif ra.get("attempted") and not ra.get("success"):
                                base += (
                                    f"A follow-up **resume** call was attempted ({ra.get('path')!r}) but failed: {ra.get('message')!r}. "
                                    "Datetime was still updated. If status still shows «موقوف», ask reception to clear pause or fix the resume endpoint; "
                                    "do not claim the datetime change failed. "
                                )
                            elif ra.get("skipped"):
                                base += (
                                    "Resume-from-pause was skipped (LINASLASER_APPOINTMENT_RESUME_PATH=off or empty). "
                                    "If the row stays Paused in the CRM, enable resume path or ask backend to clear pause on date update. "
                                )
                            else:
                                base += (
                                    "If the customer says the clinic computer still shows the old time: explain that the booking API "
                                    "confirmed the update; reception software may need refresh; rows can still show «موقوف» while "
                                    "the time field was updated—staff can verify by appointment_id. "
                                )
                            base += "Do not claim the update failed unless a later tool result contradicts this."
                            tool_output["hint_for_model"] = base
                        print(f"DEBUG: Tool output for {function_name}: {tool_output}")

                        # Enrich "next" with full customer list so the model can list every upcoming booking.
                        if function_name == "check_next_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            phone_for_enrich = normalize_phone_for_lookup(
                                function_args.get("phone")
                                or customer_phone_clean
                                or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                                or user_id
                            )
                            if phone_for_enrich:
                                try:
                                    list_resp = await api_integrations.get_customer_appointments(phone=phone_for_enrich)
                                    if isinstance(list_resp, dict) and list_resp.get("success"):
                                        all_apts = _extract_customer_appointments_list(list_resp)
                                        if all_apts:
                                            d = tool_output.get("data")
                                            if isinstance(d, dict):
                                                d["customer_appointments"] = all_apts
                                            elif d is None:
                                                tool_output["data"] = {"customer_appointments": all_apts}
                                            else:
                                                # Keep original data shape for appointment_id extraction; list is parallel.
                                                tool_output["customer_appointments"] = all_apts
                                            print(
                                                f"DEBUG: check_next_appointment enriched with {len(all_apts)} customer_appointments"
                                            )
                                except Exception as enrich_e:
                                    print(
                                        f"WARNING: check_next_appointment enrich get_customer_appointments failed: {enrich_e}"
                                    )
                            check_next_appointment_result = tool_output
                            print(f"DEBUG: Stored check_next_appointment result for auto-chaining")

                        # 📊 ANALYTICS: Track service when appointment is created
                        if function_name == "create_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            from services.analytics_events import analytics

                            api_wrapped = (
                                tool_output.get("api_response")
                                if isinstance(tool_output.get("api_response"), dict)
                                else tool_output
                            )
                            raw_data_payload = (
                                api_wrapped.get("data", {}) if isinstance(api_wrapped, dict) else {}
                            )
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
                            try:
                                from services.session_rating_service import (
                                    schedule_session_rating_prompt_after_booking,
                                )

                                asyncio.create_task(schedule_session_rating_prompt_after_booking(user_id))
                            except Exception as sr_e:
                                print(f"WARNING: session rating schedule (create_appointment): {sr_e}")
                            if tool_output.get("booking_flow_state") == "booked":
                                recovered_create_appointment_ok = True
                        elif function_name == "create_appointment" and isinstance(tool_output, dict) and not tool_output.get("success"):
                            _api = tool_output.get("api_response") if isinstance(tool_output.get("api_response"), dict) else {}
                            err_msg_raw = (
                                _api.get("message")
                                if isinstance(_api, dict) and _api.get("message") is not None
                                else tool_output.get("human_readable_reason", "Unknown error")
                            )
                            err_msg = str(err_msg_raw) if not isinstance(err_msg_raw, dict) else json.dumps(err_msg_raw, default=str)
                            api_failure_reason = f"create_appointment_tool_failed: {err_msg}"
                            print(f"create_appointment tool: API failed (no user-text retry): {err_msg}")
                        
                        # 📊 ANALYTICS: Track appointment reschedule
                        elif function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment") and isinstance(tool_output, dict) and tool_output.get("success"):
                            update_appointment_date_success_count += 1
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
                            _aid_rs = function_args.get("appointment_id")
                            _ph_rs = (
                                function_args.get("phone")
                                or customer_phone_clean
                                or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                                or ""
                            )
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="rescheduled",
                                messages_count=0,
                                phone=str(_ph_rs).strip() if _ph_rs else None,
                                appointment_id=_aid_rs,
                            )
                            print(f"📊 Analytics: Appointment rescheduled - {service_name}")
                            ra = tool_output.get("resume_appointment") or {}
                            if ra.get("attempted") and ra.get("success"):
                                pause_resume_success_count += 1
                                try:
                                    aid = function_args.get("appointment_id")
                                    phone_arg = (
                                        function_args.get("phone")
                                        or customer_phone_clean
                                        or config.user_data_whatsapp.get(user_id, {}).get("phone_number")
                                        or ""
                                    )
                                    analytics.log_appointment_pause_cleared(
                                        user_id=user_id,
                                        appointment_id=aid,
                                        phone=str(phone_arg).strip() if phone_arg else None,
                                        service=service_name,
                                    )
                                except Exception as pr_e:
                                    print(f"WARNING: analytics pause_cleared: {pr_e}")
                        elif function_name == "resume_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            pause_resume_success_count += 1
                        elif function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment") and isinstance(tool_output, dict) and not tool_output.get("success"):
                            err_msg_raw = (tool_output or {}).get("message", "Unknown error")
                            err_msg = str(err_msg_raw) if not isinstance(err_msg_raw, dict) else json.dumps(err_msg_raw, default=str)
                            api_failure_reason = f"update_appointment_date_tool_failed: {err_msg}"
                            print(f"update_appointment_date tool: API failed: {err_msg}")

                        tool_content = json.dumps(tool_output, default=str)
                        tool_round_trips.append(
                            _record_tool_round_trip(
                                function_name,
                                function_args,
                                tool_content,
                                tool_output if isinstance(tool_output, dict) else None,
                            )
                        )
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
                        tool_round_trips.append(
                            _record_tool_round_trip(function_name, function_args, err_content, None)
                        )
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
                    tool_round_trips.append(
                        _record_tool_round_trip(function_name, function_args, err_content, None)
                    )
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": err_content,
                        }
                    )

            second_response = await client.chat.completions.create(
                model=FINAL_RESPONSE_MODEL,
                messages=messages,
                response_format={"type": "json_object"}
            )
            final_response_model_used = FINAL_RESPONSE_MODEL
            if not second_response.choices:
                raise ValueError("GPT returned no choices (after tool call)")
            gpt_raw_content = second_response.choices[0].message.content.strip() if second_response.choices[0].message.content else ""
            print(f"GPT Raw Response (after tool call): {gpt_raw_content}")

            parsed_response = _parse_gpt_response_json(gpt_raw_content)
        else:
            parsed_response = _parse_gpt_response_json(gpt_raw_content)

        try:
            from services.booking import booking_fsm as _bfsm_patch

            if _bfsm_patch.fsm_enabled():
                _bp = parsed_response.get("booking_fsm_patch")
                if isinstance(_bp, dict) and _bp:
                    _bfsm_patch.merge_patch(user_id, _bp)
            parsed_response.pop("booking_fsm_patch", None)
        except Exception as _bfsm_patch_e:
            print(f"⚠️ booking_fsm_patch merge: {_bfsm_patch_e}")

        _apply_inferred_name_from_user_bundle(user_id, user_input, parsed_response)
        _prune_redundant_booking_questions_when_name_from_bundle(user_input, parsed_response)

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

        try:
            from services.booking import booking_fsm as _bfsm_guard

            if _bfsm_guard.fsm_enabled():
                br2, _gmeta = _bfsm_guard.guard_bot_reply_booking_identity(
                    user_id,
                    parsed_response.get("bot_reply") or "",
                    current_gender,
                    lang=detected_language,
                )
                if _gmeta.get("guard_applied"):
                    parsed_response["bot_reply"] = br2
                    parsed_response["booking_reply_guard"] = _gmeta
        except Exception as _bg_e:
            print(f"⚠️ booking reply guard: {_bg_e}")

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

        try:
            from services.booking import booking_fsm as _bfsm_lock_g

            _dg_final = parsed_response.get("detected_gender")
            if (
                _bfsm_lock_g.fsm_enabled()
                and _dg_final in ("male", "female")
                and (config.user_booking_state.get(user_id) or {}).get("booking_fsm", {}).get("active")
            ):
                _bfsm_lock_g.lock_gender_from_session(user_id, _dg_final, "model_output")
        except Exception as _lg_e:
            print(f"⚠️ booking_fsm lock gender (post-parse): {_lg_e}")

        if "action" not in parsed_response or "bot_reply" not in parsed_response:
            raise ValueError("GPT response missing required fields (action or bot_reply)")

        # Flow logging metadata for dashboard transparency (detailed for Activity Flow)
        tool_names = [tc.function.name for tc in tool_calls] if tool_calls else []
        _brl_flow = (parsed_response.get("bot_reply") or "").strip().lower()
        had_update_tool = bool(tool_calls) and (
            "update_appointment_date" in tool_names
            or "update_paused_appointment" in tool_names
            or "edit_appointment" in tool_names
            or "resume_appointment" in tool_names
        )

        _leaked_rec = _extract_booking_args_from_gpt_raw(gpt_raw_content or "")
        _rec_has_date = bool(_leaked_rec.get("date") or _leaked_rec.get("date_components"))
        _rec_mach = _safe_int(_leaked_rec.get("machine_id"))
        _rec_lw = dict(_leaked_rec)
        _fix_misassigned_tattoo_service_for_hair_booking(
            _rec_lw, current_gender, user_input, current_context_messages
        )
        _rec_sid = _safe_int(_rec_lw.get("service_id")) or _infer_service_id_from_leak(
            _leaked_rec, current_gender
        )
        stuck_hair_booking_recovery = (
            (parsed_response.get("action") or "").strip().lower() == "ask_for_details_for_booking"
            and _rec_has_date
            and _rec_mach is not None
            and _rec_sid in LASER_HAIR_REMOVAL_SERVICE_IDS
        )

        # Model sometimes puts create_appointment-shaped JSON in the assistant text but only calls get_machines.
        if (
            tool_calls
            and "create_appointment" not in tool_names
            and "submit_booking_intent" not in tool_names
            and not api_failure_reason
            and (
                (
                    _bot_reply_claims_completed_booking(parsed_response.get("bot_reply") or "")
                    and not _bot_reply_claims_completed_appointment_update(
                        parsed_response.get("bot_reply") or ""
                    )
                )
                or stuck_hair_booking_recovery
            )
        ):
            rec_api = await _try_recover_create_appointment_from_auxiliary_gpt_json(
                gpt_raw_content,
                user_id=user_id,
                customer_phone_clean=customer_phone_clean,
                current_gender=current_gender,
                current_preferred_lang=current_preferred_lang,
                current_context_messages=current_context_messages,
                user_input=user_input,
                body_part_required_service_ids=body_part_required_service_ids,
                is_reschedule_intent=is_reschedule_intent,
                tool_names_so_far=tool_names,
            )
            if rec_api is not None:
                rec_dump = json.dumps(rec_api, default=str)
                tool_round_trips.append(
                    _record_tool_round_trip(
                        "create_appointment_recovered_from_auxiliary_gpt_json",
                        {"note": "parsed from model output before action JSON", "recovered": True},
                        rec_dump,
                        rec_api if isinstance(rec_api, dict) else None,
                    )
                )
                if rec_api.get("success") and rec_api.get("booking_flow_state") == "booked":
                    recovered_create_appointment_ok = True
                    if stuck_hair_booking_recovery:
                        parsed_response["action"] = "answer_question"
                        if detected_language in ("ar", "franco"):
                            parsed_response["bot_reply"] = _normalize_arabic_reply(
                                "تم تثبيت الحجز على السيستم. إذا بدك تعديل بالوقت أو الفرع، خبرني 🌷"
                            )
                        else:
                            parsed_response["bot_reply"] = (
                                "Your appointment has been saved in the system. "
                                "Let me know if you need to change the time or branch."
                            )
                    try:
                        from services.analytics_events import analytics

                        _rec_api = (
                            rec_api.get("api_response")
                            if isinstance(rec_api.get("api_response"), dict)
                            else rec_api
                        )
                        raw_data_payload = _rec_api.get("data", {}) if isinstance(_rec_api, dict) else {}
                        appointment_data = (
                            raw_data_payload.get("appointment") if isinstance(raw_data_payload, dict) else {}
                        ) or {}
                        service_info = appointment_data.get("service") or {}
                        service_name = (
                            service_info.get("name", "unknown_service")
                            if isinstance(service_info, dict)
                            else str(service_info)
                        )
                        analytics.log_appointment(
                            user_id=user_id,
                            service=service_name,
                            status="booked",
                            messages_count=len(current_context_messages or []),
                        )
                        try:
                            from services.session_rating_service import (
                                schedule_session_rating_prompt_after_booking,
                            )

                            asyncio.create_task(schedule_session_rating_prompt_after_booking(user_id))
                        except Exception as sr_e:
                            print(f"WARNING: session rating schedule (recovered booking): {sr_e}")
                    except Exception as an_e:
                        print(f"WARNING: analytics (recovered create_appointment): {an_e}")
                else:
                    _rec_fail = (
                        (rec_api or {}).get("api_response")
                        if isinstance((rec_api or {}).get("api_response"), dict)
                        else (rec_api or {})
                    )
                    err_msg_raw = (
                        _rec_fail.get("message")
                        if isinstance(_rec_fail, dict) and _rec_fail.get("message") is not None
                        else (rec_api or {}).get("human_readable_reason", "Unknown error")
                    )
                    err_msg = (
                        str(err_msg_raw) if not isinstance(err_msg_raw, dict) else json.dumps(err_msg_raw, default=str)
                    )
                    api_failure_reason = f"create_appointment_tool_failed: {err_msg}"

        # Structured booking only: no same-day or text-based booking fallbacks.

        # User replied Ok/تمام after bot said it WILL update (e.g. "رح أعدّل موعد…") — model must not claim "تم تثبيت التعديل" without tools.
        if not api_failure_reason and not had_update_tool:
            _pending_update_promise = _operational_context_promises_imminent_appointment_update(operational_context)
            if not _pending_update_promise:
                for _msg in reversed(current_context_messages or []):
                    if _msg.get("role") == "assistant":
                        _pending_update_promise = _operational_context_promises_imminent_appointment_update(
                            str(_msg.get("content") or "")
                        )
                        break
            if (
                _bot_reply_claims_completed_appointment_update(parsed_response.get("bot_reply") or "")
                and _user_message_is_acknowledgment_only(user_input)
                and _pending_update_promise
            ):
                api_failure_reason = "update_claimed_without_tool_after_pending_promise"

        # Reschedule wording in user message + completion text but no update_appointment_date in this turn.
        if (
            not api_failure_reason
            and tool_calls
            and not had_update_tool
            and is_reschedule_intent
        ):
            if any(
                m in _brl_flow
                for m in (
                    "تم تأجيل",
                    "تمّ تأجيل",
                    "تم التأجيل",
                    "تم تعديل الموعد",
                    "تمّ تعديل الموعد",
                    "تم تغيير الموعد",
                    "تم تحديث الموعد",
                    "تم نقل الموعد",
                    "صار موعدك",
                    "أصبح موعدك",
                    "rescheduled",
                    "postponed your appointment",
                    "moved your appointment",
                    "appointment has been updated",
                )
            ):
                api_failure_reason = "reschedule_claimed_without_update_appointment_date_tool"

        # Claims paused appointment was cleared / became active without a successful CRM update.
        if (
            not api_failure_reason
            and tool_calls
            and had_update_tool
            and pause_resume_success_count == 0
            and _bot_reply_claims_pause_lifted_or_resumed(parsed_response.get("bot_reply") or "")
        ):
            api_failure_reason = "pause_resume_claimed_without_successful_resume_action"

        if (
            not api_failure_reason
            and tool_calls
            and not had_update_tool
            and _bot_reply_claims_pause_lifted_or_resumed(parsed_response.get("bot_reply") or "")
        ):
            api_failure_reason = "pause_resume_claimed_without_update_appointment_date_tool"

        # If the model text claims a completed booking but never called create_appointment → handover signal.
        # Skip when reply is clearly an appointment *update* completion (handled above).
        if (
            not api_failure_reason
            and tool_calls
            and "create_appointment" not in tool_names
            and "submit_booking_intent" not in tool_names
            and not recovered_create_appointment_ok
            and not _bot_reply_claims_completed_appointment_update(parsed_response.get("bot_reply") or "")
        ):
            if _bot_reply_claims_completed_booking(parsed_response.get("bot_reply") or ""):
                tattoo_soft_recover = False
                try:
                    leaked_book = _extract_booking_args_from_gpt_raw(gpt_raw_content or "")
                    inf_sid = _infer_service_id_from_leak(leaked_book, current_gender)
                    st = config.user_booking_state.get(user_id) or {}
                    st_sid = _safe_int(st.get("service_id"))
                    bp_leak = _normalize_body_part_ids(leaked_book.get("body_part_ids"))
                    bp_state = (
                        _normalize_body_part_ids(st.get("body_part_ids"))
                        if st_sid == inf_sid
                        else []
                    )
                    if (
                        inf_sid == 13
                        and 13 in body_part_required_service_ids
                        and not (bp_leak or bp_state)
                    ):
                        tattoo_soft_recover = True
                        parsed_response["action"] = "ask_for_details_for_booking"
                        parsed_response["bot_reply"] = _missing_body_part_booking_prompt(
                            13, detected_language
                        )
                        partial_state: Dict[str, Any] = {"service_id": 13}
                        bid = _resolve_branch_id_from_leak(leaked_book)
                        if bid is not None:
                            partial_state["branch_id"] = bid
                        mid = _safe_int(leaked_book.get("machine_id"))
                        if mid is not None:
                            partial_state["machine_id"] = mid
                        _remember_booking_selection(user_id, partial_state)
                        if detected_language in ("ar", "franco") and parsed_response.get("bot_reply"):
                            parsed_response["bot_reply"] = _normalize_arabic_reply(
                                parsed_response["bot_reply"]
                            )
                except Exception as tattoo_soft_e:
                    print(f"⚠️ Tattoo soft recover (missing body parts) failed: {tattoo_soft_e}")
                if not tattoo_soft_recover:
                    api_failure_reason = "booking_claimed_without_create_appointment_tool"

        # «تم تعديل كل المواعيد» etc. without enough successful update_appointment_date calls (bulk user request).
        if not api_failure_reason and _bot_reply_claims_bulk_all_appointments_updated(
            parsed_response.get("bot_reply") or ""
        ):
            nrow = 0
            if customer_phone_clean:
                try:
                    nrow = await _count_live_reschedule_row_total(customer_phone_clean)
                except Exception as bulk_cnt_e:
                    print(f"WARNING: bulk update row count failed: {bulk_cnt_e}")
            if update_appointment_date_success_count == 0:
                api_failure_reason = "bulk_update_claimed_without_successful_update_appointment_date"
            elif nrow >= 2 and update_appointment_date_success_count < nrow:
                api_failure_reason = (
                    f"bulk_update_incomplete:crm_rows~{nrow}_but_only_"
                    f"{update_appointment_date_success_count}_successful_updates"
                )

        # Token usage: when tool calls exist, sum BOTH first and second API call usage (second_response alone misses first call's output)
        first_usage = getattr(response, "usage", None) if tool_calls else None
        usage = (getattr(second_response, "usage", None) if tool_calls else getattr(response, "usage", None))
        token_breakdown: Optional[Dict[str, Any]] = None
        if tool_calls and first_usage and usage:
            pt1 = getattr(first_usage, "prompt_tokens", 0) or 0
            ct1 = getattr(first_usage, "completion_tokens", 0) or 0
            pt2 = getattr(usage, "prompt_tokens", 0) or 0
            ct2 = getattr(usage, "completion_tokens", 0) or 0
            prompt_tokens_val = pt1 + pt2
            completion_tokens_val = ct1 + ct2
            cost1 = _compute_cost_from_usage(selected_model, pt1, ct1)
            cost2 = _compute_cost_from_usage(final_response_model_used, pt2, ct2)
            tokens_val = prompt_tokens_val + completion_tokens_val
            cost_info = {
                "input_cost_usd": round((cost1.get("input_cost_usd", 0) or 0) + (cost2.get("input_cost_usd", 0) or 0), 6),
                "output_cost_usd": round((cost1.get("output_cost_usd", 0) or 0) + (cost2.get("output_cost_usd", 0) or 0), 6),
                "cost_usd": round((cost1.get("cost_usd", 0) or 0) + (cost2.get("cost_usd", 0) or 0), 6),
            }
            token_breakdown = {
                "first_gpt_call": {
                    "model": selected_model,
                    "prompt_tokens": pt1,
                    "completion_tokens": ct1,
                    "total_tokens": pt1 + ct1,
                    **cost1,
                },
                "second_gpt_call": {
                    "model": final_response_model_used,
                    "prompt_tokens": pt2,
                    "completion_tokens": ct2,
                    "total_tokens": pt2 + ct2,
                    **cost2,
                },
            }
        else:
            tokens_val = (usage.total_tokens or (getattr(usage, "prompt_tokens", 0) or 0) + (getattr(usage, "completion_tokens", 0) or 0)) if usage else None
            prompt_tokens_val = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens_val = getattr(usage, "completion_tokens", None) if usage else None
            cost_info = _compute_cost_from_usage(final_response_model_used, prompt_tokens_val or 0, completion_tokens_val or 0) if (prompt_tokens_val is not None or completion_tokens_val is not None) else {}
            if usage and prompt_tokens_val is not None:
                token_breakdown = {
                    "single_call": {
                        "model": final_response_model_used,
                        "prompt_tokens": prompt_tokens_val,
                        "completion_tokens": completion_tokens_val or 0,
                        "total_tokens": tokens_val,
                        **cost_info,
                    }
                }
        flow_meta = {
            "model": selected_model,
            "orchestration_model": selected_model,
            "final_response_model": final_response_model_used,
            "stage_models": {
                "planning": selected_model,
                "final_response": final_response_model_used,
            },
            "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
            "ai_query_summary": flow_ai_query_summary,
            "bot_sent_to_ai": flow_bot_sent_to_ai_full,
            "customer_context_sent": flow_customer_context_sent,
            "tool_calls": tool_names if tool_names else None,
            "tokens": tokens_val,
            "prompt_tokens": prompt_tokens_val,
            "completion_tokens": completion_tokens_val,
            "token_breakdown": token_breakdown,
            **cost_info,
        }
        if api_failure_reason:
            flow_meta["error"] = api_failure_reason
        if tool_calls and tool_round_trips:
            flow_meta["ai_first_response"] = ai_first_response_with_tools[:1500] if ai_first_response_with_tools else None
            flow_meta["tool_round_trips"] = tool_round_trips
        _submit_fail = _extract_submit_booking_failure_details(tool_round_trips)
        if _submit_fail:
            st = config.user_booking_state[user_id]
            retry_meta = dict(st.get("booking_retry_meta") or {})
            fail_count = int(retry_meta.get("failed_submit_count") or 0) + 1
            last_activity = (_submit_fail.get("activity_trace") or {}) if isinstance(_submit_fail.get("activity_trace"), dict) else {}
            retry_meta = {
                "failed_submit_count": fail_count,
                "last_error_code": _submit_fail.get("error_type") or api_failure_reason or "validation_error",
                "last_error_message": _submit_fail.get("human_readable_reason"),
                "last_missing_fields": list(_submit_fail.get("missing_fields") or []),
                "last_invalid_fields": dict(_submit_fail.get("invalid_fields") or {}),
                "last_conflicting_fields": dict(_submit_fail.get("conflicting_fields") or {}),
                "last_payload_sent": _submit_fail.get("tool_args"),
                "last_activity_trace": last_activity,
                "last_failure_stage": last_activity.get("failure_stage"),
                "last_pipeline_phase": last_activity.get("pipeline_phase"),
            }
            st["booking_retry_meta"] = retry_meta
            print(
                "[BOOKING_RETRY] "
                + json.dumps(
                    {
                        "user_id": user_id,
                        "failed_submit_count": fail_count,
                        "last_error_code": retry_meta["last_error_code"],
                        "last_failure_stage": retry_meta["last_failure_stage"],
                        "last_pipeline_phase": retry_meta["last_pipeline_phase"],
                        "last_missing_fields": retry_meta["last_missing_fields"],
                        "last_invalid_fields": retry_meta["last_invalid_fields"],
                        "last_conflicting_fields": retry_meta["last_conflicting_fields"],
                    },
                    ensure_ascii=False,
                    default=str,
                )[:12000]
            )
            flow_meta["booking_retry"] = retry_meta
        elif "booking_retry_meta" in config.user_booking_state.get(user_id, {}):
            # Clear retry state on non-failure turns to avoid stale handover triggers.
            if not api_failure_reason:
                config.user_booking_state[user_id].pop("booking_retry_meta", None)
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
            if service_id_for_sync is None and getattr(config, "BOOKING_LEGACY_INFERENCE", False):
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
                "orchestration_model": selected_model,
                "final_response_model": final_response_model_used,
                "stage_models": {
                    "planning": selected_model,
                    "final_response": final_response_model_used,
                },
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
                "orchestration_model": selected_model,
                "final_response_model": final_response_model_used,
                "stage_models": {
                    "planning": selected_model,
                    "final_response": final_response_model_used,
                },
                "ai_raw_response": gpt_raw_content[:2000] if gpt_raw_content else None,
                "ai_query_summary": flow_ai_query_summary,
                "bot_sent_to_ai": flow_bot_sent_to_ai_full,
                "customer_context_sent": flow_customer_context_sent,
                "error": f"{type(e).__name__}: {e}",
            },
        }