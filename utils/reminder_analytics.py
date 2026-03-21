# -*- coding: utf-8 -*-
"""Classify user replies to 24h smart reminder (confirm / postpone / cancel / defer)."""

from __future__ import annotations

import re
from typing import Optional

from utils.datetime_utils import detect_reschedule_intent

_CANCEL_PATTERNS = [
    r"\bcancel(?:led|ing)?\b",
    r"\bannul(?:er|é|e)?\b",
    r"\bunsubscribe\b",
    r"(?:إلغاء|الغاء|الغي|الغِ|الغِي|ملغي|الغاء الموعد|الغي الموعد)",
    r"\b(?:ma\s+)?bad(?:i|y)\s+(?:el\s+)?maw3",
    r"\b(?:ma\s+)?b(?:a|e)dda\s+maw3",
]

_DEFER_PATTERNS = [
    r"\b(?:later|another\s*time|call\s*me\s*back|not\s*now)\b",
    r"\b(?:we('ll| will)\s*(?:talk|speak|get\s*back))\b",
    r"(?:منرجع|منرجعو|منرجعوا|منرجعين)\s*(?:منحكي|نحكي|نحكى)",
    r"(?:نرجع|نرجعو)\s*(?:منحكي|نحكي|لنحكي|نحكى)",
    r"(?:بعدين|بعدين|بعد\s*شوي|بعد\s*شوية|لاحقا|لاحقاً)",
    r"(?:خلينا|خلّينا)\s*(?:بعدين|بعدين|لاحقا)",
    r"\bb3den\b",
    r"\bba3den\b",
    r"(?:منشوف|نشوف)\s*(?:بعدين|بعدين)",
]

_CONFIRM_PATTERNS = [
    r"^(?:yes|y|ok|okay|sure|yep|yeah|confirm|confirmed|alright|fine)\b",
    r"^(?:oui|d'accord)\b",
    r"^(?:نعم|نعم\s*تأكيد|تمام|اوكي|أوكي|اوك|أوك|ماشي|تم|صح|اي|ايه|أيه|اي\s*تمام|👍|✅)\s*$",
    r"^(?:yes|ok|تمام)\s*[!.؟]?$",
    r"^\s*(?:👍|✅)\s*$",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def classify_reminder_reply_intent(text: str) -> Optional[str]:
    """
    Map a user message to a reminder CTA bucket, or None if not a clear reply.

    Returns one of: confirm, postpone, cancel, defer
    """
    raw = (text or "").strip()
    if not raw or len(raw) > 800:
        return None

    n = _norm(raw)
    if not n:
        return None

    for p in _CANCEL_PATTERNS:
        if re.search(p, raw, re.IGNORECASE) or re.search(p, n, re.IGNORECASE):
            return "cancel"

    if detect_reschedule_intent(raw):
        return "postpone"

    for p in _DEFER_PATTERNS:
        if re.search(p, raw, re.IGNORECASE) or re.search(p, n, re.IGNORECASE):
            return "defer"

    for p in _CONFIRM_PATTERNS:
        if re.match(p, n, re.IGNORECASE) or re.match(p, raw.strip(), re.IGNORECASE):
            return "confirm"

    # Short Arabic/Franco yes without strict line anchors
    if len(raw) <= 32:
        if re.fullmatch(r"(نعم|تمام|اوكي|أوكي|ماشي|اي|ايه|أيه|تم|صح|ok|yes)", n, re.IGNORECASE):
            return "confirm"

    return None
