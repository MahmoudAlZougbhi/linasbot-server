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
_BOOKING_ENTRY_RE = re.compile(
    r"(?i)\b("
    r"book|booking|appointment|reserve|reservation|schedule|حجز|موعد|مواعيد|"
    r"احجز|بدي موعد|عندي موعد|جلسة|جلسات|session"
    r")\b"
)
_CANCEL_RE = re.compile(
    r"(?i)\b(cancel|stop|never\s*mind|الغاء|الغي|ما بدي|بطلت|لغيت)\b"
)

# User already named body areas (Lebanese/Arabic/Franco) — do not ask again in chat.
_BODY_AREA_MENTION_RE = re.compile(
    r"(?i)(بكيني|بيكيني|bikini|تيز|tize|طيز|مؤخرة|مؤخره|ورا|خلفي|قدام|حماس|"
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


def _fsm_root(user_id: str) -> Dict[str, Any]:
    st = config.user_booking_state[user_id]
    if "booking_fsm" not in st or not isinstance(st.get("booking_fsm"), dict):
        st["booking_fsm"] = new_fsm_state()
    return st["booking_fsm"]


def new_fsm_state() -> Dict[str, Any]:
    return {
        "intent": "book_appointment",
        "active": False,
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


def set_session_context(user_id: str, gender: str, phone: str) -> None:
    fsm = _fsm_root(user_id)
    if gender:
        fsm["customer_gender"] = gender
    if phone:
        fsm["customer_phone"] = str(phone).strip()


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
    if detect_booking_intent_message(user_input):
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
    t = (user_input or "").strip()
    if not t:
        return
    if _BODY_AREA_MENTION_RE.search(t):
        fsm["body_area_already_described"] = True
        log_fsm(user_id, "body_area_nl_detected", {"excerpt": t[:200]})
    # Bikini line / tize / buttocks: same package (front+back coverage) — never ask «بكيني ولا تيز» as two separate products
    if re.search(
        r"(?i)(بكيني|بيكيني|bikini).{0,40}(تيز|طيز|مؤخرة|tize|butt)|(تيز|طيز|مؤخرة|tize|butt).{0,40}(بكيني|بيكيني|bikini)",
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
    gender = fsm.get("customer_gender") or "unknown"
    ok, _missing = fields_complete(fsm, gender)
    if not ok:
        if fsm.get("booking_status") == "awaiting_confirmation":
            fsm["booking_status"] = "collecting"
            fsm["confirmation_status"] = "none"
        return
    if ok and fsm.get("booking_status") in ("collecting", None, "idle"):
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


def first_missing_field(fsm: Dict[str, Any], gender: str) -> Optional[str]:
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


def first_missing_field_for_user_chat(fsm: Dict[str, Any], gender: str) -> Optional[str]:
    """
    Same as first_missing_field but skips re-asking body_part_ids when the user already
    described areas in natural language — model must map via get_body_parts instead.
    """
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
    g = fsm.get("customer_gender") or current_gender
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


def build_prompt_block(user_id: str, current_gender: str) -> str:
    if not fsm_enabled():
        return ""
    fsm = _fsm_root(user_id)
    if not fsm.get("active"):
        return ""
    sync_from_flat_booking_state(user_id)
    g = fsm.get("customer_gender") or current_gender
    ok, miss = fields_complete(fsm, g)
    nxt = first_missing_field(fsm, g) if not ok else None
    nxt_user = first_missing_field_for_user_chat(fsm, g) if not ok else None
    can_ex, gate_reason = can_execute_submit(user_id, current_gender)
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
        )
    }
    lines = [
        "**BOOKING MODE (STRICT — server state machine)**",
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
                if (not ok and "body_part_ids" in miss and fsm.get("body_area_already_described"))
                else ("(none — awaiting confirmation or ready)" if ok else "(see missing fields)")
            )
        ),
        "- Fields still missing: " + (", ".join(miss) if miss else "(none)"),
        "- Gate for tool execution: "
        + ("READY" if can_ex else f"BLOCKED ({gate_reason})"),
        "",
        "BOOKING_STATE_JSON:",
        json.dumps(snap, ensure_ascii=False, default=str),
        "",
        "Emit optional `booking_fsm_patch` in your JSON with updated fields when the user provides them "
        '(e.g. {"service_id":12,"branch_id":1}). Set `"confirmed_booking": true` only after the user explicitly '
        "confirms the final summary.",
    ]
    return "\n".join(lines)


def record_decision_log(
    user_id: str,
    *,
    phase: str,
    next_field: Optional[str],
    gate: str,
    extracted: Optional[Dict[str, Any]] = None,
) -> None:
    log_fsm(
        user_id,
        "turn_decision",
        {
            "phase": phase,
            "first_missing_field": next_field,
            "gate": gate,
            "extracted": extracted or {},
        },
    )
