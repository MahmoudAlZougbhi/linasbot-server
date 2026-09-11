"""Temporary Meta App Review WhatsApp bind — bind/status/unbind isolation tests."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, select
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
)
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags  # noqa: E402
from services.whatsapp_cloud.graph_client import WhatsAppGraphError  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402

TEST_WABA = "900100200300"
TEST_PHONE = "900100200301"
TEST_TOKEN = "EAAG-test-token-never-log-" + ("y" * 40)
ROTATED_TOKEN = "EAAG-rotated-token-never-log-" + ("z" * 40)


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_app_review.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS", TEST_WABA)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()

    @contextmanager
    def _sess(*, require: bool = True):
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise

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
async def test_connected_app_review_credential_rotates_atomically_after_validation(
    wa_db,
    monkeypatch,
):
    from db.models.whatsapp_cloud import WhatsAppAuditEvent, WhatsAppCredential

    _mock_meta_ok(monkeypatch)
    first = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    repo = WhatsAppCloudRepository(wa_db)
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    original_connection_id = connection.id
    original_credential_id = connection.credential_id
    assert connection.credential_generation == 1

    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", ROTATED_TOKEN)
    preview = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
        dry_run=True,
    )
    assert preview.action == "dry_run"
    assert preview.detail["planned_action"] == "credential_rotate"
    assert preview.detail["credential_change_required"] is True
    assert ROTATED_TOKEN not in str(preview.public_dict())
    assert repo.load_access_token(connection) == TEST_TOKEN

    rotated = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    assert rotated.action == "credential_rotated"
    assert rotated.connection_id == original_connection_id
    assert rotated.public_dict()["public_availability"] is False
    wa_db.expire_all()
    connection = repo.get_connection(original_connection_id)
    assert connection is not None
    assert connection.lifecycle_status == "connected"
    assert connection.credential_id == original_credential_id
    assert connection.credential_generation == 2
    assert repo.load_access_token(connection) == ROTATED_TOKEN
    credentials = list(
        wa_db.scalars(select(WhatsAppCredential).where(WhatsAppCredential.connection_id == connection.id)).all()
    )
    assert len(credentials) == 1
    assert credentials[0].generation == 2
    audits = list(
        wa_db.scalars(
            select(WhatsAppAuditEvent).where(
                WhatsAppAuditEvent.connection_id == connection.id,
                WhatsAppAuditEvent.event_type == "app_review_credential_rotated",
            )
        ).all()
    )
    assert len(audits) == 1
    assert audits[0].detail["previous_generation"] == 1
    assert audits[0].detail["credential_generation"] == 2


@pytest.mark.asyncio
async def test_rotation_invalid_token_leaves_connected_credential_untouched(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    first = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    repo = WhatsAppCloudRepository(wa_db)
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    credential_id = connection.credential_id
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", ROTATED_TOKEN)

    async def _invalid(**kwargs: Any) -> dict[str, Any]:
        return {"is_valid": False}

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _invalid)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "token_invalid"
    wa_db.expire_all()
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    assert connection.lifecycle_status == "connected"
    assert connection.credential_id == credential_id
    assert connection.credential_generation == 1
    assert repo.load_access_token(connection) == TEST_TOKEN


@pytest.mark.asyncio
async def test_rotation_same_token_is_idempotent_without_subscribe_or_generation_change(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    first = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    repo = WhatsAppCloudRepository(wa_db)
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    credential_id = connection.credential_id

    async def _unexpected_subscribe(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("same-token replay must not resubscribe")

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind.subscribe_waba_webhooks", _unexpected_subscribe)
    replay = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    assert replay.action == "bind_idempotent"
    wa_db.expire_all()
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    assert connection.credential_id == credential_id
    assert connection.credential_generation == 1
    assert repo.load_access_token(connection) == TEST_TOKEN


@pytest.mark.asyncio
async def test_rotation_rejects_revoked_connection_without_resurrecting_credential(wa_db, monkeypatch):
    from db.models.whatsapp_cloud import WhatsAppCredential

    _mock_meta_ok(monkeypatch)
    first = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
    )
    repo = WhatsAppCloudRepository(wa_db)
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    credential = wa_db.get(WhatsAppCredential, connection.credential_id)
    assert credential is not None
    repo.revoke_connection(connection, actor_user_id="po2", reason="concurrent_disconnect")
    wa_db.commit()

    with pytest.raises(PermissionError, match="credential_rotation_state_conflict"):
        repo.rotate_connection_credential(
            connection,
            access_token=ROTATED_TOKEN,
            scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
            expected_generation=1,
        )

    wa_db.expire_all()
    connection = repo.get_connection(first.connection_id)
    assert connection is not None
    assert connection.lifecycle_status == "revoked"
    credential = wa_db.get(WhatsAppCredential, connection.credential_id)
    assert credential is not None
    assert credential.revoked_at is not None
    assert credential.generation == 1


@pytest.mark.asyncio
async def test_subscribe_failure_rolls_back_active_bind(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)

    async def _fail_subscribe(**kwargs: Any) -> dict[str, Any]:
        raise WhatsAppGraphError("subscribe_failed", "Meta rejected subscription", http_status=400)

    monkeypatch.setattr(
        "services.whatsapp_cloud.app_review_bind.subscribe_waba_webhooks",
        _fail_subscribe,
    )
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "waba_subscribe_failed"
    repo = WhatsAppCloudRepository(wa_db)
    assert repo.find_active_by_phone_number_id(TEST_PHONE) is None
    assert repo.list_tenant_connections("linas", include_revoked=True) == []


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
async def test_reject_missing_waba_allowlist(wa_db, monkeypatch):
    monkeypatch.delenv("META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS", raising=False)
    with pytest.raises(AppReviewBindError) as exc:
        await bind_app_review_test_number(
            tenant_id="linas",
            waba_id=TEST_WABA,
            phone_number_id=TEST_PHONE,
            access_token=None,
            actor_user_id="po1",
        )
    assert exc.value.code == "waba_allowlist_required"


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
