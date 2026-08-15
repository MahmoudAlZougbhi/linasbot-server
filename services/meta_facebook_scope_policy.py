"""Single trust-domain policy for Facebook Page access-token grants."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from services.meta_app_registry_common import (
    META_CHANNEL_SCOPES,
    META_COMMENT_SCOPES,
    META_FACEBOOK_LOGIN_EXTRA_SCOPES,
    META_FORBIDDEN_SCOPES,
)

FACEBOOK_PAGE_BINDING_SCOPES = META_CHANNEL_SCOPES["facebook"] | META_COMMENT_SCOPES["facebook"]

# App A can also own a WhatsApp product. Meta may therefore report these grants
# on the same inspected token. They are valid coexistence authority, but they do
# not belong in a Facebook Page binding and must be stripped before persistence.
FACEBOOK_PAGE_TOKEN_COEXISTENCE_SCOPES = (
    frozenset(
        {
            # Facebook Login grants public_profile by default. It is not Page
            # authority and is never persisted on the Page binding, but its
            # presence must not make every legitimate Page token unusable.
            "public_profile",
            "whatsapp_business_management",
            "whatsapp_business_messaging",
        }
    )
    | META_FACEBOOK_LOGIN_EXTRA_SCOPES
)


def normalize_facebook_page_token_scopes(
    scopes: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (persisted Page scopes, prohibited scopes) for an App-A Page token.

    Instagram Login has a separate app id, token and callback trust domain. Any
    legacy ``instagram_*`` grant on this Facebook Page token is consequently a
    configuration error, while the allowlisted WhatsApp grants may coexist and
    are removed rather than rejected.
    """

    raw = {str(scope).strip() for scope in scopes if str(scope).strip()}
    inspected = raw - FACEBOOK_PAGE_TOKEN_COEXISTENCE_SCOPES
    # This OAuth flow is intentionally limited to the six Page DM/comment
    # permissions. The bearer itself retains every grant even when registry
    # metadata drops it, so silently ignoring an unknown extra would store
    # authority that the App Review packet never requested or disclosed.
    prohibited = inspected - FACEBOOK_PAGE_BINDING_SCOPES
    prohibited |= inspected & META_FORBIDDEN_SCOPES
    persisted = tuple(sorted(raw & FACEBOOK_PAGE_BINDING_SCOPES))
    return persisted, tuple(sorted(prohibited))


def facebook_page_granular_targets_are_allowlisted(
    debug_data: dict[str, Any],
    *,
    page_id: str,
) -> bool:
    """Reject every explicit foreign target on a Page-relevant permission.

    Meta can omit ``granular_scopes`` or omit ``target_ids`` on otherwise-valid
    Page tokens, so absence is not treated as a foreign grant. When target IDs
    are present, however, every one must be the selected Facebook Page; a linked
    Instagram account belongs to the separate Instagram Login trust domain.
    """

    expected_page = str(page_id or "").strip()
    if not expected_page:
        return False
    granular = debug_data.get("granular_scopes")
    if not isinstance(granular, list):
        return True
    for raw_item in granular:
        if not isinstance(raw_item, dict):
            continue
        if str(raw_item.get("scope") or "").strip() not in FACEBOOK_PAGE_BINDING_SCOPES:
            continue
        targets = raw_item.get("target_ids")
        if targets is None:
            continue
        if not isinstance(targets, list):
            return False
        normalized = {str(target).strip() for target in targets if str(target).strip()}
        if normalized and normalized != {expected_page}:
            return False
    return True
