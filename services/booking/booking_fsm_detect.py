"""Booking FSM detection, session, and identity helpers (LOC split)."""

from __future__ import annotations

import json
import re
from typing import Any, cast

import config

# --- Intent detection (booking mode entry) ---
# Include Franco spellings (mw3ad = موعد, 7ejz = حجز) so booking FSM + body-area NL run on short replies.
_BOOKING_ENTRY_RE = re.compile(
    r"(?i)\b("
    r"book|booking|appointment|appt|reserve|reservation|schedule|session|"
    r"mw3ad|mw3ede|mwede|mw3id|maw3ed|maw3id|maw3ad|"
    r"7ejz|7ajz|a7jaz|7ez|"
    r"حجز|موعد|مواعيد|احجز|بدي موعد|عندي موعد|جلسة|جلسات"
    r")\b"
)
_CANCEL_RE = re.compile(r"(?i)\b(cancel|stop|never\s*mind|الغاء|الغي|ما بدي|بطلت|لغيت)\b")

# User already named body areas (Lebanese/Arabic/Franco) — do not ask again in chat.
_BODY_AREA_MENTION_RE = re.compile(
    r"(?i)(بكيني|بيكيني|bikini|تيز|tizeh?|طيز|مؤخرة|مؤخره|ورا|خلفي|قدام|حماس|"
    r"إبط|ابط|ابط|رجل|رجلين|وجه|وش|صدر|ظهر|bikini|butt|underarm|leg|face)",
    re.UNICODE,
)

# Short affirmative / negative (confirmation step)
_AFFIRM_RE = re.compile(
    r"(?i)^\s*("
    r"ok|okay|yes|yeah|yep|sure|deal|done|confirm|neo|quadro|candela|"
    r"تمام|اوكي|أوكي|ايه|نعم|اه|آه|تم|ماشي|حاضر|يلا|نعم\s*نفذ|نفذ|موافق|"
    r"👍|✅"
    r")\s*\.?\s*$"
)
_NEGATIVE_RE = re.compile(
    r"(?i)^\s*("
    r"no|nope|cancel|لا|لأ|لاء|مو\s*موافق|غير|بدي\s*غير"
    r")\s*\.?\s*$"
)

# Strip re-confirmation questions when gender is already known (server-side guard).
_GENDER_RECONFIRM_RE = re.compile(
    r"(?is)[^\n.!?؟]*"
    r"(تأكد|للتأكيد|بس\s*أتأكد|فقط\s*للتأكيد|just\s*to\s*confirm|confirm\s+your|are\s+you\s+sure)"
    r"[^\n.!?؟]{0,80}"
    r"(شاب|شابة|ذكر|أنثى|رجل|مرأة|بنت|ولد|جنسك|جنس|male|female|man|woman|boy|girl)"
    r"[^\n]*"
)


def _fsm_root(user_id: str) -> dict[str, Any]:
    st = config.user_booking_state[user_id]
    if "booking_fsm" not in st or not isinstance(st.get("booking_fsm"), dict):
        st["booking_fsm"] = new_fsm_state()
    return cast(dict[str, Any], st["booking_fsm"])


def new_fsm_state() -> dict[str, Any]:
    return {
        "intent": "book_appointment",
        "active": False,
        "customer_id": None,
        "customer_name": None,
        "customer_phone": None,
        "customer_gender": None,
        "service_id": None,
        "service_name": None,
        "branch_id": None,
        "branch_name": None,
        "machine_id": None,
        "machine_name": None,
        "body_part_ids": [],
        "body_part_names": [],
        "appointment_date": None,
        "appointment_time": None,
        "slot_id": None,
        "confirmation_status": "none",
        "booking_status": "idle",
        "execution_allowed": False,
        "last_asked_field": None,
        "body_area_already_described": False,
        "bikini_tize_single_package": False,
        "crm_customer_file": False,
        "crm_profile_applied": False,
        "locked_fields": {},
        "last_next_question_field": None,
        "duplicate_question_detected": False,
        "pending_confirmation_summary": None,
        "retry_counts": {
            "service": 0,
            "branch": 0,
            "body_parts": 0,
            "machine": 0,
            "date": 0,
            "time": 0,
            "confirmation": 0,
        },
        "updated_fields_last_turn": [],
        "last_log": [],
    }


