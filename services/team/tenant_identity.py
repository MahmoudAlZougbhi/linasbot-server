"""Signup checks for tenant ids and business names. Existing rows stay readable."""

from __future__ import annotations

import re

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


def validate_tenant_identity(*, tenant_id: str, business_name: str = "", email: str = "") -> str:
    tid = (tenant_id or "").strip().lower()
    if not _SLUG.fullmatch(tid) or _BAD_TENANT.search(tid):
        raise ValueError("Invalid tenant identifier")
    if business_name and _BAD_TEXT.search(business_name):
        raise ValueError("Invalid business name")
    if email and _BAD_TEXT.search(email):
        raise ValueError("Invalid email")
    return tid


def is_junk_identity(*, tenant_id: str, business_name: str = "", email: str = "") -> bool:
    if (tenant_id or "").strip().lower() in PROTECTED_TENANTS:
        return False
    try:
        validate_tenant_identity(tenant_id=tenant_id, business_name=business_name, email=email)
    except ValueError:
        return True
    return False
