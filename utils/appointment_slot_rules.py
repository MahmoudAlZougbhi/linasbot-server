"""
Clinic slot rules (service + gender + branch + device) in bot local time.

Used to reject create_appointment / update_appointment_date before the CRM call
so the model can apologize and offer valid days/hours.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# --- IDs (aligned with OpenAI tool schema / booking flow) ---
BEIRUT_BRANCH_ID = 1
ANTELIAS_BRANCH_ID = 2

CO2_SERVICE_IDS = frozenset({2, 11})
WHITENING_SERVICE_IDS = frozenset({4, 5, 14})
TATTOO_SERVICE_ID = 13
HAIR_MEN = 1
HAIR_WOMEN = 12

# Candela device IDs from CRM — override with APPOINTMENT_CANDELA_MACHINE_IDS="15,22"
def _candela_machine_ids() -> frozenset:
    raw = (os.environ.get("APPOINTMENT_CANDELA_MACHINE_IDS") or "").strip()
    if raw:
        out: set = set()
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return frozenset(out) if out else frozenset({15})
    return frozenset({15})


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+", s)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return None
        return None


def _hm(h: int, m: int = 0) -> int:
    return h * 60 + m


def _time_mins(d: datetime.datetime) -> int:
    return d.hour * 60 + d.minute


def _weekday(d: datetime.datetime) -> int:
    return d.weekday()  # Monday=0 ... Sunday=6


def parse_normalized_api_datetime(date_str: str, tz: datetime.tzinfo) -> Optional[datetime.datetime]:
    """Parse create/update tool `date` after normalize_tool_date (`%Y-%m-%d %H:%M:%S` in tz)."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def find_appointment_row_in_check_next_payload(
    check_next_result: Optional[dict],
    appointment_id: Optional[int],
) -> Optional[dict]:
    """Match `appointment_id` against enriched check_next payload (customer_appointments + next row)."""
    if appointment_id is None or not isinstance(check_next_result, dict):
        return None

    def _rows_from_payload(payload: dict) -> List[dict]:
        ca = payload.get("customer_appointments")
        if isinstance(ca, list):
            return [x for x in ca if isinstance(x, dict)]
        data = payload.get("data")
        if isinstance(data, dict):
            ca2 = data.get("customer_appointments")
            if isinstance(ca2, list):
                return [x for x in ca2 if isinstance(x, dict)]
        return []

    for row in _rows_from_payload(check_next_result):
        rid = _safe_int(row.get("appointment_id") or row.get("id") or row.get("appointmentId"))
        if rid == appointment_id:
            return row

    data = check_next_result.get("data")
    if isinstance(data, dict):
        ap = data.get("appointment")
        if isinstance(ap, dict):
            rid = _safe_int(ap.get("appointment_id") or ap.get("id") or ap.get("appointmentId"))
            if rid == appointment_id:
                return ap
        if _safe_int(data.get("appointment_id") or data.get("id")) == appointment_id:
            return data
    return None


