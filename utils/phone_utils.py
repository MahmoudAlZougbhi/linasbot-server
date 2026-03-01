# utils/phone_utils.py
"""
Single source of truth for phone normalization (E.164) used everywhere:
lookups, cache keys, DB, conversation identity. Lebanon (+961) supported.
"""
import re
from typing import Optional

# Default country code when local number has no country code (Lebanon)
DEFAULT_COUNTRY_CODE_LEBANON = "961"


def normalize_phone(raw_phone: Optional[str]) -> str:
    """
    Normalize to E.164 for Lebanon. Used for ALL lookups, cache keys, DB, identity.
    - Remove spaces/dashes
    - If starts with "0" -> treat as local: "+961" + rest (without leading 0)
    - If starts with "961" (no +) -> add "+"
    - Result always "+<countrycode><number>" (e.g. +9613956607)
    Returns empty string for invalid/placeholder/empty input.
    """
    if raw_phone is None:
        return ""
    value = str(raw_phone).strip()
    if not value or value.lower() in ("unknown", "none", "null") or value.startswith("room:"):
        return ""
    # Digits only for logic (keep + for prefix check)
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    # Strip leading 00 (international dialing)
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return ""
    # Lebanon: local numbers often 7 or 8 digits, optionally with leading 0
    if digits.startswith("0") and len(digits) > 1:
        digits = digits[1:]
    if digits.startswith("961") and len(digits) > 3:
        # Already has country code
        national = digits[3:].lstrip("0") or "0"
        digits = "961" + national
    elif len(digits) <= 8 and not digits.startswith("961"):
        # Local number (e.g. 3956607 or 03956607 already stripped to 3956607)
        digits = DEFAULT_COUNTRY_CODE_LEBANON + digits
    # Ensure we have 961 and reasonable length (e.g. 961 + 7 or 8 digits)
    if not digits.startswith("961"):
        return ""
    if len(digits) < 10:  # 961 + at least 7 digits
        return ""
    return "+" + digits


def is_phone_like_user_id(user_id: Optional[str]) -> bool:
    """True if user_id looks like a phone (Meta/360 wa_id) rather than a room_id."""
    if not user_id:
        return False
    uid = str(user_id).strip()
    if uid.startswith("+961") or uid.startswith("961"):
        return True
    digits = re.sub(r"\D", "", uid)
    if digits.startswith("0") and len(digits) == 8:
        # Lebanon local with leading 0 (e.g. 03956607)
        if digits[1] in "37":
            return True
        return False
    if len(digits) <= 8 and digits.startswith("7"):
        return True
    if len(digits) == 7 and digits[0] in "37":
        return True
    # 8 digits not starting with 7 or 0 are likely room_id (Qiscus)
    if len(digits) == 8:
        return False
    return False
