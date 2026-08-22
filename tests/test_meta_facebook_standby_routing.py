"""Facebook Page Inbox standby DMs must route to the Facebook binding."""

from __future__ import annotations

import logging

import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    META_COMMENT_SCOPES,
    get_meta_app_configs,
)
from services.meta_multi_app_router import resolve_registry_events
from services.meta_page_webhook_subscription import desired_binding_webhook_subscription
from tests.meta_app_registry_helpers import ALL_MESSAGING_SCOPES, _credential, _page_payload

pytest_plugins = ("tests.meta_app_registry_fixtures",)


def _standby_payload(*, page_id: str, message_id: str = "mid-standby") -> dict[str, object]:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "standby": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": page_id},
                        "message": {"mid": message_id, "text": "hello from inbox"},
                    }
                ],
            }
        ],
    }


def _activate_facebook(*, registry, instagram_account_id: str) -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=instagram_account_id,
        app_key=APP_A_KEY,
        credential=_credential(app_id, LINAS_PAGE_ID),
        actor_id="owner",
    )


@pytest.mark.asyncio
async def test_standby_page_inbox_dm_routes_to_facebook_binding(registry) -> None:
    _activate_facebook(registry=registry, instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID)
    routed = await resolve_registry_events(
        _standby_payload(page_id=LINAS_PAGE_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
    )
    assert len(routed) == 1
    assert routed[0].event["channel"] == "facebook"
    assert routed[0].event["text"] == "hello from inbox"


@pytest.mark.asyncio
async def test_facebook_page_id_is_not_used_as_instagram_account_id(registry) -> None:
    _activate_facebook(registry=registry, instagram_account_id="")
    routed = await resolve_registry_events(
        _page_payload(page_id=LINAS_PAGE_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
    )
    assert len(routed) == 1
    assert routed[0].event["channel"] == "facebook"


@pytest.mark.asyncio
async def test_empty_standby_resolve_logs_inbound_buckets(registry, caplog) -> None:
    caplog.set_level(logging.INFO, logger="services.meta_multi_app_router")
    routed = await resolve_registry_events(
        _standby_payload(page_id=LINAS_PAGE_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
    )
    assert routed == []
    assert any(
        "dm_resolve_empty" in record.getMessage() and "standby=1" in record.getMessage() for record in caplog.records
    )


def test_desired_facebook_page_subscription_includes_standby(registry) -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    scopes = tuple(ALL_MESSAGING_SCOPES) + tuple(META_COMMENT_SCOPES["facebook"])
    activated = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_id, LINAS_PAGE_ID, scopes=scopes),
        actor_id="owner",
    )
    assert desired_binding_webhook_subscription(activated, registry=registry) == (
        "feed",
        "messages",
        "messaging_postbacks",
        "standby",
    )
