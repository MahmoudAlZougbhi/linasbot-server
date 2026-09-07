"""Read-only Enhanced Video Context probe. Never sends the account token to Marketing APIs."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.tiktok_business.capabilities import TOKEN_KIND_ACCOUNT
from services.tiktok_business.errors import TikTokBusinessError
from services.tiktok_business.identity_api import identity_get
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.status import tiktok_integration_row


async def probe_linas_enhanced_readonly(*, tenant_id: str = "linas") -> dict[str, Any]:
    row = tiktok_integration_row(tenant_id)
    enhanced = dict(row.get("enhanced_video_context") or {})
    connection = None
    opened_ads = None
    guard = "no_connection"
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_active_for_tenant(tenant_id)
        if connection is not None:
            opened_ads = TikTokEnhancedRepository(session).open_advertiser_tokens(
                tenant_id=tenant_id, connection_id=connection.id
            )
            account = repo.open_tokens(connection)
            try:
                await identity_get(
                    access_token=str(account.get("access_token") or ""),
                    token_kind=TOKEN_KIND_ACCOUNT,
                    advertiser_id="must-not-send",
                )
                guard = "failed_open"
            except TikTokBusinessError as exc:
                guard = exc.code
    return {
        "tenant_id": tenant_id,
        "connected": bool(row.get("connected")),
        "post_context": row.get("post_context"),
        "enhanced_video_context": {
            "status": enhanced.get("status"),
            "reason_code": enhanced.get("reason_code"),
            "user_message": enhanced.get("user_message"),
        },
        "advertiser_token_present": bool(opened_ads),
        "account_token_identity_guard": guard,
        "acceptable": guard == "token_type_mismatch"
        or (connection is None and guard == "no_connection")
        or enhanced.get("status")
        in {"waiting_for_permission", "authorization_required", "identity_authorization_required"},
    }
