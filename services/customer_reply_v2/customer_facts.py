"""Persistent safe customer facts (name correction, explicit gender, language)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from storage.persistent_storage import get_data_root
from services.customer_reply_v2.models import CustomerFacts

# Explicit self-identification only — not third-party mentions.
_NAME_CORRECTION_PATTERNS = [
    re.compile(r"\bmy\s+(?:real\s+)?name\s+is\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40})", re.I),
    re.compile(r"\b(?:call|please\s+call)\s+me\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40})", re.I),
    re.compile(r"اسمي(?:\s+الحقيقي)?\s+([^\s،,.!?]+)", re.I),
    re.compile(r"ناديني\s+([^\s،,.!?]+)", re.I),
    re.compile(
        r"\b(?:not|not\s+anymore)\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40}).{0,40}?"
        r"\b(?:my\s+name\s+is|i(?:'m| am))\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40})",
        re.I,
    ),
]

_THIRD_PARTY_NAME_BLOCKERS = re.compile(
    r"\b(my\s+(sister|brother|friend|husband|wife|mom|dad|employee|colleague)|"
    r"send\s+this\s+to|the\s+employee(?:'s)?\s+name|"
    r"أختي|أخوي|صديقي|صديقتي|زوجي|زوجتي|موظف)\b",
    re.I,
)

_GENDER_EXPLICIT = [
    (re.compile(r"\b(?:i\s+am|i'm)\s+(a\s+)?(man|male|woman|female)\b", re.I), "group"),
    (re.compile(r"\b(?:for\s+)?(men|women)\s+(?:services?|please)\b", re.I), "audience"),
    (re.compile(r"أنا\s+(رجل|ذكر|امرأة|أنثى|بنت|ولد)", re.I), "ar"),
]

_AMBIGUOUS_LANG_TOKENS = frozenset(
    {"ok", "okay", "yes", "no", "yep", "nope", "👍", "🙏", "❤️", "🙂", "😂", "haha", "lol", "mm", "hmm"}
)


def _facts_path(tenant_id: str, channel: str, asset_id: str, provider_sender_id: str) -> Path:
    key = hashlib.sha256(f"{tenant_id}|{channel}|{asset_id}|{provider_sender_id}".encode()).hexdigest()[:32]
    root = Path(get_data_root()) / "tenants" / tenant_id / "customer_reply_v2" / "facts" / channel
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{key}.json"


def load_customer_facts(
    *,
    tenant_id: str,
    channel: str,
    asset_id: str,
    provider_sender_id: str,
    provider_display_name: str = "",
) -> CustomerFacts:
    path = _facts_path(tenant_id, channel, asset_id, provider_sender_id)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    confirmed = data.get("customer_confirmed_name")
    name_source = data.get("name_source") or "provider"
    # Provider refresh must not overwrite explicit correction.
    provider_name = str(data.get("provider_display_name") or provider_display_name or "")
    if provider_display_name and name_source != "explicit_self_report":
        provider_name = provider_display_name
    elif provider_display_name and not data.get("provider_display_name"):
        provider_name = provider_display_name
    # Always keep latest provider name as audit metadata when provided.
    if provider_display_name:
        provider_name_audit = provider_display_name
    else:
        provider_name_audit = provider_name

    facts = CustomerFacts(
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id,
        provider_sender_id=provider_sender_id,
        provider_display_name=provider_name_audit,
        customer_confirmed_name=str(confirmed) if confirmed else None,
        name_source="explicit_self_report" if confirmed and name_source == "explicit_self_report" else "provider",
        gender=str(data["gender"]) if data.get("gender") else None,
        preferred_language=str(data["preferred_language"]) if data.get("preferred_language") else None,
    )
    return facts


def save_customer_facts(facts: CustomerFacts) -> None:
    path = _facts_path(facts.tenant_id, facts.channel, facts.asset_id, facts.provider_sender_id)
    payload = {
        "provider_display_name": facts.provider_display_name,
        "customer_confirmed_name": facts.customer_confirmed_name,
        "name_source": facts.name_source,
        "gender": facts.gender,
        "preferred_language": facts.preferred_language,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_customer_facts(*, tenant_id: str, channel: str, asset_id: str, provider_sender_id: str) -> bool:
    path = _facts_path(tenant_id, channel, asset_id, provider_sender_id)
    if path.exists():
        path.unlink()
        return True
    return False


def extract_explicit_name_correction(message: str) -> str | None:
    text = (message or "").strip()
    if not text or _THIRD_PARTY_NAME_BLOCKERS.search(text):
        return None
    # Prefer "My name is X, not Y" style — capture the affirmed name.
    m = re.search(
        r"\bmy\s+name\s+is\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40})"
        r"(?:\s*,?\s*not\s+[A-Za-z\u0600-\u06FF][\w\u0600-\u06FF'\-]{1,40})?",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip()
    for pat in _NAME_CORRECTION_PATTERNS:
        hit = pat.search(text)
        if hit:
            # last group is usually the affirmed name for dual-group patterns
            return (hit.group(hit.lastindex or 1) or "").strip() or None
    return None


def extract_explicit_gender(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if re.search(r"\b(i\s+am|i'm)\s+(a\s+)?(man|male)\b", lowered):
        return "men"
    if re.search(r"\b(i\s+am|i'm)\s+(a\s+)?(woman|female)\b", lowered):
        return "women"
    if re.search(r"أنا\s+(رجل|ذكر|ولد)", text):
        return "men"
    if re.search(r"أنا\s+(امرأة|أنثى|بنت)", text):
        return "women"
    # Do not infer from names/photos — only clear self-report above.
    return None


def should_update_language(message: str, detected_language: str | None) -> bool:
    text = (message or "").strip()
    if not detected_language:
        return False
    if not text or text.lower() in _AMBIGUOUS_LANG_TOKENS:
        return False
    if len(text) <= 2 and not any("\u0600" <= ch <= "\u06FF" for ch in text):
        return False
    return True


def apply_message_fact_updates(facts: CustomerFacts, message: str, detected_language: str | None) -> CustomerFacts:
    """Return updated facts from explicit self-reports only. Persists when changed."""
    changed = False
    name = extract_explicit_name_correction(message)
    if name:
        facts.customer_confirmed_name = name
        facts.name_source = "explicit_self_report"
        changed = True
    gender = extract_explicit_gender(message)
    if gender and gender != facts.gender:
        facts.gender = gender
        changed = True
    if should_update_language(message, detected_language) and detected_language != facts.preferred_language:
        facts.preferred_language = detected_language
        changed = True
    if changed:
        save_customer_facts(facts)
    elif facts.provider_display_name:
        # Ensure first-contact provider name is stored without overwriting corrections.
        save_customer_facts(facts)
    return facts
