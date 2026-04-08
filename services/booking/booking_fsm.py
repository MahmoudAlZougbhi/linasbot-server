# -*- coding: utf-8 -*-
"""
Deterministic booking state machine (server-side).

Persists under config.user_booking_state[user_id]["booking_fsm"].
When BOOKING_FSM_ENABLED, submit_booking_intent is blocked until required fields
are collected and the user has confirmed once (execution_allowed).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import config
from services.booking.constants import DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS
from services.booking.intent_pipeline import _service_requires_machine

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
_CANCEL_RE = re.compile(
    r"(?i)\b(cancel|stop|never\s*mind|الغاء|الغي|ما بدي|بطلت|لغيت)\b"
)

# User already named body areas (Lebanese/Arabic/Franco) — do not ask again in chat.
_BODY_AREA_MENTION_RE = re.compile(
    r"(?i)(بكيني|بيكيني|bikini|تيز|tizeh?|طيز|مؤخرة|مؤخره|ورا|خلفي|قدام|حماس|"
    r"إبط|ابط|ابط|رجل|رجلين|وجه|وش|صدر|ظهر|bikini|butt|underarm|leg|face)",
    re.UNICODE,
)

# Short affirmative / negative (confirmation step)
_AFFIRM_RE = re.compile(
    r"(?i)^\s*("
    r"ok|okay|yes|yeah|yep|sure|deal|done|confirm|neo|quadro|candela|trio|"
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


def _fsm_root(user_id: str) -> Dict[str, Any]:
    st = config.user_booking_state[user_id]
    if "booking_fsm" not in st or not isinstance(st.get("booking_fsm"), dict):
        st["booking_fsm"] = new_fsm_state()
    return st["booking_fsm"]


def new_fsm_state() -> Dict[str, Any]:
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
    customer_display_name: Optional[str] = None,
    crm_customer_file: bool = False,
    customer_id: Optional[str] = None,
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


def lock_field(fsm: Dict[str, Any], field: str, source: str) -> None:
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


def _crm_exists_for_user(user_id: str, fsm: Dict[str, Any]) -> bool:
    return bool(fsm.get("crm_customer_file")) or bool(
        config.user_data_whatsapp.get(user_id, {}).get("crm_customer_exists")
    )


def _name_satisfied(fsm: Dict[str, Any], user_id: str) -> bool:
    if _crm_exists_for_user(user_id, fsm):
        return True
    if fsm.get("locked_fields", {}).get("customer_name"):
        return True
    un = (config.user_names.get(user_id) or "").strip()
    ph = {"client", "unknown", "unknown customer", "test user"}
    nl = un.lower()
    return bool(un and un != "client" and nl not in ph and not nl.startswith("test user"))


def _gender_satisfied(fsm: Dict[str, Any], user_id: str, current_gender: str) -> bool:
    if _crm_exists_for_user(user_id, fsm):
        return True
    if fsm.get("locked_fields", {}).get("customer_gender"):
        return True
    g = fsm.get("customer_gender") or current_gender
    return g in ("male", "female")


def identity_missing(fsm: Dict[str, Any], user_id: str, current_gender: str) -> List[str]:
    """New customers only: name + gender required before slot collection policy."""
    if _crm_exists_for_user(user_id, fsm):
        return []
    miss: List[str] = []
    if not _name_satisfied(fsm, user_id):
        miss.append("customer_name")
    if not _gender_satisfied(fsm, user_id, current_gender):
        miss.append("customer_gender")
    return miss


def log_fsm(user_id: str, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
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


def combined_user_text_for_fsm(user_input: Optional[str]) -> str:
    """
    Merge main message + any [User clarified: ...] blocks so Franco stubs + clarification
    still trigger booking mode and body-area detection (e.g. Ok + clarified «tizeh»).
    """
    raw = (user_input or "").strip()
    if not raw:
        return ""
    parts: List[str] = [raw]
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


def apply_heuristic_confirmation(user_id: str, user_input: str) -> None:
    """If awaiting confirmation and user sends a short yes, allow execution."""
    if not fsm_enabled():
        return
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    if fsm.get("booking_status") != "awaiting_confirmation":
        return
    if detect_affirmative_short(user_input):
        fsm["execution_allowed"] = True
        fsm["confirmation_status"] = "confirmed"
        fsm["booking_status"] = "ready_to_execute"
        log_fsm(user_id, "confirmation_heuristic_yes", {})
    elif detect_negative_short(user_input):
        fsm["execution_allowed"] = False
        fsm["confirmation_status"] = "rejected"
        fsm["booking_status"] = "collecting"
        log_fsm(user_id, "confirmation_heuristic_no", {})


def invalidate_dependents(fsm: Dict[str, Any], changed: str) -> None:
    ch = (changed or "").lower()
    if ch == "service_id":
        fsm["body_part_ids"] = []
        fsm["body_part_names"] = []
        fsm["body_area_already_described"] = False
        fsm["bikini_tize_single_package"] = False
        fsm["machine_id"] = None
        fsm["machine_name"] = None
        fsm["appointment_date"] = None
        fsm["appointment_time"] = None
        fsm["slot_id"] = None
        fsm["execution_allowed"] = False
        fsm["confirmation_status"] = "none"
    elif ch == "branch_id":
        fsm["appointment_date"] = None
        fsm["appointment_time"] = None
        fsm["slot_id"] = None
        fsm["machine_id"] = None
        fsm["machine_name"] = None
        fsm["execution_allowed"] = False
        fsm["confirmation_status"] = "none"
    elif ch in ("appointment_date", "date"):
        fsm["appointment_time"] = None
        fsm["slot_id"] = None
        fsm["execution_allowed"] = False
        fsm["confirmation_status"] = "none"


def merge_patch(user_id: str, patch: Dict[str, Any]) -> List[str]:
    """Merge GPT-provided booking_fsm_patch. Returns list of field keys updated."""
    if not patch or not isinstance(patch, dict):
        return []
    fsm = _fsm_root(user_id)
    updated: List[str] = []
    lf = fsm.setdefault("locked_fields", {})
    key_map = {
        "service_id": "service_id",
        "service_name": "service_name",
        "branch_id": "branch_id",
        "branch_name": "branch_name",
        "machine_id": "machine_id",
        "machine_name": "machine_name",
        "body_part_ids": "body_part_ids",
        "body_part_names": "body_part_names",
        "appointment_date": "appointment_date",
        "appointment_time": "appointment_time",
        "slot_id": "slot_id",
        "customer_name": "customer_name",
        "customer_gender": "customer_gender",
        "confirmed_booking": "_confirmed_booking",
        "confirmation_accepted": "_confirmed_booking",
    }
    for pk, fk in key_map.items():
        if pk not in patch:
            continue
        val = patch[pk]
        if fk == "_confirmed_booking":
            if val is True:
                fsm["execution_allowed"] = True
                fsm["confirmation_status"] = "confirmed"
                fsm["booking_status"] = "ready_to_execute"
                updated.append("confirmation")
            continue
        if fk == "customer_gender" and val is not None:
            gs = str(val).strip().lower()
            if gs in ("male", "female"):
                if lf.get("customer_gender") == "crm":
                    log_fsm(
                        user_id,
                        "merge_patch_skipped_locked",
                        {"field": "customer_gender", "reason": "crm_lock"},
                    )
                    continue
                fsm["customer_gender"] = gs
                lf["customer_gender"] = "patch"
                updated.append(fk)
            continue
        if fk == "customer_name" and val is not None and str(val).strip():
            if lf.get("customer_name") == "crm":
                log_fsm(
                    user_id,
                    "merge_patch_skipped_locked",
                    {"field": "customer_name", "reason": "crm_lock"},
                )
                continue
            fsm["customer_name"] = str(val).strip()
            lf["customer_name"] = "patch"
            updated.append(fk)
            continue
        if fk == "body_part_ids" and val is not None:
            if isinstance(val, list):
                fsm[fk] = []
                for x in val:
                    try:
                        fsm[fk].append(int(x))
                    except (TypeError, ValueError):
                        continue
                if fsm[fk]:
                    fsm["body_area_already_described"] = True
            updated.append(fk)
            continue
        old = fsm.get(fk)
        if val is not None and val != "" and val != old:
            if fk in ("service_id", "branch_id", "machine_id"):
                try:
                    nv = int(val)
                except (TypeError, ValueError):
                    continue
                if fk == "service_id" and fsm.get("service_id") != nv:
                    invalidate_dependents(fsm, "service_id")
                if fk == "branch_id" and fsm.get("branch_id") != nv:
                    invalidate_dependents(fsm, "branch_id")
                fsm[fk] = nv
                updated.append(fk)
            else:
                fsm[fk] = val
                updated.append(fk)
    fsm["updated_fields_last_turn"] = updated
    if updated:
        log_fsm(user_id, "merge_patch", {"updated": updated, "patch_keys": list(patch.keys())})
    recompute_confirmation_gate(user_id)
    return updated


def recompute_confirmation_gate(user_id: str) -> None:
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    if fsm.get("execution_allowed") or fsm.get("booking_status") == "ready_to_execute":
        return
    cur_g = config.user_gender.get(user_id, "unknown")
    id_m = identity_missing(fsm, user_id, cur_g)
    ok_slots, _missing_slots = fields_complete(fsm, cur_g)
    ok_all = (not id_m) and ok_slots
    if not ok_all:
        if fsm.get("booking_status") == "awaiting_confirmation":
            fsm["booking_status"] = "collecting"
            fsm["confirmation_status"] = "none"
        return
    if ok_all and fsm.get("booking_status") in ("collecting", None, "idle"):
        fsm["booking_status"] = "awaiting_confirmation"
        fsm["confirmation_status"] = "pending"
        fsm["execution_allowed"] = False
        log_fsm(user_id, "gate_awaiting_confirmation", {})


def sync_from_flat_booking_state(user_id: str) -> None:
    """Copy legacy user_booking_state keys into FSM."""
    st = config.user_booking_state.get(user_id) or {}
    fsm = _fsm_root(user_id)
    for k in ("service_id", "branch_id", "machine_id", "appointment_date", "appointment_time"):
        if st.get(k) is not None:
            try:
                if k in ("service_id", "branch_id", "machine_id"):
                    fsm[k] = int(st[k])
                else:
                    fsm[k] = str(st[k]).strip()
            except (TypeError, ValueError):
                pass
    if st.get("body_part_ids") is not None and isinstance(st.get("body_part_ids"), list):
        fsm["body_part_ids"] = list(st["body_part_ids"])
        if fsm["body_part_ids"]:
            fsm["body_area_already_described"] = True
    li = st.get("last_booking_intent")
    if isinstance(li, dict) and str(li.get("body_part") or "").strip():
        fsm["body_area_already_described"] = True
    if str(st.get("body_part") or "").strip():
        fsm["body_area_already_described"] = True


def sync_from_tool_call(
    user_id: str,
    tool_name: str,
    function_args: Dict[str, Any],
    tool_output: Any,
) -> None:
    if not fsm_enabled():
        return
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return
    fa = dict(function_args or {})
    if tool_name in ("get_services",):
        pass
    if tool_name in ("submit_booking_intent", "create_appointment"):
        for k in ("service_id", "branch_id", "machine_id"):
            if fa.get(k) is not None:
                try:
                    fsm[k] = int(fa[k])
                except (TypeError, ValueError):
                    pass
        if fa.get("body_part_ids"):
            bp = fa.get("body_part_ids")
            if isinstance(bp, list):
                fsm["body_part_ids"] = [int(x) for x in bp if x is not None]
        ds = str(fa.get("date") or "").strip()
        if ds:
            if " " in ds or "T" in ds.lower():
                parts = ds.replace("T", " ").split()
                fsm["appointment_date"] = parts[0][:10]
                if len(parts) > 1:
                    fsm["appointment_time"] = parts[1][:8]
            else:
                fsm["appointment_date"] = ds[:10]
        if fa.get("time") and not fsm.get("appointment_time"):
            fsm["appointment_time"] = str(fa["time"]).strip()[:16]
        log_fsm(user_id, "sync_from_submit_args", {"keys": list(fa.keys())})


def fields_complete(fsm: Dict[str, Any], gender: str) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    sid = fsm.get("service_id")
    bid = fsm.get("branch_id")
    if sid is None:
        missing.append("service_id")
    if bid is None:
        missing.append("branch_id")
    svc_id = int(sid) if sid is not None else None
    if svc_id is not None and svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS:
        bp = fsm.get("body_part_ids") or []
        if not bp:
            missing.append("body_part_ids")
    if svc_id is not None and _service_requires_machine(svc_id):
        if fsm.get("machine_id") is None:
            missing.append("machine_id")
    if not fsm.get("appointment_date"):
        missing.append("appointment_date")
    if not fsm.get("appointment_time"):
        missing.append("appointment_time")
    return (len(missing) == 0, missing)


def first_missing_field(fsm: Dict[str, Any], gender: str, user_id: str) -> Optional[str]:
    id_m = identity_missing(fsm, user_id, gender)
    if "customer_name" in id_m:
        return "customer_name"
    if "customer_gender" in id_m:
        return "customer_gender"
    ok, miss = fields_complete(fsm, gender)
    if ok:
        return None
    order = [
        "service_id",
        "branch_id",
        "body_part_ids",
        "machine_id",
        "appointment_date",
        "appointment_time",
    ]
    for f in order:
        if f in miss:
            return f
    return miss[0] if miss else None


def first_missing_field_for_user_chat(fsm: Dict[str, Any], gender: str, user_id: str) -> Optional[str]:
    """
    Same as first_missing_field but skips re-asking body_part_ids when the user already
    described areas in natural language — model must map via get_body_parts instead.
    """
    id_m = identity_missing(fsm, user_id, gender)
    if "customer_name" in id_m:
        return "customer_name"
    if "customer_gender" in id_m:
        return "customer_gender"
    ok, miss = fields_complete(fsm, gender)
    if ok:
        return None
    order = [
        "service_id",
        "branch_id",
        "body_part_ids",
        "machine_id",
        "appointment_date",
        "appointment_time",
    ]
    for f in order:
        if f not in miss:
            continue
        if f == "body_part_ids" and fsm.get("body_area_already_described"):
            continue
        return f
    if "body_part_ids" in miss and fsm.get("body_area_already_described"):
        for f in order:
            if f in miss and f != "body_part_ids":
                return f
        return None
    return miss[0] if miss else None


def can_execute_submit(user_id: str, current_gender: str) -> Tuple[bool, str]:
    if not fsm_enabled():
        return True, ""
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return True, ""
    _cg = fsm.get("customer_gender")
    if _cg == "unknown":
        _cg = None
    g = _cg or current_gender
    id_m = identity_missing(fsm, user_id, current_gender)
    if id_m:
        return False, f"fsm_incomplete:{','.join(id_m)}"
    ok, miss = fields_complete(fsm, g)
    if not ok:
        return False, f"fsm_incomplete:{','.join(miss)}"
    if not require_final_confirmation():
        return True, ""
    if not fsm.get("execution_allowed"):
        return False, "fsm_confirmation_required"
    return True, ""


def parse_gate_reason(gate_reason: str) -> List[str]:
    if not gate_reason or not str(gate_reason).startswith("fsm_incomplete:"):
        return []
    return [x for x in str(gate_reason).split(":", 1)[1].split(",") if x]


def human_gate_message(gate_reason: str, lang: str) -> str:
    gr = gate_reason or ""
    if gr == "fsm_confirmation_required":
        if (lang or "ar").lower() == "en":
            return (
                "Booking is not executed yet: the user must confirm the summary once "
                "(yes) before submit_booking_intent. Ask one short confirmation, then call the tool."
            )
        return (
            "الحجز لم يُنفَّذ: لازم تأكيد واحد من الزبون بعد الملخص قبل استدعاء submit_booking_intent."
        )
    if gr.startswith("fsm_incomplete"):
        tail = gr.split(":", 1)[1] if ":" in gr else ""
        if (lang or "ar").lower() == "en":
            return (
                "Booking payload incomplete per server state machine. "
                f"Missing: {tail or 'required fields'}. Collect these via tools before submit_booking_intent."
            )
        return (
            "الحجز ناقص حسب نظام الحجز: الحقول المطلوبة غير مكتملة ("
            + (tail or "…")
            + "). أكمل الجمع عبر الأدوات قبل submit_booking_intent."
        )
    return "Booking blocked by server booking state machine."


def mark_booking_completed(user_id: str) -> None:
    fsm = _fsm_root(user_id)
    fsm["booking_status"] = "completed"
    fsm["active"] = False
    fsm["execution_allowed"] = False
    log_fsm(user_id, "booking_completed", {})


def build_unified_booking_snapshot(
    user_id: str,
    current_gender: str,
    *,
    customer_exists: bool,
    customer_id: Optional[str],
    name_is_known: bool,
    crm_data_used: bool,
) -> Dict[str, Any]:
    """Single structured object for prompts + activity logs (session memory)."""
    fsm = _fsm_root(user_id)
    _cg_fsm = fsm.get("customer_gender")
    if _cg_fsm == "unknown":
        _cg_fsm = None
    g = _cg_fsm or current_gender
    id_miss = identity_missing(fsm, user_id, current_gender)
    ok_slots, slot_miss = fields_complete(fsm, g)
    miss_all = list(id_miss) + [x for x in slot_miss if x not in id_miss]
    nxt = first_missing_field_for_user_chat(fsm, g, user_id) if miss_all else None
    can_ex, gate = can_execute_submit(user_id, current_gender)
    lf = dict(fsm.get("locked_fields") or {})
    return {
        "customer_exists": bool(customer_exists),
        "customer_id": customer_id or fsm.get("customer_id"),
        "customer_name": fsm.get("customer_name") or config.user_names.get(user_id),
        "gender": g if g in ("male", "female") else None,
        "customer_name_source": lf.get("customer_name")
        or ("crm" if customer_exists and name_is_known else ("session" if name_is_known else None)),
        "gender_source": lf.get("customer_gender")
        or (
            "crm"
            if customer_exists and g in ("male", "female")
            else ("session" if g in ("male", "female") else None)
        ),
        "gender_question_skipped": bool(customer_exists and g in ("male", "female")),
        "crm_profile_data_used": bool(crm_data_used),
        "service_id": fsm.get("service_id"),
        "service_name": fsm.get("service_name"),
        "body_part_ids": fsm.get("body_part_ids"),
        "machine_id": fsm.get("machine_id"),
        "branch_id": fsm.get("branch_id"),
        "desired_date": fsm.get("appointment_date"),
        "desired_time": fsm.get("appointment_time"),
        "confirmation_required": bool(require_final_confirmation()),
        "confirmation_received": bool(fsm.get("execution_allowed")),
        "missing_fields": miss_all,
        "next_question_target": nxt,
        "booking_status": fsm.get("booking_status"),
        "submit_gate": "ready" if can_ex else gate,
        "locked_fields": lf,
        "slots_complete": ok_slots,
        "identity_complete": not bool(id_miss),
    }


def guard_bot_reply_booking_identity(
    user_id: str,
    bot_reply: str,
    current_gender: str,
    *,
    lang: str = "ar",
) -> Tuple[str, Dict[str, Any]]:
    """Remove gender re-confirmation lines when gender is already known (logic-level anti-loop)."""
    fsm = _fsm_root(user_id)
    meta: Dict[str, Any] = {"guard_applied": False}
    if not fsm.get("active"):
        return bot_reply, meta
    br = (bot_reply or "").strip()
    if not br:
        return bot_reply, meta
    g_eff = (fsm.get("customer_gender") or current_gender or "").strip().lower()
    if g_eff not in ("male", "female"):
        return bot_reply, meta
    if not _GENDER_RECONFIRM_RE.search(br):
        return bot_reply, meta
    cleaned = _GENDER_RECONFIRM_RE.sub("", br)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(re.sub(r"\s+", "", cleaned)) < 12:
        cleaned = (
            "تمام، منكمل بخطوات الحجز حسب اللي ناقص (خدمة، فرع، وقت…)."
            if (lang or "ar").lower() != "en"
            else "OK — let’s continue with the remaining booking details."
        )
    meta["guard_applied"] = True
    meta["reason"] = "gender_reconfirmation_removed"
    log_fsm(user_id, "bot_reply_guard", meta)
    return cleaned, meta


def build_prompt_block(user_id: str, current_gender: str) -> str:
    if not fsm_enabled():
        return ""
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return ""
    sync_from_flat_booking_state(user_id)
    _cg_fsm = fsm.get("customer_gender")
    if _cg_fsm == "unknown":
        _cg_fsm = None
    g = _cg_fsm or current_gender
    _un = (config.user_names.get(user_id) or "").strip()
    _ph = {"client", "unknown", "unknown customer", "test user"}
    _nl = _un.lower()
    _name_ok = _un and _un != "client" and _nl not in _ph and not _nl.startswith("test user")
    _crm = bool(fsm.get("crm_customer_file")) or bool(
        config.user_data_whatsapp.get(user_id, {}).get("crm_customer_exists")
    )
    id_miss = identity_missing(fsm, user_id, current_gender)
    ok_slots, miss = fields_complete(fsm, g)
    miss_all = list(id_miss) + [x for x in miss if x not in id_miss]
    ok_all = (not id_miss) and ok_slots
    nxt = first_missing_field(fsm, g, user_id) if not ok_all else None
    nxt_user = first_missing_field_for_user_chat(fsm, g, user_id) if not ok_all else None
    can_ex, gate_reason = can_execute_submit(user_id, current_gender)
    unified = build_unified_booking_snapshot(
        user_id,
        current_gender,
        customer_exists=bool(_crm),
        customer_id=fsm.get("customer_id"),
        name_is_known=bool(_name_ok),
        crm_data_used=bool(fsm.get("crm_profile_applied")),
    )
    snap = {
        k: fsm.get(k)
        for k in (
            "service_id",
            "branch_id",
            "machine_id",
            "body_part_ids",
            "appointment_date",
            "appointment_time",
            "booking_status",
            "confirmation_status",
            "execution_allowed",
            "body_area_already_described",
            "bikini_tize_single_package",
            "customer_name",
            "crm_customer_file",
            "customer_id",
            "locked_fields",
        )
    }
    g_eff = _cg_fsm or current_gender or "unknown"
    _name_line = (
        f"«{_un}» — **do NOT** ask for full name; use in address."
        if _name_ok
        else (
            "CRM file exists — **do NOT** ask for name (address politely without requesting name)."
            if _crm
            else "(name not on server — ask once only if booking flow still requires it per Style Guide)"
        )
    )
    _gender_line = (
        f"'{g_eff}' — **FORBIDDEN**: ask_gender, «شو جنسك», «للرجال أو للنساء», or any men-vs-women question."
        if g_eff in ("male", "female")
        else f"'{g_eff}' — collect gender only if Style Guide allows (one short question)."
    )
    lines = [
        "**BOOKING MODE (STRICT — server state machine)**",
        "- **SERVER-KNOWN PROFILE (authoritative):** "
        f"Name: {_name_line} | Gender on server: {_gender_line}",
        "- Collect **only remaining** booking facts (service/branch/areas/machine/date/time per BOOKING STATE); "
        "merge into tools / `booking_fsm_patch`. **Do not** re-verify identity when the line above already has name or gender.",
        "- You are in **booking mode**. Replies must be **short**. Ask **only one** clear question per message.",
        "- **Do not** re-ask for fields already set in BOOKING STATE below.",
        "- **Body areas (Arabic):** If the user already said which areas (e.g. بكيني، مؤخرة، تيز، إبط…), **do not ask again** which area. "
        "Call `get_body_parts` and map their words to CRM ids; put them in `submit_booking_intent.body_part_ids`.",
        "- **Forbidden in bot_reply to customers:** asking again for the same body area, or stiff wording like «منطقة من النظام» / «رقم المنطقة» / «قطعة الجسم الدقيقة» / «أي جزء». "
        "If you must ask once (only when nothing was said yet), use natural Arabic e.g. «شو المناطق يلي بدك ياها للجلسة؟» or «أي مناطق بالجسم بدك تعمليها؟».",
        "- **Bikini + buttocks (تيز/مؤخرة):** One package (front + back intimate line). "
        "If the user said تيز or مؤخرة or بكيني (or any mix), treat as **one booking intent** — do **not** ask «بكيني فقط ولا مع المؤخرة؟» or «بكيني ولا تيز»; map with `get_body_parts` and continue.",
        "- **Do not** repeat confirmation. If `execution_allowed` is true, you may call `submit_booking_intent` in this turn.",
        "- If `booking_status` is `awaiting_confirmation` and `execution_allowed` is false: send **one** summary and ask yes/no only. **Do not** call `submit_booking_intent` until the user confirms.",
        "- Use **only** IDs returned by your tools (services, branches, machines, body_parts). Never invent IDs.",
        "- Next field still missing internally (includes CRM ids): "
        + (nxt or "(none — awaiting confirmation or ready)"),
        "- **Next question to ask the user** (skips re-asking body areas if already described in chat): "
        + (
            nxt_user
            if nxt_user is not None
            else (
                "(use get_body_parts to map areas — do not ask the user again)"
                if (
                    not ok_all
                    and "body_part_ids" in miss_all
                    and fsm.get("body_area_already_described")
                )
                else ("(none — awaiting confirmation or ready)" if ok_all else "(see missing fields)")
            )
        ),
        "- Fields still missing (identity + booking): "
        + (", ".join(miss_all) if miss_all else "(none)"),
        "- Gate for tool execution: "
        + ("READY" if can_ex else f"BLOCKED ({gate_reason})"),
        "",
        "BOOKING_STATE_JSON:",
        json.dumps(snap, ensure_ascii=False, default=str),
        "",
        "UNIFIED_BOOKING_STATE_JSON (server memory — merge updates each turn; do not re-ask locked fields):",
        json.dumps(unified, ensure_ascii=False, default=str),
        "",
        "Emit optional `booking_fsm_patch` in your JSON with updated fields when the user provides them "
        '(e.g. {"service_id":12,"branch_id":1}). Set `"confirmed_booking": true` only after the user explicitly '
        "confirms the final summary.",
    ]
    if fsm.get("body_area_already_described"):
        lines.insert(
            7,
            "- **CRITICAL — body_area_already_described is TRUE:** the user already named a zone (incl. Franco **tize/tizeh**, Arabic تيز/مؤخرة/بكيني). "
            "**Do NOT** ask «شو المنطقة بالضبط» or repeat «منطقة». Call `get_body_parts`, map to ids, then ask only what is still missing (usually branch or time).",
        )
    return "\n".join(lines)


def record_decision_log(
    user_id: str,
    *,
    phase: str,
    next_field: Optional[str],
    gate: str,
    extracted: Optional[Dict[str, Any]] = None,
) -> None:
    fsm = _fsm_root(user_id)
    dup = False
    if (
        next_field is not None
        and fsm.get("last_next_question_field") is not None
        and fsm.get("last_next_question_field") == next_field
    ):
        dup = True
        fsm["duplicate_question_detected"] = True
        log_fsm(
            user_id,
            "duplicate_question_warning",
            {"field": next_field, "phase": phase},
        )
    else:
        fsm["duplicate_question_detected"] = False
    fsm["last_next_question_field"] = next_field
    log_fsm(
        user_id,
        "turn_decision",
        {
            "phase": phase,
            "first_missing_field": next_field,
            "gate": gate,
            "duplicate_question_detected": dup,
            "extracted": extracted or {},
        },
    )
