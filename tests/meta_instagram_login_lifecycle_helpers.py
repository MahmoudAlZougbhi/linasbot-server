"""Fixtures and payload builders for Instagram Login lifecycle tests."""

from __future__ import annotations

import time

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential

INSTAGRAM_ID = "17840000999900021"
DM_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
)
FULL_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
    "instagram_business_content_publish",
)
PAGE_SCOPES = ("instagram_basic", "instagram_manage_messages", "instagram_manage_comments", "instagram_content_publish")


def _binding(
    registry: MetaAppRegistry,
    *,
    auth_flow: str,
    scopes: tuple[str, ...] = FULL_SCOPES,
    webhook_status: str = "ready",
    webhook_fields: tuple[str, ...] = ("messages", "messaging_postbacks"),
) -> object:
    return registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="112233" if auth_flow == "facebook_login" else "",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=f"token-{auth_flow}",
            token_app_id="2963733803971681" if auth_flow == "facebook_login" else "1035856539045307",
            token_profile_id="112233" if auth_flow == "facebook_login" else INSTAGRAM_ID,
            scopes=scopes,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="998877",
            auth_flow=auth_flow,
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow=auth_flow,
        webhook_subscription_status=webhook_status,
        webhook_subscribed_fields=webhook_fields,
    )


def _dm_payload() -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": INSTAGRAM_ID,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": INSTAGRAM_ID},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-dup", "text": "hello"},
                    }
                ],
            }
        ],
    }


def _comment_payload() -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": INSTAGRAM_ID,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-1",
                            "text": "nice",
                            "from": {"id": "author-1", "username": "fan"},
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }
