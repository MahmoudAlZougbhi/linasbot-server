"""Builders for two-app Meta registry tests."""

from __future__ import annotations

import time

from services.meta_app_registry import MetaBindingCredential

ALL_MESSAGING_SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


def _credential(app_id: str, page_id: str, *, scopes: tuple[str, ...] = ALL_MESSAGING_SCOPES) -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token=f"sensitive-token-{app_id}-{page_id}",
        token_app_id=app_id,
        token_profile_id=page_id,
        scopes=scopes,
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id="112233445566",
    )


def _page_payload(*, page_id: str, message_id: str = "mid-1") -> dict[str, object]:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": page_id},
                        "message": {"mid": message_id, "text": "hello"},
                    }
                ],
            }
        ],
    }
