"""Instagram API with Instagram Login OAuth for Meta App A."""

from __future__ import annotations

from services.meta_instagram_login_oauth_complete import complete_instagram_login
from services.meta_instagram_login_oauth_staging import (  # noqa: F401 — preserve historical imports
    _authorize_staged_instagram_binding_reconciled,
    _compensate_failed_instagram_activation,
    _discard_staged_instagram_binding_reconciled,
    _instagram_activation_commit_matches,
    _InstagramProviderVerificationDeferred,
    _mark_instagram_cleanup_pending,
)
from services.meta_instagram_login_oauth_tokens import (  # noqa: F401 — preserve historical imports
    INSTAGRAM_LOGIN_OAUTH_FLOW,
    InstagramLoginOAuthResult,
    _graph_instagram_get,
    _scopes_from_payload,
    _tenant_has_recent_instagram_cleanup,
    begin_instagram_login,
    credential_needs_refresh,
    exchange_instagram_long_lived_token,
    exchange_instagram_short_lived_token,
    fetch_instagram_login_profile,
    refresh_instagram_long_lived_token,
    resolve_instagram_login_scopes,
)

__all__ = (
    "INSTAGRAM_LOGIN_OAUTH_FLOW",
    "InstagramLoginOAuthResult",
    "begin_instagram_login",
    "complete_instagram_login",
    "credential_needs_refresh",
    "exchange_instagram_long_lived_token",
    "exchange_instagram_short_lived_token",
    "fetch_instagram_login_profile",
    "refresh_instagram_long_lived_token",
    "resolve_instagram_login_scopes",
)
