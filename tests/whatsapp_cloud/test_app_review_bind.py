"""Temporary Meta App Review WhatsApp bind — bind/status/unbind isolation tests."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32
os.environ["META_APP_A_ID"] = "2963733803971681"
os.environ["META_APP_A_SECRET"] = "test-app-a-secret"
os.environ["META_APP_A_WEBHOOK_VERIFY_TOKEN"] = "test-verify-token"
os.environ["META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID"] = "es-config-test"
os.environ["WHATSAPP_CLOUD_CONNECTION_UI_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_AI_REPLIES_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] = "false"
os.environ["PUBLIC_URL"] = "https://example.test"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.app_review_bind import (  # noqa: E402
    APP_REVIEW_SOURCE,
    AppReviewBindError,
    bind_app_review_test_number,
    status_app_review_bind,
    unbind_app_review_test_number,
)
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402

TEST_WABA = "900100200300"
TEST_PHONE = "900100200301"
TEST_TOKEN = "EAAG-test-token-never-log-" + ("y" * 40)


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_app_review.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", TEST_TOKEN)
    monkeypatch.delenv("META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS", raising=False)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()

    @contextmanager
    def _sess(*, require: bool = True):
        yield session
        session.commit()

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind.whatsapp_session", _sess)
    yield session
    session.close()
    reset_engine_for_tests()


def _mock_meta_ok(monkeypatch, *, phone_id: str = TEST_PHONE, waba_id: str = TEST_WABA) -> None:
    async def _debug(**kwargs: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "app_id": "2963733803971681",
            "scopes": [
                "whatsapp_business_management",
                "whatsapp_business_messaging",
            ],
        }

    async def _phones(**kwargs: Any) -> list[dict[str, Any]]:
        assert kwargs["waba_id"] == waba_id
        return [
            {
                "id": phone_id,
                "display_phone_number": "+1 555 010 1234",
                "verified_name": "Linas Test",
            }
        ]

    async def _sub(**kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _debug)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.fetch_waba_phone_numbers", _phones)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind.subscribe_waba_webhooks", _sub)


@pytest.mark.asyncio
async def test_bind_once_idempotent_replay(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    r1 = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
        idempotency_key="bind-1",
    )
    assert r1.success and r1.action == "bind"
    assert r1.display_phone_last4 == "1234"
    conn_id = r1.connection_id

    r2 = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
        idempotency_key="bind-1",
    )
    assert r2.success and r2.action == "bind_idempotent"
    assert r2.connection_id == conn_id

    repo = WhatsAppCloudRepository(wa_db)
    active = [
        c for c in repo.list_tenant_connections("linas", include_revoked=False) if c.lifecycle_status == "connected"
    ]
    assert len(active) == 1
    assert active[0].connection_source == APP_REVIEW_SOURCE
    assert active[0].ai_default_enabled is True
    assert get_whatsapp_cloud_flags().public_availability is False


@pytest.mark.asyncio
async def test_reject_wrong_tenant(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="other",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "tenant_forbidden"


@pytest.mark.asyncio
async def test_reject_sample_phone_and_invalid_token(wa_db, monkeypatch):
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id="123456123",
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "sample_phone_forbidden"

    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", "short")
    with pytest.raises(AppReviewBindError) as exc2:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc2.value.code == "token_invalid"


@pytest.mark.asyncio
async def test_reject_expired_token_fail_closed(wa_db, monkeypatch):
    async def _bad(**kwargs: Any) -> dict[str, Any]:
        return {"is_valid": False}

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _bad)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "token_invalid"


@pytest.mark.asyncio
async def test_reject_token_issued_for_different_meta_app(wa_db, monkeypatch):
    async def _wrong_app(**kwargs: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "app_id": "9999999999999999",
            "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        }

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _wrong_app)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "token_app_mismatch"


@pytest.mark.asyncio
async def test_reject_phone_owned_by_other_tenant(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    repo = WhatsAppCloudRepository(wa_db)
    other = repo.create_connection_with_credential(
        tenant_id="chance",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id=TEST_PHONE,
        display_phone_number="+15550109999",
        verified_name="Other",
        access_token="other-token-xxxxxxxxxxxxxxxxxxxx",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(other, webhook_fields=["messages"])
    wa_db.commit()

    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "phone_owned_elsewhere"


@pytest.mark.asyncio
async def test_reject_phone_not_in_waba(wa_db, monkeypatch):
    async def _debug(**kwargs: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "app_id": "2963733803971681",
            "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        }

    async def _phones(**kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": "999", "display_phone_number": "+1 555 000 0000"}]

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _debug)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.fetch_waba_phone_numbers", _phones)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "phone_not_in_waba"


@pytest.mark.asyncio
async def test_status_not_connected_without_active_bind(wa_db):
    st = status_app_review_bind()
    assert st["active_count"] == 0
    assert st["connection"] is None
    assert st["public_availability"] is False


@pytest.mark.asyncio
async def test_resolver_and_unbind(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    bound = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    repo = WhatsAppCloudRepository(wa_db)
    found = repo.find_active_by_phone_number_id(TEST_PHONE)
    assert found is not None
    assert found.tenant_id == "linas"
    assert found.id == bound.connection_id

    st = status_app_review_bind()
    assert st["active_count"] == 1
    assert st["connection"]["lifecycle_status"] == "connected"
    assert st["connection"]["display_phone_last4"] == "1234"

    un = unbind_app_review_test_number(actor_user_id="po1")
    assert un.success and un.action == "unbind"
    assert repo.find_active_by_phone_number_id(TEST_PHONE) is None
    st2 = status_app_review_bind()
    assert st2["active_count"] == 0


@pytest.mark.asyncio
async def test_inbound_resolves_linas_uses_ai_bridge_not_canned(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )

    import json

    from services.whatsapp_cloud import webhook_processor as wp

    ai_calls: list[dict[str, Any]] = []

    async def fake_ai(snapshot):
        ai_calls.append(dict(snapshot))

    monkeypatch.setattr(wp, "maybe_generate_and_send_ai_reply", fake_ai)
    monkeypatch.setattr(wp, "evaluate_ai_eligibility", lambda session, c: (True, None))

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(wp, "whatsapp_session", _sess)
    monkeypatch.setattr("services.whatsapp_cloud.ai_bridge.whatsapp_session", _sess)

    inbound = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": TEST_WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": TEST_PHONE},
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.app-review-1",
                                    "type": "text",
                                    "text": {"body": "What is the unique Linas knowledge phrase?"},
                                    "timestamp": "1710000000",
                                }
                            ],
                            "contacts": [{"profile": {"name": "Reviewer"}, "wa_id": "15551234567"}],
                        },
                    }
                ],
            }
        ],
    }
    result = await wp.process_whatsapp_cloud_webhook(
        raw_body=json.dumps(inbound).encode(),
        payload=inbound,
    )
    assert result["accepted"] >= 1
    assert len(ai_calls) == 1
    assert ai_calls[0]["tenant_id"] == "linas"
    # No canned branch in ai_bridge — production path uses Customer Reply V2 + send_text_message.
    import inspect

    import services.whatsapp_cloud.ai_bridge as ai_bridge

    src = inspect.getsource(ai_bridge.maybe_generate_and_send_ai_reply)
    assert "run_customer_reply_v2_dm" in src
    assert "send_text_message" in src
    assert "canned" not in src.lower()
    assert "app_review" not in src.lower()


@pytest.mark.asyncio
async def test_embedded_signup_source_unchanged_and_cross_tenant(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    repo = WhatsAppCloudRepository(wa_db)
    normal = repo.create_connection_with_credential(
        tenant_id="linas",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="555",
        phone_number_id="555001",
        display_phone_number="+96170000001",
        verified_name="Normal",
        access_token="normal-token-xxxxxxxxxxxxxxxxxxxx",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    assert normal.connection_source == "embedded_signup"
    repo.mark_connection_connected(normal, webhook_fields=["messages"])
    wa_db.commit()

    await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    # Other tenant cannot resolve linas test phone.
    other_found = WhatsAppCloudRepository(wa_db).find_active_by_phone_number_id(TEST_PHONE)
    assert other_found is not None and other_found.tenant_id == "linas"

    unbind_app_review_test_number(actor_user_id="po1")
    # Normal Embedded Signup connection remains.
    still = repo.get_connection(normal.id)
    assert still is not None
    assert still.lifecycle_status == "connected"
    assert still.connection_source == "embedded_signup"
    assert get_whatsapp_cloud_flags().public_availability is False


@pytest.mark.asyncio
async def test_refuse_unbind_non_app_review(wa_db, monkeypatch):
    repo = WhatsAppCloudRepository(wa_db)
    normal = repo.create_connection_with_credential(
        tenant_id="linas",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="555",
        phone_number_id="555002",
        display_phone_number="+96170000002",
        verified_name="Normal",
        access_token="normal-token-xxxxxxxxxxxxxxxxxxxx",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(normal, webhook_fields=["messages"])
    wa_db.commit()
    with pytest.raises(AppReviewBindError) as exc:
        unbind_app_review_test_number(actor_user_id="po1", connection_id=normal.id)
    assert exc.value.code == "not_app_review_bind"


@pytest.mark.asyncio
async def test_unbind_idempotent_when_already_revoked(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    bound = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    first = unbind_app_review_test_number(actor_user_id="po1", connection_id=bound.connection_id)
    assert first.action == "unbind"
    second = unbind_app_review_test_number(actor_user_id="po1", connection_id=bound.connection_id)
    assert second.action == "unbind_idempotent"
    assert second.connection_id == bound.connection_id


@pytest.mark.asyncio
async def test_ai_bridge_uses_send_text_message(monkeypatch):
    """Outbound path remains the production Graph sender (no test-only branch)."""
    import services.whatsapp_cloud.ai_bridge as ai_bridge

    assert hasattr(ai_bridge, "send_text_message")
    # Ensure import is the graph client function, not a stub.
    assert ai_bridge.send_text_message.__module__ == "services.whatsapp_cloud.graph_client"
    assert AsyncMock  # keep import used for typing clarity in suite
