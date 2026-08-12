"""Legacy GPT chat-response helpers group 2."""

from __future__ import annotations

import re
from typing import Any

from services import api_integrations
from services.chat_response_service_constants import _EXCLUDED_RESCHEDULE_SUMMARY_STATUSES
from services.chat_response_service_profile import (
    _appointment_row_status_lower,
    _extract_customer_appointments_list,
    _filter_appointments_for_reschedule_overview,
    _format_appointment_row_for_reschedule_hint,
    _is_paused_like_appointment_status,
)


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
            "- **Pause from chat:** The assistant **does not** put appointments on hold—`pause_appointment` is disabled server-side. "
            "If someone asks to «وقف الموعد» for hold-without-new-date, tell them reception can do it; your job is **reactivation** and rescheduling.\n"
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
        "- **Never** call **`pause_appointment`** — it is disabled. For **Paused → Available at the same date/time**, call **`resume_appointment`** once you have the right **`appointment_id`**.\n"
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

def _operational_context_promises_imminent_appointment_update(ctx: str | None) -> bool:
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
        r"يرجع.*يجي.*(?:على|ع)\s*موعد|كمّل.*جلس|كمل.*جلس|كمّل.*موعد|كمل.*موعد|تكمل|"
        r"خليه.{0,20}available|يصير.{0,12}available|متاح.{0,18}موقوف|موقوف.{0,22}متاح|"
        r"مش.{0,6}موقوف|ما.{0,6}بقى.{0,8}موقوف|فك.{0,10}الموقوف|رجّع.{0,15}فعّال",
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

def _build_pause_resume_execution_guardrail(
    *,
    resume_attempted: bool,
    resume_succeeded: bool,
    date_update_succeeded: bool,
    direct_resume_succeeded: bool,
) -> str:
    """
    Structured instruction for the final response pass.
    Keep it factual and non-user-facing so the final model verbalizes only what tools proved.
    """
    facts = [
        "AUTHORITATIVE EXECUTION FACTS FOR FINAL BOT REPLY:",
        f"- date_update_succeeded={bool(date_update_succeeded)}",
        f"- resume_attempted={bool(resume_attempted)}",
        f"- resume_succeeded={bool(resume_succeeded)}",
        f"- direct_resume_succeeded={bool(direct_resume_succeeded)}",
    ]
    if resume_succeeded or direct_resume_succeeded:
        facts.append(
            "- You MAY say the paused appointment became active/Available again because the backend confirmed it."
        )
    elif date_update_succeeded:
        facts.append(
            "- You MUST NOT say the paused appointment became Available. Only say the date/time changed successfully."
        )
        facts.append("- If needed, say status may still appear paused until reception/back office confirms it.")
    elif resume_attempted:
        facts.append(
            "- Resume was attempted but not confirmed successful. Do NOT say the appointment is Available now."
        )
    else:
        facts.append("- No successful resume action was confirmed. Do NOT claim the paused status was removed.")
    return "\n".join(facts)

def _status_requests_available(status_val: Any) -> bool:
    sv = str(status_val or "").strip().lower()
    return sv in ("available", "active", "resume", "resumed")

def _arabic_indic_digits_to_ascii(text: str) -> str:
    if not text:
        return ""
    return text.translate(
        str.maketrans(
            "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
            "01234567890123456789",
        )
    )

def _appointment_numeric_id(apt: dict | None) -> int | None:
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

def _customer_appointments_embedded_in_payload(payload: dict) -> list[dict]:
    """check_next_appointment enriched shape: data.customer_appointments."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        ca = data.get("customer_appointments")
        if isinstance(ca, list) and ca:
            return [x for x in ca if isinstance(x, dict)]
    return []

