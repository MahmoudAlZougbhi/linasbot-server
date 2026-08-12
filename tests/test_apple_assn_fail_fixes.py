"""ASSN typed mapping, signedRenewalInfo, claim-before-effect (FAIL #8/#9/#12)."""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.apple_billing import AppleNotificationEventRow  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.apple_assn_types import classify_assn_action, status_for_notification_type  # noqa: E402
from services.apple_iap_effects import get_or_create_app_account_token  # noqa: E402
from services.apple_iap_processor import process_notification_v2  # noqa: E402
from services.apple_notification_claim import claim_notification, finalize_notification  # noqa: E402
from services.credit_ledger_service import CreditLedgerService  # noqa: E402
from services.entitlements_service import EntitlementsStore  # noqa: E402
from services.store_iap_service import normalize_apple_status  # noqa: E402


@pytest.fixture()
def apple_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_assn.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("APPLE_IAP_ISSUER_ID", "a3b052c7-c0ed-4935-8e2e-4b57946e1f6b")
    monkeypatch.setenv("APPLE_IAP_KEY_ID", "8H9SZG552B")
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
    monkeypatch.setattr("services.apple_credit_grant_ops.credit_ledger_service", ledger)
    monkeypatch.setattr("services.apple_renewal_info.entitlements_store", store)
    monkeypatch.setattr("services.entitlements_service._DATA_ROOT", tmp_path)
    yield tmp_path
    reset_engine_for_tests()


