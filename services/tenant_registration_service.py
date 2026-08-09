"""
Public SaaS company registration.

Creates an isolated tenant admin account. Never assigns the reserved ``linas`` tenant.
Passwords reuse the same strength rules as offline admin provisioning.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from typing import Any

from services.admin_provisioning_service import validate_provision_password
from services.user_service import user_service

_RESERVED_TENANTS = frozenset(
    {
        "linas",
        "admin",
        "administrator",
        "api",
        "www",
        "root",
        "system",
        "meta",
        "oauth",
        "webhook",
        "static",
        "downloads",
        "null",
        "undefined",
        "test",
        "demo",
        "default",
    }
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class RegistrationResult:
    user: dict[str, Any]
    tenant_id: str
    business_name: str


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _slugify_business_name(business_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", business_name or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "biz"
    if slug[0].isdigit():
        slug = f"b-{slug}"
    return slug[:48].rstrip("-") or "biz"


def allocate_tenant_id(business_name: str) -> str:
    """
    Allocate a unique tenant id derived from the business name.
    Collision handling appends a short random suffix. Reserved ids are never returned.
    """
    base = _slugify_business_name(business_name)
    if base in _RESERVED_TENANTS:
        base = f"biz-{base}"[:48].rstrip("-")

    candidates = [base]
    for _ in range(8):
        candidates.append(f"{base}-{secrets.token_hex(2)}")

    for candidate in candidates:
        try:
            tenant_id = user_service._normalize_tenant_id(candidate)
        except ValueError:
            continue
        if tenant_id in _RESERVED_TENANTS:
            continue
        if user_service.tenant_id_exists(tenant_id):
            continue
        return tenant_id

    raise ValueError("Could not allocate a unique company workspace id")


def register_company_account(
    *,
    business_name: str,
    email: str,
    password: str,
    name: str | None = None,
    display_name: str | None = None,
    gender: str | None = None,
    preferred_language: str | None = None,
    form_of_address: str | None = None,
) -> RegistrationResult:
    business = (business_name or "").strip()
    if len(business) < 2 or len(business) > 120:
        raise ValueError("Business name must be between 2 and 120 characters")

    email_n = _normalize_email(email)
    if not email_n or "@" not in email_n or "." not in email_n.split("@")[-1]:
        raise ValueError("A valid email is required")

    validate_provision_password(password)

    if user_service.get_user_by_email(email_n):
        raise ValueError("Email already exists")

    tenant_id = allocate_tenant_id(business)
    shown_name = (display_name or name or "").strip() or business
    gender_norm = str(gender or "unset").strip().lower()
    if gender_norm not in {"male", "female", "unset"}:
        gender_norm = "unset"
    lang = str(preferred_language or "en").strip().lower()
    if lang.startswith("ar"):
        lang = "ar"
    elif lang.startswith("fr"):
        lang = "fr"
    else:
        lang = "en"

    user = user_service.create_user(
        {
            "email": email_n,
            "password": password,
            "name": shown_name,
            "displayName": shown_name,
            "gender": gender_norm,
            "preferredLanguage": lang,
            "formOfAddress": (form_of_address or "").strip()[:80],
            "role": "admin",
            "permissions": None,
            "status": "active",
            "tenantId": tenant_id,
            "businessName": business,
        },
        created_by="public-register",
    )
    return RegistrationResult(user=user, tenant_id=tenant_id, business_name=business)
