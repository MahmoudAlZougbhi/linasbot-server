"""Booking FSM merge/sync/gate helpers (LOC split)."""

from __future__ import annotations

from typing import Any

import config
from services.booking.constants import (
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    _service_requires_machine,
)
from services.booking.booking_fsm_detect import (
    _fsm_root,
    detect_affirmative_short,
    detect_negative_short,
    fsm_enabled,
    identity_missing,
    log_fsm,
    require_final_confirmation,
)

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


def invalidate_dependents(fsm: dict[str, Any], changed: str) -> None:
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


def merge_patch(user_id: str, patch: dict[str, Any]) -> list[str]:
    """Merge GPT-provided booking_fsm_patch. Returns list of field keys updated."""
    if not patch or not isinstance(patch, dict):
        return []
    fsm = _fsm_root(user_id)
    updated: list[str] = []
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
    function_args: dict[str, Any],
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


def fields_complete(fsm: dict[str, Any], gender: str) -> tuple[bool, list[str]]:
    missing: list[str] = []
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


def first_missing_field(fsm: dict[str, Any], gender: str, user_id: str) -> str | None:
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


def first_missing_field_for_user_chat(fsm: dict[str, Any], gender: str, user_id: str) -> str | None:
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


def can_execute_submit(user_id: str, current_gender: str) -> tuple[bool, str]:
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


def parse_gate_reason(gate_reason: str) -> list[str]:
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
        return "الحجز لم يُنفَّذ: لازم تأكيد واحد من الزبون بعد الملخص قبل استدعاء submit_booking_intent."
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
