"""Human-request detect for Live Chat handoff. No customer-facing copy."""

from __future__ import annotations

import re

# --- Human handover intent (meaning-based; common phrases) ---
HUMAN_REQUEST_PATTERNS = [
    # Arabic
    r"بدي\s*(?:أحكي|أتكلم|أتكلم)\s*(?:مع|ل)",
    r"بدي\s*(?:موظف|موظفة|حدا|حد)\s*(?:يحكي|يتواصل|يرد)\s*معي",
    r"خليني\s*(?:احكي|اتواصل)\s*مع\s*(?:حد|موظف|موظفة)",
    r"بدي\s*الدعم\s*البشري",
    r"حوّلني\s*(?:لموظف|للموظف|لبشر|لإنسان)",
    r"حد\s*(?:يحكي|يتكلم)\s*معي",
    r"موظف",
    r"موظفة",
    r"إنسان",
    r"شخص\s*حقيقي",
    r"واحد\s*(?:منكم|منكن)",
    r"بدي\s*حد",
    r"حابب\s*أحكي\s*مع",
    r"بدي\s*احكي\s*مع",
    r"بدّي\s*احكي\s*مع",
    r"بدي\s*أحكي\s*مع",
    r"احكي\s*مع\s*حدا",
    r"بدي\s*خدمة\s*العملاء",
    r"ما\s*بدي\s*بوت",
    r"ممكن\s*(?:حد|واحد)\s*(?:يحكي|يتكلم)",
    r"أريد\s*التحدث\s*مع",
    r"أريد\s*موظف",
    r"أريد\s*(?:إنسان|موظفة)",
    # Franco / Arabizi
    r"bade\s*(?:ehke|a7ke)\s*ma[3a]?\s*(?:hada|7ada|human|agent)",
    r"baddi\s*(?:hada|7ada)\s*(?:y7ke|ye7ke)\s*ma3e",
    r"(?:7awelni|hawelni)\s*(?:la|lal)\s*(?:hada|7ada|human|agent|mowazaf)",
    r"bade\s*(?:mowazaf|mwazzaf|employee|agent)",
    r"ma\s*bade\s*bot",
    r"bade\s*customer\s*service",
    r"khallini\s*ehke\s*ma3\s*(?:hada|agent|employee)",
    # English
    r"speak\s*(?:to|with)\s*(?:a\s*)?(?:human|person|agent|representative|employee)",
    r"i\s*want\s*to\s*speak\s*(?:to|with)\s*(?:someone|a\s*human|an?\s*agent)",
    r"can\s*i\s*speak\s*(?:to|with)\s*(?:someone|an?\s*agent|a\s*human)",
    r"i\s*need\s*(?:help\s*from\s*)?(?:a\s*)?(?:human|agent|representative|person)",
    r"no\s*bot",
    r"not\s*(?:a\s*)?bot",
    r"live\s*agent",
    r"talk\s*(?:to|with)\s*(?:a\s*)?(?:human|person|agent|representative)",
    r"customer\s*service",
    r"connect\s*me\s*(?:to|with)",
    r"transfer\s*me\s*(?:to|with)",
    r"real\s*person",
    r"human\s*agent",
    # French
    r"parler\s*(?:à|avec)\s*(?:un\s*)?(?:humain|employé|agent|personne)",
    r"je\s*veux\s*parler\s*(?:à|avec)\s*(?:un\s*)?(?:humain|agent|employé)",
    r"pouvez[-\s]*vous\s*me\s*passer\s*(?:un\s*)?(?:agent|humain|employé)",
    r"pas\s*de\s*bot",
    r"service\s*client",
    r"vraie\s*personne",
    r"agent\s*humain",
]
HUMAN_REQUEST_RE = re.compile("|".join(f"({p})" for p in HUMAN_REQUEST_PATTERNS), re.IGNORECASE | re.UNICODE)

# Simple keywords (fallback when regex misses)
HUMAN_REQUEST_KEYWORDS = [
    "human",
    "موظف",
    "موظفة",
    "حد يحكي",
    "بدي حد",
    "واحد منكم",
    "شخص حقيقي",
    # Do not use bare English "person" — matches "personal care tips" falsely.
    "representative",
    "employee",
    "customer service",
    "service client",
    "بدي حدا",
    "بدي انسان",
    "حوّلني",
    "حولني",
    "تحويل لموظف",
    "بدي احكي مع حدا",
    "بدّي احكي مع حدا",
    "احكي مع حدا",
    "مع حدا",
    "بدي احكي مع شخص",
    "احكي مع شخص",
    "bade hada",
    "baddi hada",
    "bade a7ke",
    "ehke ma3",
    "hawelni",
    "7awelni",
    "ما بدي بوت",
    "live agent",
    "no bot",
    "not a bot",
    "pas de bot",
    "human agent",
    "real person",
]


def _normalize(text: str) -> str:
    return (text or "").strip()


def is_human_request(message: str) -> bool:
    """Detect if the customer wants a human teammate (Live Chat), not a Requests card."""
    t = _normalize(message)
    if len(t) < 3:
        return False
    t_lower = t.lower()
    if re.search(r"\bpersonal\b", t_lower) and not re.search(
        r"\b(?:real\s+person|speak|talk|human\s+agent)\b", t_lower
    ):
        return False
    if HUMAN_REQUEST_RE.search(t):
        return True
    return any(kw in t_lower for kw in HUMAN_REQUEST_KEYWORDS)
