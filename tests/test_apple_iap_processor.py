"""Apple IAP processor: idempotency, refund reverse, notification replay, cross-tenant."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.apple_billing import AppleAppAccountTokenRow  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.apple_iap_effects import get_or_create_app_account_token  # noqa: E402
from services.apple_iap_processor import (  # noqa: E402
    process_notification_v2,
    process_signed_transaction,
)
from services.credit_ledger_service import CreditLedgerService  # noqa: E402
from services.entitlements_service import EntitlementsStore  # noqa: E402


@pytest.fixture()
def apple_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_iap.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("APPLE_IAP_ISSUER_ID", "a3b052c7-c0ed-4935-8e2e-4b57946e1f6b")
    monkeypatch.setenv("APPLE_IAP_KEY_ID", "8H9SZG552B")
    # Point at a dummy path that exists so credentials_configured is true in webhook paths.
    key_path = tmp_path / "SubscriptionKey_TEST.p8"
    key_path.write_text(
        "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgTEST\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPLE_IAP_PRIVATE_KEY_PATH", str(key_path))
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    ent_root = tmp_path / "entitlements"
    ledger_root = tmp_path / "credit_ledger"
    store = EntitlementsStore(root=ent_root)
    ledger = CreditLedgerService(root=ledger_root)
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr("services.apple_iap_effects.entitlements_store", store)
    monkeypatch.setattr("services.apple_iap_effects.credit_ledger_service", ledger)
    monkeypatch.setattr(
        "services.entitlements_service._DATA_ROOT",
        tmp_path,
    )
    yield tmp_path
    reset_engine_for_tests()


def _sub_payload(
    *,
    transaction_id: str,
    product_id: str = "com.linasai.subscription.basic.monthly",
    app_account_token: str | None = None,
    expires_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    data: dict[str, Any] = {
        "transactionId": transaction_id,
        "originalTransactionId": transaction_id,
        "productId": product_id,
        "bundleId": "com.linasai.app",
        "environment": "Sandbox",
        "type": "Auto-Renewable Subscription",
        "purchaseDate": now_ms,
        "expiresDate": expires_ms or (now_ms + 30 * 86400 * 1000),
    }
    if app_account_token:
        data["appAccountToken"] = app_account_token
    return data


def _credit_payload(
    *,
    transaction_id: str,
    product_id: str = "com.linasai.credits.2500",
    app_account_token: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "transactionId": transaction_id,
        "originalTransactionId": transaction_id,
        "productId": product_id,
        "bundleId": "com.linasai.app",
        "environment": "Sandbox",
        "type": "Consumable",
        "purchaseDate": int(time.time() * 1000),
    }
    if app_account_token:
        data["appAccountToken"] = app_account_token
    return data


def test_idempotent_subscription_apply(apple_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _sub_payload(transaction_id="txn_sub_1")
    monkeypatch.setattr(
        "services.apple_iap_processor.decode_jws_payload",
        lambda *_a, **_k: payload,
    )
    first = process_signed_transaction(
        signed_transaction_jws="a.b.c",
        tenant_id="tenant_a",
        user_id="user_a",
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    second = process_signed_transaction(
        signed_transaction_jws="a.b.c",
        tenant_id="tenant_a",
        user_id="user_a",
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    assert first["ok"] is True
    assert first.get("duplicate") is False
    assert second.get("duplicate") is True
    from services.entitlements_service import entitlements_store

    ent = entitlements_store.get("tenant_a")
    assert ent.plan_id == "lite"
    assert ent.status == "active"
    assert ent.source == "apple"


def test_idempotent_credit_grant(apple_env: Path) -> None:
    payload = _credit_payload(transaction_id="txn_cred_1")
    first = process_signed_transaction(
        signed_transaction_jws="x.y.z",
        tenant_id="tenant_c",
        user_id="user_c",
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    second = process_signed_transaction(
        signed_transaction_jws="x.y.z",
        tenant_id="tenant_c",
        user_id="user_c",
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    assert first["ok"] is True
    assert first["effect"]["credits"] == 2500
    assert second.get("duplicate") is True
    from services.credit_ledger_service import credit_ledger_service
    from services.entitlements_service import entitlements_store

    assert credit_ledger_service.get_balance("tenant_c") >= 2500
    assert entitlements_store.get("tenant_c").extra_credits == 2500


def test_refund_reverse_once(apple_env: Path) -> None:
    payload = _credit_payload(transaction_id="txn_cred_ref")
    process_signed_transaction(
        signed_transaction_jws="r.e.f",
        tenant_id="tenant_r",
        user_id="user_r",
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    from services.apple_iap_effects import reverse_consumable_credits
    from services.credit_ledger_service import credit_ledger_service
    from services.entitlements_service import entitlements_store

    first = reverse_consumable_credits(
        tenant_id="tenant_r", transaction_id="txn_cred_ref", product_id=payload["productId"]
    )
    second = reverse_consumable_credits(
        tenant_id="tenant_r", transaction_id="txn_cred_ref", product_id=payload["productId"]
    )
    assert first.get("duplicate") is not True
    assert second.get("duplicate") is True
    assert entitlements_store.get("tenant_r").extra_credits == 0
    assert credit_ledger_service.get_balance("tenant_r") == 0


def test_notification_replay(apple_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    txn = _sub_payload(transaction_id="txn_notify_1")
    token = get_or_create_app_account_token(tenant_id="tenant_n", user_id="user_n")
    txn["appAccountToken"] = token
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "SUBSCRIBED",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }

    def _decode(token: str, **_kwargs: Any) -> dict[str, Any]:
        if token == "signed.outer.payload":
            return outer
        return txn

    monkeypatch.setattr("services.apple_iap_processor.decode_jws_payload", _decode)
    first = process_notification_v2({"signedPayload": "signed.outer.payload"})
    second = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert first.get("duplicate") is False
    assert second.get("duplicate") is True
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_n").plan_id == "lite"


def test_cross_tenant_app_account_token_denied(apple_env: Path) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_a", user_id="user_a")
    payload = _credit_payload(transaction_id="txn_x", app_account_token=token)
    with pytest.raises(PermissionError):
        process_signed_transaction(
            signed_transaction_jws="c.r.o",
            tenant_id="tenant_b",
            user_id="user_b",
            source="test",
            decoded_payload=payload,
            skip_jws_verify=True,
        )
    # Token alone resolves to tenant_a and grants there — not tenant_b.
    ok = process_signed_transaction(
        signed_transaction_jws="c.r.o",
        tenant_id=None,
        source="test",
        decoded_payload=payload,
        skip_jws_verify=True,
    )
    assert ok["tenant_id"] == "tenant_a"
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_b").extra_credits == 0
    assert entitlements_store.get("tenant_a").extra_credits == 2500


def test_client_verify_requires_app_account_token(apple_env: Path) -> None:
    payload = _credit_payload(transaction_id="txn_client_no_token")
    with pytest.raises(PermissionError, match="appAccountToken required"):
        process_signed_transaction(
            signed_transaction_jws="c.l.i",
            tenant_id="tenant_z",
            user_id="user_z",
            source="client_verify",
            decoded_payload=payload,
            skip_jws_verify=True,
        )


def test_app_account_token_stable(apple_env: Path) -> None:
    a = get_or_create_app_account_token(tenant_id="t1", user_id="u1")
    b = get_or_create_app_account_token(tenant_id="t1", user_id="u1")
    assert a == b
    with whatsapp_session() as session:
        row = session.get(AppleAppAccountTokenRow, a)
        assert row is not None
        assert row.tenant_id == "t1"