def _sub_payload(
    *,
    transaction_id: str,
    product_id: str = "com.linasai.subscription.basic.monthly",
    app_account_token: str | None = None,
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
        "expiresDate": now_ms + 30 * 86400 * 1000,
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


def _patch_decode(
    monkeypatch: pytest.MonkeyPatch,
    *,
    outer: dict[str, Any],
    txn: dict[str, Any] | None = None,
    renewal: dict[str, Any] | None = None,
    outer_token: str = "signed.outer.payload",
    txn_token: str = "t.x.n",
    renewal_token: str = "r.e.n",
) -> None:
    def _decode(token: str, **_kwargs: Any) -> dict[str, Any]:
        if token == outer_token:
            return outer
        if token == renewal_token and renewal is not None:
            return renewal
        if txn is not None:
            return txn
        raise AssertionError(f"unexpected jws token {token!r}")

    monkeypatch.setattr("services.apple_iap_processor.decode_jws_payload", _decode)
    monkeypatch.setattr("services.apple_renewal_info.decode_jws_payload", _decode)


# --- A) typed mapping unit tests ---


def test_classify_metadata_only_types_not_active() -> None:
    for ntype in ("PRICE_INCREASE", "RENEWAL_EXTENDED", "DID_CHANGE_RENEWAL_PREF"):
        c = classify_assn_action(ntype)
        assert c["action"] == "metadata"
        assert c["effect_kind"] == "metadata_only"
        assert c["status"] is None
        with pytest.raises(ValueError):
            normalize_apple_status(ntype)
        assert status_for_notification_type(ntype) is None


def test_classify_one_time_charge_consumable_only() -> None:
    c = classify_assn_action("ONE_TIME_CHARGE")
    assert c["action"] == "apply_txn"
    assert c["effect_kind"] == "consumable_only"
    assert c["status"] is None


def test_classify_unknown_not_active() -> None:
    c = classify_assn_action("TOTALLY_UNKNOWN_TYPE_XYZ")
    assert c["action"] == "ignore"
    assert c["effect_kind"] == "failed_unknown_type"
    assert c["status"] is None
    with pytest.raises(ValueError, match="unknown ASSN"):
        status_for_notification_type("TOTALLY_UNKNOWN_TYPE_XYZ")
    with pytest.raises(ValueError):
        normalize_apple_status("TOTALLY_UNKNOWN_TYPE_XYZ")


def test_normalize_no_longer_defaults_active() -> None:
    assert normalize_apple_status("SUBSCRIBED") == "active"
    assert normalize_apple_status("DID_FAIL_TO_RENEW") == "grace"
    assert normalize_apple_status("GRACE_PERIOD") == "grace"
    assert normalize_apple_status("BILLING_RETRY") == "grace"
    assert normalize_apple_status("EXPIRED") == "expired"
    assert normalize_apple_status("REFUND") == "refunded"
    assert normalize_apple_status("REVOKE") == "revoked"
    assert normalize_apple_status("DID_CHANGE_RENEWAL_STATUS") == "canceled"


# --- Processor per-type: must not become active ---


@pytest.mark.parametrize(
    "ntype",
    ["PRICE_INCREASE", "RENEWAL_EXTENDED", "DID_CHANGE_RENEWAL_PREF"],
)
def test_processor_metadata_types_not_active(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch, ntype: str
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_meta", user_id="user_meta")
    txn = _sub_payload(transaction_id=f"txn_meta_{ntype}", app_account_token=token)
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": ntype,
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn)
    out = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert out.get("duplicate") is False
    assert out["classification"]["status"] is None
    assert out["classification"]["effect_kind"] == "metadata_only"
    from services.entitlements_service import entitlements_store

    ent = entitlements_store.get("tenant_meta")
    # Fresh tenant: metadata-only must not activate.
    assert ent.status == "none"


def test_processor_one_time_charge_consumable(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_otc", user_id="user_otc")
    txn = _credit_payload(transaction_id="txn_otc_1", app_account_token=token)
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "ONE_TIME_CHARGE",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn)
    out = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert out.get("ok") is True
    effect = out["effect"]
    nested = effect.get("effect") if isinstance(effect.get("effect"), dict) else effect
    assert int(nested.get("credits") or 0) == 2500
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_otc").extra_credits == 2500
    assert entitlements_store.get("tenant_otc").status == "none"


def test_processor_one_time_charge_subscription_skipped(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_otc_sub", user_id="u")
    txn = _sub_payload(transaction_id="txn_otc_sub", app_account_token=token)
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "ONE_TIME_CHARGE",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn)
    out = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert out["effect"].get("skipped") is True
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_otc_sub").status == "none"


def test_processor_unknown_type_ignored_no_effect(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_unk", user_id="u")
    txn = _sub_payload(transaction_id="txn_unk", app_account_token=token)
    nuid = str(uuid.uuid4())
    outer = {
        "notificationUUID": nuid,
        "notificationType": "FUTURE_APPLE_TYPE_99",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn)
    out = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert out.get("reason") == "failed_unknown_type"
    assert out["classification"]["action"] == "ignore"
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_unk").status == "none"
    with whatsapp_session() as session:
        row = session.get(AppleNotificationEventRow, nuid)
        assert row is not None
        assert row.processing_status == "ignored"


# --- B) signedRenewalInfo ---


def test_signed_renewal_info_grace_and_cancel(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_ren", user_id="user_ren")
    txn = _sub_payload(transaction_id="txn_ren_1", app_account_token=token)
    # First activate via SUBSCRIBED
    outer_sub = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "SUBSCRIBED",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer_sub, txn=txn)
    process_notification_v2({"signedPayload": "signed.outer.payload"})

    now_ms = int(time.time() * 1000)
    renewal = {
        "originalTransactionId": "txn_ren_1",
        "autoRenewStatus": 0,
        "autoRenewProductId": "com.linasai.subscription.basic.monthly",
        "gracePeriodExpiresDate": now_ms + 3 * 86400 * 1000,
        "isInBillingRetryPeriod": True,
        "priceIncreaseStatus": 0,
        "expirationIntent": 1,
        "renewalDate": now_ms + 30 * 86400 * 1000,
    }
    outer = {
        "notificationUUID": str(uuid.uuid4()),
        "notificationType": "DID_FAIL_TO_RENEW",
        "data": {
            "environment": "Sandbox",
            "signedTransactionInfo": "t.x.n",
            "signedRenewalInfo": "r.e.n",
        },
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn, renewal=renewal)
    out = process_notification_v2({"signedPayload": "signed.outer.payload"})
    assert "renewal" in out
    assert out["renewal"]["forced_active"] is False
    assert out["renewal"]["renewal_info"]["autoRenewStatus"] == 0
    assert out["renewal"]["renewal_info"]["isInBillingRetryPeriod"] is True
    assert out["renewal"]["hints"]["lifecycle"] == "grace"
    from services.entitlements_service import entitlements_store

    ent = entitlements_store.get("tenant_ren")
    assert ent.status == "grace"


# --- C) claim-before-effect / concurrent ---


def test_claim_integrity_duplicate_path(apple_env: Path) -> None:
    nuid = str(uuid.uuid4())
    first = claim_notification(
        notification_uuid=nuid,
        notification_type="SUBSCRIBED",
        subtype=None,
        environment="Sandbox",
        signed_payload_sha256="abc",
    )
    assert first["duplicate"] is False
    assert first["claimed"] is True
    second = claim_notification(
        notification_uuid=nuid,
        notification_type="SUBSCRIBED",
        subtype=None,
        environment="Sandbox",
        signed_payload_sha256="abc",
    )
    assert second["duplicate"] is True
    assert second["processing_status"] == "processing"
    finalize_notification(
        notification_uuid=nuid,
        processing_status="applied",
        result={"ok": True},
    )
    third = claim_notification(
        notification_uuid=nuid,
        notification_type="SUBSCRIBED",
        subtype=None,
        environment="Sandbox",
        signed_payload_sha256="abc",
    )
    assert third["duplicate"] is True
    assert third["processing_status"] == "applied"


def test_failed_can_be_redriven(apple_env: Path) -> None:
    nuid = str(uuid.uuid4())
    claim_notification(
        notification_uuid=nuid,
        notification_type="SUBSCRIBED",
        subtype=None,
        environment="Sandbox",
        signed_payload_sha256="x",
    )
    finalize_notification(notification_uuid=nuid, processing_status="failed", result={"failed": True})
    again = claim_notification(
        notification_uuid=nuid,
        notification_type="SUBSCRIBED",
        subtype=None,
        environment="Sandbox",
        signed_payload_sha256="x",
    )
    assert again["duplicate"] is False
    assert again.get("retried") is True


def test_concurrent_notification_one_effect(
    apple_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = get_or_create_app_account_token(tenant_id="tenant_race", user_id="user_race")
    txn = _sub_payload(transaction_id="txn_race_1", app_account_token=token)
    nuid = str(uuid.uuid4())
    outer = {
        "notificationUUID": nuid,
        "notificationType": "SUBSCRIBED",
        "data": {"environment": "Sandbox", "signedTransactionInfo": "t.x.n"},
    }
    _patch_decode(monkeypatch, outer=outer, txn=txn)

    results: list[dict[str, Any]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _worker() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(process_notification_v2({"signedPayload": "signed.outer.payload"}))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errors, errors
    assert len(results) == 2
    dup_flags = sorted(bool(r.get("duplicate")) for r in results)
    # SQLite may serialize; still exactly one non-duplicate effect path.
    assert dup_flags == [False, True]
    from services.entitlements_service import entitlements_store

    assert entitlements_store.get("tenant_race").plan_id == "lite"
    assert entitlements_store.get("tenant_race").status == "active"
    with whatsapp_session() as session:
        row = session.get(AppleNotificationEventRow, nuid)
        assert row is not None
        assert row.processing_status == "applied"