def fsm_enabled() -> bool:
    return getattr(config, "BOOKING_FSM_ENABLED", True)


def require_final_confirmation() -> bool:
    return getattr(config, "BOOKING_FSM_REQUIRE_CONFIRMATION", True)


def set_session_context(
    user_id: str,
    gender: str,
    phone: str,
    *,
    customer_display_name: str | None = None,
    crm_customer_file: bool = False,
    customer_id: str | None = None,
) -> None:
    fsm = _fsm_root(user_id)
    lf = fsm.setdefault("locked_fields", {})
    if customer_id is not None and str(customer_id).strip():
        fsm["customer_id"] = str(customer_id).strip()
    # Only persist real genders — avoid storing the string "unknown" and confusing the model
    if gender in ("male", "female"):
        fsm["customer_gender"] = gender
        if crm_customer_file:
            lf["customer_gender"] = "crm"
    if phone:
        fsm["customer_phone"] = str(phone).strip()
    if customer_display_name and str(customer_display_name).strip():
        fsm["customer_name"] = str(customer_display_name).strip()
        if crm_customer_file:
            lf["customer_name"] = "crm"
    fsm["crm_customer_file"] = bool(crm_customer_file)
    if crm_customer_file:
        fsm["crm_profile_applied"] = True


def lock_field(fsm: dict[str, Any], field: str, source: str) -> None:
    fsm.setdefault("locked_fields", {})[field] = source


def lock_gender_from_user_message(user_id: str, gender: str) -> None:
    if gender not in ("male", "female"):
        return
    fsm = _fsm_root(user_id)
    if fsm.get("locked_fields", {}).get("customer_gender") == "crm":
        return
    fsm["customer_gender"] = gender
    lock_field(fsm, "customer_gender", "user_message")


def lock_gender_from_session(user_id: str, gender: str, source: str = "model_output") -> None:
    """Persist model/session gender into FSM when CRM did not already lock it."""
    if gender not in ("male", "female"):
        return
    fsm = _fsm_root(user_id)
    if fsm.get("locked_fields", {}).get("customer_gender") == "crm":
        return
    fsm["customer_gender"] = gender
    lock_field(fsm, "customer_gender", source)


def _crm_exists_for_user(user_id: str, fsm: dict[str, Any]) -> bool:
    return bool(fsm.get("crm_customer_file")) or bool(
        config.user_data_whatsapp.get(user_id, {}).get("crm_customer_exists")
    )


def _name_satisfied(fsm: dict[str, Any], user_id: str) -> bool:
    if _crm_exists_for_user(user_id, fsm):
        return True
    if fsm.get("locked_fields", {}).get("customer_name"):
        return True
    un = (config.user_names.get(user_id) or "").strip()
    ph = {"client", "unknown", "unknown customer", "test user"}
    nl = un.lower()
    return bool(un and un != "client" and nl not in ph and not nl.startswith("test user"))


def _gender_satisfied(fsm: dict[str, Any], user_id: str, current_gender: str) -> bool:
    if _crm_exists_for_user(user_id, fsm):
        return True
    if fsm.get("locked_fields", {}).get("customer_gender"):
        return True
    g = fsm.get("customer_gender") or current_gender
    return g in ("male", "female")


def identity_missing(fsm: dict[str, Any], user_id: str, current_gender: str) -> list[str]:
    """New customers only: name + gender required before slot collection policy."""
    if _crm_exists_for_user(user_id, fsm):
        return []
    miss: list[str] = []
    if not _name_satisfied(fsm, user_id):
        miss.append("customer_name")
    if not _gender_satisfied(fsm, user_id, current_gender):
        miss.append("customer_gender")
    return miss


