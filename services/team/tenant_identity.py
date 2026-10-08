"""Signup checks for tenant ids and business names. Existing rows stay readable."""

from __future__ import annotations

import re
from typing import Any

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_BAD_TENANT = re.compile(
    r"(or-1-1|169-254-169-254|meta-data|metadata|(^|-)script(-|$))",
    re.IGNORECASE,
)
_BAD_TEXT = re.compile(
    r"(<|>|</|onerror\s*=|javascript:|--|/\*|\bor\s+1\s*=\s*1\b|169\.254\.169\.254|169-254-169-254)",
    re.IGNORECASE,
)
PROTECTED_TENANTS = frozenset({"linas", "platform", "testuser"})
REVIEW_TENANTS = frozenset({"apple-account", "chance-app", "linsss"})
_PROBE_ID = re.compile(
    r"(probe|proof|recon|ssrf|sqli|xss|(^|-)script(-|$)|top10|^t10x?$|xfg|or-1-1|169-254|^other$|^ok-clinic|^privateum$)",
    re.IGNORECASE,
)
_TEST_EMAIL = re.compile(
    r"@(?:.+\.tld|p\.tld|tld2\.tld|privtest\.tld|linas\.ai\.test|example\.[a-z0-9.]+)$",
    re.IGNORECASE,
)
_INJECT = re.compile(r"[<>'\"]|--|\.\./|\r|\n")


def validate_tenant_identity(*, tenant_id: str, business_name: str = "", email: str = "") -> str:
    tid = (tenant_id or "").strip().lower()
    if not _SLUG.fullmatch(tid) or _BAD_TENANT.search(tid):
        raise ValueError("Invalid tenant identifier")
    if business_name and _BAD_TEXT.search(business_name):
        raise ValueError("Invalid business name")
    if email and _BAD_TEXT.search(email):
        raise ValueError("Invalid email")
    return tid


def matched_junk_rule(*, tenant_id: str, business_name: str = "", email: str = "") -> str:
    tid = (tenant_id or "").strip().lower()
    if tid in PROTECTED_TENANTS:
        return ""
    if any(_INJECT.search(value or "") for value in (tid, business_name, email)):
        return "injection"
    if _PROBE_ID.search(tid) or _PROBE_ID.search(business_name or ""):
        return "probe"
    if _TEST_EMAIL.search(email or ""):
        return "test_email"
    try:
        validate_tenant_identity(tenant_id=tid or "x", business_name=business_name, email=email)
    except ValueError:
        return "invalid"
    return ""


def is_junk_identity(*, tenant_id: str, business_name: str = "", email: str = "") -> bool:
    return bool(matched_junk_rule(tenant_id=tenant_id, business_name=business_name, email=email))


def classify_tenant(row: dict[str, Any]) -> str:
    tid = str(row.get("tenant_id") or "").strip().lower()
    if tid in PROTECTED_TENANTS:
        return "protected"
    used = int(row.get("messages_used") or 0) or int(row.get("credits_used") or 0)
    used = used or int(row.get("historical_credit_remaining") or 0) or int(row.get("payments") or 0)
    if row.get("published_brain") or used:
        return "protected"
    if tid in REVIEW_TENANTS:
        return "needs_owner_review"
    if matched_junk_rule(
        tenant_id=tid,
        business_name=str(row.get("business_name") or ""),
        email=str(row.get("email") or ""),
    ):
        return "candidate"
    return "normal"
