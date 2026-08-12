"""
Deterministic booking state machine (server-side).

Persists under config.user_booking_state[user_id]["booking_fsm"].
When BOOKING_FSM_ENABLED, submit_booking_intent is blocked until required fields
are collected and the user has confirmed once (execution_allowed).
"""

from __future__ import annotations

import json
import re
from typing import Any

import config
from services.booking.booking_fsm_detect import (  # noqa: F401
    _AFFIRM_RE,
    _BODY_AREA_MENTION_RE,
    _BOOKING_ENTRY_RE,
    _CANCEL_RE,
    _GENDER_RECONFIRM_RE,
    _NEGATIVE_RE,
    _crm_exists_for_user,
    _fsm_root,
    _gender_satisfied,
    _name_satisfied,
    combined_user_text_for_fsm,
    detect_affirmative_short,
    detect_booking_intent_message,
    detect_cancel_intent,
    detect_negative_short,
    enter_booking_mode,
    exit_booking_mode,
    fsm_enabled,
    identity_missing,
    infer_body_area_from_user_message,
    lock_field,
    lock_gender_from_session,
    lock_gender_from_user_message,
    log_fsm,
    maybe_enter_booking_mode,
    maybe_exit_booking_mode,
    new_fsm_state,
    require_final_confirmation,
    set_session_context,
)
from services.booking.booking_fsm_merge import (  # noqa: F401
    apply_heuristic_confirmation,
    can_execute_submit,
    fields_complete,
    first_missing_field,
    first_missing_field_for_user_chat,
    human_gate_message,
    invalidate_dependents,
    mark_booking_completed,
    merge_patch,
    parse_gate_reason,
    recompute_confirmation_gate,
    sync_from_flat_booking_state,
    sync_from_tool_call,
)


def build_unified_booking_snapshot(
    user_id: str,
    current_gender: str,
    *,
    customer_exists: bool,
    customer_id: str | None,
    name_is_known: bool,
    crm_data_used: bool,
) -> dict[str, Any]:
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
        or ("crm" if customer_exists and g in ("male", "female") else ("session" if g in ("male", "female") else None)),
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
) -> tuple[str, dict[str, Any]]:
    """Remove gender re-confirmation lines when gender is already known (logic-level anti-loop)."""
    fsm = _fsm_root(user_id)
    meta: dict[str, Any] = {"guard_applied": False}
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
        f"- **SERVER-KNOWN PROFILE (authoritative):** Name: {_name_line} | Gender on server: {_gender_line}",
        "- Collect **only remaining** booking facts (service/branch/areas/machine/date/time per BOOKING STATE); "
        "merge into tools / `booking_fsm_patch`. **Do not** re-verify identity when the line above already has name or gender.",
        "- You are in **booking mode**. Replies must be **short**. Ask **only one** clear question per message.",
        "- **Do not** re-ask for fields already set in BOOKING STATE below.",
        "- **Body areas (Arabic):** If the user already said which areas (e.g. بكيني، مؤخرة، تيز، إبط…), **do not ask again** which area. "
        "Call `get_body_parts` and map their words to CRM ids; put them in `submit_booking_intent.body_part_ids`.",
        "- **Franco Lebanese (server + CRM mapping):** **tize / tizeh / teze / teiz** = مؤخرة/طيز — same **bikini-line package** as Arabic **تيز/مؤخرة**. "
        "Resolve with **`get_body_parts`** to the **Bikini** (or equivalent) row; pass **`body_part_ids`** in **`submit_booking_intent`**. **Never** drop or ignore this wording from the user message.",
        "- **Forbidden in bot_reply to customers:** asking again for the same body area, or stiff wording like «منطقة من النظام» / «رقم المنطقة» / «قطعة الجسم الدقيقة» / «أي جزء». "
        "If you must ask once (only when nothing was said yet), use natural Arabic e.g. «شو المناطق يلي بدك ياها للجلسة؟» or «أي مناطق بالجسم بدك تعمليها؟».",
        "- **Bikini + buttocks (تيز/مؤخرة):** One package (front + back intimate line). "
        "If the user said تيز or مؤخرة or بكيني (or any mix), treat as **one booking intent** — do **not** ask «بكيني فقط ولا مع المؤخرة؟» or «بكيني ولا تيز»; map with `get_body_parts` and continue.",
        "- **Do not** repeat confirmation. If `execution_allowed` is true, you may call `submit_booking_intent` in this turn.",
        "- If the user's current message already contains all booking details and clearly asks to book/execute/check availability, call `submit_booking_intent` with every extracted field now; the backend may auto-confirm complete one-message booking payloads.",
        "- If details are incomplete or ambiguous and `booking_status` is `awaiting_confirmation` with `execution_allowed` false: send **one** summary and ask yes/no only.",
        "- Use **only** IDs returned by your tools (services, branches, machines, body_parts). Never invent IDs.",
        "- Next field still missing internally (includes CRM ids): "
        + (nxt or "(none — awaiting confirmation or ready)"),
        "- **Next question to ask the user** (skips re-asking body areas if already described in chat): "
        + (
            nxt_user
            if nxt_user is not None
            else (
                "(use get_body_parts to map areas — do not ask the user again)"
                if (not ok_all and "body_part_ids" in miss_all and fsm.get("body_area_already_described"))
                else ("(none — awaiting confirmation or ready)" if ok_all else "(see missing fields)")
            )
        ),
        "- Fields still missing (identity + booking): " + (", ".join(miss_all) if miss_all else "(none)"),
        "- Gate for tool execution: " + ("READY" if can_ex else f"BLOCKED ({gate_reason})"),
        "",
        "BOOKING_STATE_JSON:",
        json.dumps(snap, ensure_ascii=False, default=str),
        "",
        "UNIFIED_BOOKING_STATE_JSON (server memory — merge updates each turn; do not re-ask locked fields):",
        json.dumps(unified, ensure_ascii=False, default=str),
        "",
        "Emit optional `booking_fsm_patch` in your JSON with updated fields when the user provides them "
        '(e.g. {"service_id":12,"branch_id":1}). Set `"confirmed_booking": true` after the user explicitly '
        "confirms the final summary, or when the same current user message already provided all required booking details and asked you to book/execute.",
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
    next_field: str | None,
    gate: str,
    extracted: dict[str, Any] | None = None,
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
