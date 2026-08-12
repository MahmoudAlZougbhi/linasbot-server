"""Legacy GPT chat-response helpers group 1."""

from __future__ import annotations

import asyncio
import datetime
import json
import re
from typing import Any

import config
from services.chat_response_service_constants import (
    _EXCLUDED_RESCHEDULE_SUMMARY_STATUSES,
    _PAUSED_LIKE_STATUS_NORMALIZED,
    _TOOL_ROUND_ARGS_MAX,
    _TOOL_ROUND_RESPONSE_MAX,
)
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
    merge_conversation_user_id_variants,
)


def _record_tool_round_trip(
    function_name: str,
    function_args: Any,
    tool_content: str,
    parsed_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    rec: dict[str, Any] = {
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

def _normalize_profile_gender(value: Any) -> str | None:
    """Normalize user-facing gender words to the backend profile values."""
    s = str(value or "").strip().lower()
    if not s:
        return None
    male_values = {"male", "m", "man", "boy", "ذكر", "رجل", "شب", "zakar", "shab", "sabe", "sabi"}
    female_values = {"female", "f", "woman", "girl", "أنثى", "انثى", "بنت", "صبية", " بنت", "bent", "sabeye", "sabye"}
    if s in male_values:
        return "male"
    if s in female_values:
        return "female"
    return None

def _validate_profile_name(value: Any) -> tuple[str | None, str | None]:
    """Return (clean_name, error) for a user-requested profile name change."""
    name = str(value or "").strip()
    if not name:
        return None, None
    name_pattern = r"^[A-Za-z\u00C0-\u00FF\u0600-\u06FF\s\-\']+$"
    if not (2 <= len(name) <= 50):
        return None, "name_length_invalid"
    if not re.match(name_pattern, name, re.UNICODE):
        return None, "name_characters_invalid"
    return name, None

async def _update_profile_name_in_firestore(user_id: str, name: str, phone_number: str | None) -> int:
    """Persist a profile name on all known user-id variants we can safely resolve."""
    db = get_firestore_db()
    if not db:
        return 0
    app_id = "linas-ai-bot-backend"
    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, phone_number)
    users_coll = db.collection("artifacts").document(app_id).collection("users")
    updated = 0
    for uid in merge_conversation_user_id_variants(user_id, canonical_user_id):
        if not uid:
            continue
        user_doc_ref = users_coll.document(uid)
        payload: dict[str, Any] = {
            "user_id": uid,
            "name": name,
            "last_updated": datetime.datetime.now(),
            "last_activity": datetime.datetime.now(),
        }
        try:
            snap = await asyncio.to_thread(user_doc_ref.get)
            if snap.exists:
                await asyncio.to_thread(user_doc_ref.update, payload)
            else:
                payload["created_at"] = datetime.datetime.now()
                await asyncio.to_thread(user_doc_ref.set, payload)
            updated += 1
        except Exception as exc:
            print(f"⚠️ update profile name failed for {uid}: {exc}")
    return updated

async def _update_current_conversation_customer_info(
    user_id: str,
    conversation_id: str | None,
    *,
    name: str | None = None,
    gender: str | None = None,
    phone_number: str | None = None,
) -> int:
    """Keep dashboard customer_info aligned after explicit profile corrections."""
    db = get_firestore_db()
    if not db or not conversation_id:
        return 0
    app_id = "linas-ai-bot-backend"
    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, phone_number)
    users_coll = db.collection("artifacts").document(app_id).collection("users")
    updated = 0
    for uid in merge_conversation_user_id_variants(user_id, canonical_user_id):
        ref = users_coll.document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        try:
            snap = await asyncio.to_thread(ref.get)
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            customer_info = dict(data.get("customer_info") or {})
            if name:
                customer_info["name"] = name
            if gender:
                customer_info["gender"] = gender
                customer_info["greeting_stage"] = 2
            await asyncio.to_thread(
                ref.update,
                {
                    "customer_info": customer_info,
                    "last_updated": datetime.datetime.now(),
                },
            )
            updated += 1
        except Exception as exc:
            print(f"⚠️ update conversation customer_info failed for {uid}/{conversation_id}: {exc}")
    return updated

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

def _extract_appointment_id_from_check_response(response: dict) -> int | None:
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

def _filter_appointments_for_reschedule_overview(appointments: list[dict]) -> list[dict]:
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
    bits: list[str] = []
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
    area_labels: list[str] = []
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