def log_fsm(user_id: str, event: str, payload: dict[str, Any] | None = None) -> None:
    line = {
        "event": event,
        "user_id": user_id,
        "payload": payload or {},
    }
    try:
        s = json.dumps(line, default=str, ensure_ascii=False)[:10000]
    except (TypeError, ValueError):
        s = str(line)[:10000]
    print(f"[BOOKING_FSM] {s}")
    fsm = _fsm_root(user_id)
    log = fsm.setdefault("last_log", [])
    log.append(line)
    if len(log) > 30:
        del log[:-30]


def combined_user_text_for_fsm(user_input: str | None) -> str:
    """
    Merge main message + any [User clarified: ...] blocks so Franco stubs + clarification
    still trigger booking mode and body-area detection (e.g. Ok + clarified «tizeh»).
    """
    raw = (user_input or "").strip()
    if not raw:
        return ""
    parts: list[str] = [raw]
    for m in re.finditer(r"\[User clarified:\s*(.+?)\]", raw, flags=re.IGNORECASE | re.DOTALL):
        inner = (m.group(1) or "").strip()
        if inner:
            parts.append(inner.split("\n")[0].strip())
    return "\n".join(parts)


def detect_booking_intent_message(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    return bool(_BOOKING_ENTRY_RE.search(text))


def detect_cancel_intent(text: str) -> bool:
    if not text:
        return False
    return bool(_CANCEL_RE.search(text))


def detect_affirmative_short(text: str) -> bool:
    t = (text or "").strip()
    if len(t) > 120:
        return False
    return bool(_AFFIRM_RE.match(t))


def detect_negative_short(text: str) -> bool:
    t = (text or "").strip()
    if len(t) > 80:
        return False
    return bool(_NEGATIVE_RE.match(t))


def enter_booking_mode(user_id: str, reason: str = "intent_detected") -> None:
    fsm = _fsm_root(user_id)
    if fsm.get("active"):
        return
    fsm["active"] = True
    fsm["booking_status"] = "collecting"
    fsm["confirmation_status"] = "none"
    fsm["execution_allowed"] = False
    log_fsm(user_id, "enter_booking_mode", {"reason": reason})


def exit_booking_mode(user_id: str, reason: str) -> None:
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    fsm["active"] = False
    fsm["booking_status"] = "idle"
    fsm["execution_allowed"] = False
    fsm["confirmation_status"] = "none"
    log_fsm(user_id, "exit_booking_mode", {"reason": reason})


def maybe_enter_booking_mode(user_id: str, user_input: str) -> None:
    if not fsm_enabled():
        return
    combined = combined_user_text_for_fsm(user_input)
    if detect_booking_intent_message(combined):
        enter_booking_mode(user_id, "keyword")


def maybe_exit_booking_mode(user_id: str, user_input: str) -> None:
    if not fsm_enabled():
        return
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    if detect_cancel_intent(user_input) and fsm.get("booking_status") != "completed":
        exit_booking_mode(user_id, "user_cancel")


def infer_body_area_from_user_message(user_id: str, user_input: str) -> None:
    """
    Mark body areas as already described from NL so we do not re-ask the same question.
    Bikini + buttocks (تيز/مؤخرة) are one commercial package — do not split in bot_reply.
    """
    if not fsm_enabled():
        return
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    t = combined_user_text_for_fsm(user_input).strip()
    if not t:
        return
    if _BODY_AREA_MENTION_RE.search(t):
        fsm["body_area_already_described"] = True
        log_fsm(user_id, "body_area_nl_detected", {"excerpt": t[:200]})
    # Bikini line / tize / buttocks: same package (front+back coverage) — never ask «بكيني ولا تيز» as two separate products
    if re.search(
        r"(?i)(بكيني|بيكيني|bikini).{0,40}(تيز|طيز|مؤخرة|tizeh?|butt)|(تيز|طيز|مؤخرة|tizeh?|butt).{0,40}(بكيني|بيكيني|bikini)",
        t,
    ) or re.search(r"(?i)(بكيني\s*و\s*مؤخرة|مؤخرة\s*و\s*بكيني|bikini\s*\+\s*butt|تيز\s*و\s*بكيني)", t):
        fsm["bikini_tize_single_package"] = True
        fsm["body_area_already_described"] = True
