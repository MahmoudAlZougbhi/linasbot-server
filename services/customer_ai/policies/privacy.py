"""Public comments must not leak private facts or claim a DM without a receipt."""

from __future__ import annotations

import re

_DM_CLAIM = re.compile(
    r"(sent you a dm|i (just )?sent (you )?(a )?dm|check (your )?dms?|"
    r"sent a private message|أرسلتلك|ارسلتك|شوف الخاص|شوف الdm|دirect message)",
    re.I,
)
_CONTACT = re.compile(
    r"(\+?\d[\d\s\-()]{7,}\d|\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b)",
    re.I,
)
_SAFE_NO_CLAIM = "We'll continue privately if needed."


def claims_private_send(text: str) -> bool:
    return bool(_DM_CLAIM.search(text or ""))


def public_comment_safe(text: str, *, dm_receipt_ok: bool = False) -> str:
    cleaned = _CONTACT.sub("", text or "")
    if claims_private_send(cleaned) and not dm_receipt_ok:
        cleaned = _DM_CLAIM.sub("", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" -–—,.")
        if not cleaned:
            return _SAFE_NO_CLAIM
        if not cleaned.endswith((".", "!", "?")):
            cleaned = f"{cleaned}."
        return f"{cleaned} {_SAFE_NO_CLAIM}"
    return " ".join(cleaned.split()).strip()
