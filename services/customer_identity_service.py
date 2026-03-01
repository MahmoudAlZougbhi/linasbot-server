# services/customer_identity_service.py
"""
Resolve customer from external CRM/main system before naming or creating users.
Cache by normalized_phone with TTL. On API failure: do NOT set a name (fallback unknown/phone only).
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional

from utils.phone_utils import normalize_phone

logger = logging.getLogger(__name__)

# TTL in seconds for external lookup cache (reduce API load)
EXTERNAL_RESOLVE_CACHE_TTL = 600  # 10 minutes

_external_resolve_cache: Dict[str, Dict[str, Any]] = {}
_cache_entries_ttl: Dict[str, float] = {}


def _phone_to_api_format(normalized_phone: str) -> str:
    """External API expects local digits (no +, no 961 for Lebanon)."""
    if not normalized_phone or not normalized_phone.startswith("+"):
        return normalized_phone or ""
    digits = normalized_phone[1:]
    if digits.startswith("961") and len(digits) > 3:
        return digits[3:]
    return digits


async def resolve_customer_from_external(normalized_phone: str) -> Dict[str, Any]:
    """
    Resolve customer from external system by normalized E.164 phone.
    Returns: { "exists": bool, "name": str|None, "external_id": str|None, "gender": str|None }
    On timeout/failure: exists=False, name=None (do not create named user; use unknown/phone only).
    Cache key: normalized_phone only. TTL applied.
    """
    if not normalized_phone or not normalized_phone.startswith("+"):
        return {"exists": False, "name": None, "external_id": None, "gender": None}

    now = time.monotonic()
    # Evict expired
    for key in list(_cache_entries_ttl.keys()):
        if now - _cache_entries_ttl.get(key, 0) > EXTERNAL_RESOLVE_CACHE_TTL:
            _external_resolve_cache.pop(key, None)
            _cache_entries_ttl.pop(key, None)

    cached = _external_resolve_cache.get(normalized_phone)
    if cached is not None:
        logger.debug("External resolve cache hit for %s", normalized_phone)
        return cached

    api_phone = _phone_to_api_format(normalized_phone)
    result = {"exists": False, "name": None, "external_id": None, "gender": None}

    try:
        from services.api_integrations import get_customer_by_phone
        response = await get_customer_by_phone(phone=api_phone)
        if response and response.get("success") and response.get("data"):
            data = response["data"]
            result["exists"] = True
            result["name"] = (data.get("name") or "").strip() or None
            ext_id = data.get("id")
            result["external_id"] = str(ext_id) if ext_id is not None else None
            g = (data.get("gender") or "").strip().lower()
            result["gender"] = g if g in ("male", "female") else None
            logger.info(
                "External resolve: phone=%s exists=True name=%s external_id=%s",
                normalized_phone, result["name"], result["external_id"]
            )
        else:
            logger.info(
                "External resolve: phone=%s exists=False (not in CRM)",
                normalized_phone
            )
    except asyncio.TimeoutError:
        logger.warning("External resolve timeout for %s; fallback unknown", normalized_phone)
    except Exception as e:
        logger.warning("External resolve failed for %s: %s; fallback unknown", normalized_phone, e)

    _external_resolve_cache[normalized_phone] = result
    _cache_entries_ttl[normalized_phone] = now
    return result


def invalidate_external_resolve_cache(normalized_phone: Optional[str] = None):
    """Clear cache for one number or entire cache (e.g. after customer update)."""
    if normalized_phone:
        _external_resolve_cache.pop(normalized_phone, None)
        _cache_entries_ttl.pop(normalized_phone, None)
    else:
        _external_resolve_cache.clear()
        _cache_entries_ttl.clear()