def extract_appointment_booking_fields(row: Optional[dict]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    if not row or not isinstance(row, dict):
        return None, None, None

    sid = _safe_int(row.get("service_id"))
    if sid is None:
        svc = row.get("service")
        if isinstance(svc, dict):
            sid = _safe_int(svc.get("id") or svc.get("service_id"))

    bid = _safe_int(row.get("branch_id"))
    if bid is None:
        br = row.get("branch")
        if isinstance(br, dict):
            bid = _safe_int(br.get("id") or br.get("branch_id"))
        elif isinstance(br, str):
            blower = br.strip().lower()
            if "beirut" in blower:
                bid = BEIRUT_BRANCH_ID
            elif "antelias" in blower or "antelia" in blower:
                bid = ANTELIAS_BRANCH_ID

    mid = _safe_int(row.get("machine_id"))
    if mid is None:
        m = row.get("machine")
        if isinstance(m, dict):
            mid = _safe_int(m.get("id") or m.get("machine_id"))

    return sid, bid, mid


def _fail(
    code: str,
    explanation_en: str,
    suggestions_en: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "slot_validation": {
            "code": code,
            "explanation_en": explanation_en,
            "suggestions_en": suggestions_en,
        },
    }


def _ok() -> Dict[str, Any]:
    return {"ok": True}


def _resolve_effective_gender(gender_raw: str, service_id: Optional[int]) -> Optional[str]:
    g = (gender_raw or "").strip().lower()
    if g in ("male", "m", "man"):
        return "male"
    if g in ("female", "f", "woman", "women"):
        return "female"
    if service_id == HAIR_MEN:
        return "male"
    if service_id == HAIR_WOMEN:
        return "female"
    return None


def _is_candela(machine_id: Optional[int]) -> bool:
    if machine_id is None:
        return False
    return machine_id in _candela_machine_ids()


def validate_booking_slot(
    *,
    dt_local: datetime.datetime,
    service_id: Optional[int],
    branch_id: Optional[int],
    machine_id: Optional[int],
    gender_raw: str,
) -> Dict[str, Any]:
    """
    Return {"ok": True} or {"ok": False, "slot_validation": {...}}.
    Unknown service_id → ok True (CRM may still reject).
    """
    if branch_id not in (BEIRUT_BRANCH_ID, ANTELIAS_BRANCH_ID):
        return _ok()

    wd = _weekday(dt_local)
    tm = _time_mins(dt_local)
    eff_g = _resolve_effective_gender(gender_raw, service_id)

    # --- Tattoo: Beirut, Thu/Sat, 13:00–16:00 ---
    if service_id == TATTOO_SERVICE_ID:
        if branch_id != BEIRUT_BRANCH_ID:
            return _fail(
                "tattoo_branch",
                "Laser tattoo removal is only available at the Beirut branch.",
                "Offer Beirut on Thursday or Saturday between 1:00 PM and 4:00 PM (clinic local time).",
            )
        if wd not in (3, 5):  # Thu, Sat
            return _fail(
                "tattoo_weekday",
                "Laser tattoo removal is only scheduled on Thursday and Saturday.",
                "Offer Thursday or Saturday between 1:00 PM and 4:00 PM at Beirut.",
            )
        if not (_hm(13, 0) <= tm <= _hm(16, 0)):
            return _fail(
                "tattoo_hours",
                "Laser tattoo removal hours are 1:00 PM to 4:00 PM.",
                "Offer the same day at a time between 1:00 PM and 4:00 PM, or another Thursday/Saturday in that window.",
            )
        return _ok()

    # --- CO2: Beirut only, Thursday & Saturday, 1:00 PM–4:00 PM ---
    if service_id in CO2_SERVICE_IDS:
        if branch_id != BEIRUT_BRANCH_ID:
            return _fail(
                "co2_branch",
                "CO2 laser is only available at the Beirut branch.",
                "Offer Beirut on Thursday or Saturday between 1:00 PM and 4:00 PM (clinic local time).",
            )
        if wd not in (3, 5):  # Thu, Sat
            return _fail(
                "co2_weekday",
                "CO2 laser at Beirut is only on Thursday and Saturday.",
                "Offer Thursday or Saturday between 1:00 PM and 4:00 PM at Beirut.",
            )
        if not (_hm(13, 0) <= tm <= _hm(16, 0)):
            return _fail(
                "co2_hours",
                "CO2 laser at Beirut is only between 1:00 PM and 4:00 PM.",
                "Offer Thursday or Saturday between 1:00 PM and 4:00 PM at Beirut.",
            )
        return _ok()

    # --- Whitening ---
    if service_id in WHITENING_SERVICE_IDS:
        if eff_g is None:
            return _ok()
        if eff_g == "female":
            if wd == 6:
                if branch_id == ANTELIAS_BRANCH_ID:
                    return _fail(
                        "whitening_female_sunday_antelias",
                        "Antelias is closed on Sunday for women's whitening.",
                        "Offer Beirut on Sunday between 2:00 PM and 7:00 PM, or Monday/Wednesday/Friday at either branch (9:00 AM–7:00 PM).",
                    )
                if not (_hm(14, 0) <= tm <= _hm(19, 0)):
                    return _fail(
                        "whitening_female_sunday_beirut",
                        "On Sunday at Beirut, women's whitening is between 2:00 PM and 7:00 PM.",
                        "Offer Sunday 2:00 PM–7:00 PM at Beirut, or Monday/Wednesday/Friday 9:00 AM–7:00 PM.",
                    )
                return _ok()
            if wd in (0, 2, 4):
                if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                    return _fail(
                        "whitening_female_hours",
                        "For women, whitening on Mon/Wed/Fri is between 9:00 AM and 7:00 PM.",
                        "Offer Monday, Wednesday, or Friday between 9:00 AM and 7:00 PM.",
                    )
                return _ok()
            return _fail(
                "whitening_female_weekday",
                "For women, whitening is on Monday, Wednesday, and Friday (9 AM–7 PM), plus Sunday afternoon at Beirut only.",
                "Offer Monday, Wednesday, or Friday 9:00 AM–7:00 PM, or Sunday 2:00 PM–7:00 PM at Beirut.",
            )
        # male
        if branch_id == BEIRUT_BRANCH_ID:
            if wd in (1, 3, 5):
                if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                    return _fail(
                        "whitening_male_beirut_hours",
                        "For men at Beirut, Tue/Thu/Sat whitening is between 9:00 AM and 7:00 PM.",
                        "Offer Tuesday, Thursday, or Saturday between 9:00 AM and 7:00 PM at Beirut.",
                    )
                return _ok()
            if wd == 6:
                if not (_hm(9, 0) <= tm <= _hm(14, 0)):
                    return _fail(
                        "whitening_male_beirut_sunday",
                        "For men at Beirut, Sunday whitening is between 9:00 AM and 2:00 PM.",
                        "Offer Sunday 9:00 AM–2:00 PM or Tue/Thu/Sat 9:00 AM–7:00 PM at Beirut.",
                    )
                return _ok()
            return _fail(
                "whitening_male_beirut_weekday",
                "For men at Beirut, whitening is Tue/Thu/Sat 9 AM–7 PM or Sun 9 AM–2 PM.",
                "Offer Tuesday, Thursday, Saturday (9:00 AM–7:00 PM) or Sunday (9:00 AM–2:00 PM) at Beirut.",
            )
        # Antelias male
        if wd in (1, 3):
            if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                return _fail(
                    "whitening_male_antelias_hours",
                    "For men at Antelias, Tue/Thu whitening is between 9:00 AM and 7:00 PM.",
                    "Offer Tuesday or Thursday between 9:00 AM and 7:00 PM at Antelias.",
                )
            return _ok()
        if wd == 5:  # Sat
            if not (_hm(8, 0) <= tm <= _hm(13, 0)):
                return _fail(
                    "whitening_male_antelias_sat",
                    "For men at Antelias, Saturday whitening ends at 1:00 PM (slots from 8:00 AM).",
                    "Offer Saturday between 8:00 AM and 1:00 PM at Antelias, or Tue/Thu 9:00 AM–7:00 PM.",
                )
            return _ok()
        return _fail(
            "whitening_male_antelias_weekday",
            "For men at Antelias, whitening is Tuesday/Thursday (9 AM–7 PM) or Saturday (8 AM–1 PM).",
            "Offer Tuesday or Thursday 9:00 AM–7:00 PM, or Saturday 8:00 AM–1:00 PM at Antelias.",
        )

    # --- Hair removal ---
    if service_id == HAIR_WOMEN:
        if _is_candela(machine_id) and branch_id != BEIRUT_BRANCH_ID:
            return _fail(
                "candela_female_branch",
                "Candela laser hair removal for women is only at the Beirut branch.",
                "Offer Beirut on Monday, Wednesday, or Friday (9:00 AM–7:00 PM), or Sunday 2:00 PM–7:00 PM.",
            )
        if wd == 6:
            if branch_id == ANTELIAS_BRANCH_ID:
                return _fail(
                    "hair_female_sunday_antelias",
                    "Antelias is closed on Sunday for women's laser hair removal.",
                    "Offer Beirut on Sunday between 2:00 PM and 7:00 PM, or Monday/Wednesday/Friday at either branch.",
                )
            if not (_hm(14, 0) <= tm <= _hm(19, 0)):
                return _fail(
                    "hair_female_sunday_beirut",
                    "On Sunday at Beirut, women's laser hair is between 2:00 PM and 7:00 PM.",
                    "Offer Sunday 2:00 PM–7:00 PM at Beirut, or Monday/Wednesday/Friday 9:00 AM–7:00 PM.",
                )
            return _ok()
        if wd in (0, 2, 4):
            if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                return _fail(
                    "hair_female_hours",
                    "Women's laser hair removal on Mon/Wed/Fri is between 9:00 AM and 7:00 PM.",
                    "Offer Monday, Wednesday, or Friday between 9:00 AM and 7:00 PM.",
                )
            return _ok()
        return _fail(
            "hair_female_weekday",
            "Women's laser hair removal is Monday, Wednesday, Friday (9 AM–7 PM), and Sunday afternoon at Beirut only.",
            "Offer Mon/Wed/Fri 9:00 AM–7:00 PM, or Sunday 2:00 PM–7:00 PM at Beirut.",
        )

    if service_id == HAIR_MEN:
        # Candela (men): same days and hours as men's laser at Beirut — not a separate Tue/Thu-only window.
        if _is_candela(machine_id) and branch_id != BEIRUT_BRANCH_ID:
            return _fail(
                "candela_male_branch",
                "Candela laser hair removal for men is only at the Beirut branch.",
                "Offer Beirut on men's laser days: Tuesday, Thursday, Saturday 9:00 AM–7:00 PM, or Sunday 9:00 AM–2:00 PM.",
            )
        if branch_id == BEIRUT_BRANCH_ID:
            if wd in (1, 3, 5):
                if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                    return _fail(
                        "hair_male_beirut_hours",
                        "For men at Beirut, Tue/Thu/Sat laser hair is between 9:00 AM and 7:00 PM.",
                        "Offer Tuesday, Thursday, or Saturday between 9:00 AM and 7:00 PM at Beirut.",
                    )
                return _ok()
            if wd == 6:
                if not (_hm(9, 0) <= tm <= _hm(14, 0)):
                    return _fail(
                        "hair_male_beirut_sunday",
                        "For men at Beirut, Sunday laser hair is between 9:00 AM and 2:00 PM.",
                        "Offer Sunday 9:00 AM–2:00 PM or Tue/Thu/Sat 9:00 AM–7:00 PM at Beirut.",
                    )
                return _ok()
            return _fail(
                "hair_male_beirut_weekday",
                "For men at Beirut, laser hair is Tue/Thu/Sat 9 AM–7 PM or Sun 9 AM–2 PM.",
                "Offer Tuesday, Thursday, Saturday (9:00 AM–7:00 PM) or Sunday (9:00 AM–2:00 PM) at Beirut.",
            )
        # Antelias male (non-Candela)
        if wd in (1, 3):
            if not (_hm(9, 0) <= tm <= _hm(19, 0)):
                return _fail(
                    "hair_male_antelias_hours",
                    "For men at Antelias, Tue/Thu laser hair is between 9:00 AM and 7:00 PM.",
                    "Offer Tuesday or Thursday between 9:00 AM and 7:00 PM at Antelias.",
                )
            return _ok()
        if wd == 5:
            if not (_hm(8, 0) <= tm <= _hm(13, 0)):
                return _fail(
                    "hair_male_antelias_sat",
                    "For men at Antelias, Saturday laser hair ends at 1:00 PM (from 8:00 AM).",
                    "Offer Saturday 8:00 AM–1:00 PM at Antelias, or Tue/Thu 9:00 AM–7:00 PM.",
                )
            return _ok()
        return _fail(
            "hair_male_antelias_weekday",
            "For men at Antelias, laser hair is Tuesday/Thursday (9 AM–7 PM) or Saturday (8 AM–1 PM).",
            "Offer Tuesday or Thursday 9:00 AM–7:00 PM, or Saturday 8:00 AM–1:00 PM at Antelias.",
        )

    return _ok()
