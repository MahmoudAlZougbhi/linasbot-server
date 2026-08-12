"""ASSN webhook must process without App Store API .p8 when JWS path is ok."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.apple_iap_effects import get_or_create_app_account_token  # noqa: E402
from services.apple_iap_processor import process_notification_v2  # noqa: E402
from services.credit_ledger_service import CreditLedgerService  # noqa: E402
from services.entitlements_service import EntitlementsStore  # noqa: E402


@pytest.fixture()
def apple_env_no_p8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_iap_no_p8.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.delenv("APPLE_IAP_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("APPLE_APP_STORE_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setenv("APPLE_IAP_PRIVATE_KEY_PATH", str(tmp_path / "missing-SubscriptionKey.p8"))
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    store = EntitlementsStore(root=tmp_path / "entitlements")
    ledger = CreditLedgerService(root=tmp_path / "credit_ledger")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr("services.apple_iap_effects.entitlements_store", store)
    monkeypatch.setattr("services.apple_credit_grant_ops.credit_ledger_service", ledger)
    monkeypatch.setattr("services.entitlements_service._DATA_ROOT", tmp_path)
    yield tmp_path
    reset_engine_for_tests()


@pytest.mark.asyncio
async def test_assn_webhook_works_without_p8(apple_env_no_p8: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.apple_app_store_client import iap_credentials_configured

    assert iap_credentials_configured() is False

    monkeypatch.setattr(
        "modules.apple_store_webhook_api.process_notification_v2",
        lambda _body: {
            "ok": True,
            "duplicate": False,
            "notification_uuid": "uuid-no-p8",
            "notification_type": "SUBSCRIBED",
        },
    )

    class _Req:
        async def json(self) -> dict[str, Any]:
            return {"signedPayload": "hdr.pay.sig"}

    from modules.apple_store_webhook_api import _handle_apple_assn

    result = await _handle_apple_assn(_Req())  # type: ignore[arg-type]
    assert result["success"] is True
    assert result["notification_uuid"] == "uuid-no-p8"


def test_process_notification_without_p8_when_decode_mocked(
    apple_env_no_p8: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.apple_app_store_client import iap_credentials_configured

    assert iap_credentials_configured() is False
    token = get_or_create_app_account_token(tenant_id="tenant_nop8", user_id="user_nop8")
    now_ms = 1_700_000_000_000
    txn = {
        "transactionId": "txn_nop8",
        "originalTransactionId": "txn_nop8",
        "productId": "com.linasai.subscription.basic.monthly",
        "bundleId": "com.linasai.app",
        "environment": "Sandbox",
        "type": "Auto-Renewable Subscription",
        "purchaseDate": now_ms,
        "expiresDate": now_ms + 30 * 86400 * 1000,
        "appAccountToken": token,
    }
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "SUBSCRIBED",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }

    def _decode(signed: str, **_kwargs: Any) -> dict[str, Any]:
        if signed == "signed.outer.nop8":
            return outer
        return txn

    monkeypatch.setattr("services.apple_iap_processor.decode_jws_payload", _decode)
    out = process_notification_v2({"signedPayload": "signed.outer.nop8"})
    assert out.get("ok") is True
    assert out.get("duplicate") is False

    from services.store_iap_service import verify_apple_notification_payload

    # Second call is a duplicate; must not raise for missing .p8 credentials.
    verify_out = verify_apple_notification_payload({"signedPayload": "signed.outer.nop8"})
    assert verify_out.get("event_id") == outer["notificationUUID"]
    assert verify_out.get("processor_result", {}).get("duplicate") is True
    assert verify_out.get("processor_result", {}).get("ok") is True
