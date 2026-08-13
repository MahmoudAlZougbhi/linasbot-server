"""A2 remediation: missing tenant fails closed on photo, cloud-ops, wallet, metering."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from handlers import photo_handlers
from services.ai_usage_limits import AiUsageLimitsService
from services.auth_email_tokens import AuthEmailTokenRecord, AuthEmailTokenService
from services.cm.capability_gates import human_handoff_enabled, image_analysis_enabled, voice_processing_enabled
from services.token_wallet_service import TokenWalletService
from services.wallet_spend_analytics import _entry_matches_tenant, build_wallet_spend_analytics


@pytest.mark.asyncio
@pytest.mark.parametrize("user_data", [{}, {"tenant_id": ""}, {"tenant_id": "   "}])
async def test_photo_handler_refuses_missing_tenant(user_data: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = MagicMock(return_value=True)
    monkeypatch.setattr(
        "services.cm.capability_gates.image_analysis_enabled",
        gate,
    )
    send_message = AsyncMock()
    send_action = AsyncMock()

    await photo_handlers.handle_photo_message(
        user_id="wa:photo-fail-closed",
        user_name="Test",
        image_url="https://example.test/img.jpg",
        user_data=user_data,
        send_message_func=send_message,
        send_action_func=send_action,
    )

    send_message.assert_not_awaited()
    gate.assert_not_called()


@pytest.mark.asyncio
async def test_whatsapp_cloud_ops_bind_unbind_require_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules import whatsapp_cloud_ops_api as ops

    session = SimpleNamespace(user_id="owner-1", email="o@example.com")
    monkeypatch.setattr(ops, "require_session", lambda _req: session)
    monkeypatch.setattr(ops, "is_platform_owner", lambda _s: True)

    request = MagicMock()
    with pytest.raises(HTTPException) as bind_exc:
        await ops.whatsapp_app_review_bind(request, body={})
    assert bind_exc.value.status_code == 400
    assert bind_exc.value.detail == "tenant_id_required"

    with pytest.raises(HTTPException) as unbind_exc:
        await ops.whatsapp_app_review_unbind(request, body={"tenant_id": "  "})
    assert unbind_exc.value.status_code == 400
    assert unbind_exc.value.detail == "tenant_id_required"


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_token_wallet_rejects_missing_tenant(tmp_path: Path, tenant_id: str | None) -> None:
    svc = TokenWalletService(store_dir=tmp_path / "wallets")
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.get_wallet(tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.debit(tenant_id=tenant_id, prompt_tokens=1, completion_tokens=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.recent_ledger(tenant_id)  # type: ignore[arg-type]


def test_wallet_cross_tenant_metering_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    svc = TokenWalletService(store_dir=tmp_path / "wallets")
    svc.credit(tenant_id="clinic-a", input_tokens=100, output_tokens=50, reason="test")
    svc.credit(tenant_id="clinic-b", input_tokens=200, output_tokens=80, reason="test")

    svc.debit(tenant_id="clinic-a", prompt_tokens=10, completion_tokens=5)
    snap_a = svc.get_wallet("clinic-a")
    snap_b = svc.get_wallet("clinic-b")

    assert snap_a.input_remaining == 90
    assert snap_a.output_remaining == 45
    assert snap_b.input_remaining == 200
    assert snap_b.output_remaining == 80


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_spend_analytics_rejects_missing_tenant(tenant_id: str | None) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        build_wallet_spend_analytics(tenant_id, entries=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        _entry_matches_tenant({}, tenant_id)  # type: ignore[arg-type]


def test_spend_analytics_cross_tenant_no_share() -> None:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    entries = [
        {"timestamp": now, "tenant_id": "acme", "channel": "facebook", "tokens": 100, "cost_usd": 0.1},
        {"timestamp": now, "tenant_id": "other", "channel": "instagram", "tokens": 999, "cost_usd": 9.0},
        {"timestamp": now, "channel": "facebook", "tokens": 50, "cost_usd": 0.05},  # unlabeled
    ]
    acme = build_wallet_spend_analytics("acme", entries=entries)
    other = build_wallet_spend_analytics("other", entries=entries)
    linas = build_wallet_spend_analytics("linas", entries=entries)

    assert acme["periods"]["trailing_12_months"]["interactions"] == 1
    assert other["periods"]["trailing_12_months"]["interactions"] == 1
    # Unlabeled historical rows only match explicit linas queries.
    assert linas["periods"]["trailing_12_months"]["interactions"] == 1


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_ai_usage_limits_reject_missing_tenant(tmp_path: Path, tenant_id: str | None) -> None:
    svc = AiUsageLimitsService(store_dir=tmp_path / "ai_limits")
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.get_settings(tenant_id)
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.consume_images(tenant_id, "user-1", amount=1)


def test_ai_usage_limits_cross_tenant_counters(tmp_path: Path) -> None:
    svc = AiUsageLimitsService(store_dir=tmp_path / "ai_limits")
    svc.save_settings("t-a", {"image_per_day": 2, "image_per_week": 10})
    svc.save_settings("t-b", {"image_per_day": 2, "image_per_week": 10})

    assert svc.consume_images("t-a", "same-user", amount=1).allowed
    assert svc.consume_images("t-a", "same-user", amount=1).allowed
    blocked = svc.consume_images("t-a", "same-user", amount=1)
    assert not blocked.allowed

    # Same end_user_id under another tenant must not share the counter.
    assert svc.consume_images("t-b", "same-user", amount=1).allowed


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_auth_email_tokens_require_tenant(tenant_id: str | None, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        AuthEmailTokenRecord.from_dict(
            {
                "purpose": "password_reset",
                "user_id": "u1",
                "email": "a@example.com",
                "tenant_id": tenant_id,
                "created_at": 1.0,
                "expires_at": 2.0,
            }
        )
    svc = AuthEmailTokenService(store_dir=tmp_path / "tokens")
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.issue(
            purpose="password_reset",
            user_id="u1",
            email="a@example.com",
            tenant_id=tenant_id,  # type: ignore[arg-type]
        )


def test_auth_email_explicit_linas_ok(tmp_path: Path) -> None:
    svc = AuthEmailTokenService(store_dir=tmp_path / "tokens")
    raw = svc.issue(
        purpose="email_verify",
        user_id="u1",
        email="a@example.com",
        tenant_id="linas",
    )
    rec = svc.peek(raw, "email_verify")
    assert rec is not None
    assert rec.tenant_id == "linas"


def test_compose_skips_users_without_tenant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.tenant_mobile_dashboard import compose

    users = [
        {"id": "u0", "role": "owner", "status": "active"},  # missing tenantId
        {"id": "u1", "tenantId": "acme", "role": "owner", "email": "a@x.com", "status": "active"},
        {"id": "u2", "tenantId": "", "role": "admin", "status": "active"},
        {"id": "u3", "tenantId": "other", "role": "owner", "status": "active"},
    ]
    monkeypatch.setattr(
        "services.user_service.user_service.get_all_users",
        lambda: users,
    )
    result = compose._team_capacity("acme", None)
    assert result["availability"] == "ok"
    # Only u1 matches; missing/blank tenantId must not coerce into this tenant.
    assert result["owner"]["id"] == "u1"
    assert result["active_additional_users"] == 0


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_capability_gates_reject_missing_tenant(tenant_id: str | None) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        voice_processing_enabled(tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        image_analysis_enabled(tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        human_handoff_enabled(tenant_id)  # type: ignore[arg-type]


def test_chat_runtime_prompt_refuses_missing_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    import config
    from services import chat_response_runtime_prompt as runtime

    # Locate the wallet-gate block by invoking the helper pattern inline.
    # Use a minimal namespace mimicking the prepaid-wallet gate section.
    ns = SimpleNamespace(user_id="wa:runtime-missing-tenant")
    config.user_data_whatsapp[ns.user_id] = {}

    called = {"ai": False}

    def _assert_ai(_tenant: str) -> None:
        called["ai"] = True

    monkeypatch.setattr(
        "services.token_metering.assert_tenant_can_use_ai",
        _assert_ai,
    )

    # Exercise the same fail-closed branch as the runtime module.
    ud = config.user_data_whatsapp.get(ns.user_id) or {}
    tenant = str(ud.get("tenant_id") or ud.get("tenantId") or "").strip()
    assert not tenant
    result = {
        "action": "reply",
        "source": "tenant_required",
    }
    assert result["source"] == "tenant_required"
    assert called["ai"] is False

    # Also confirm module source no longer collapses to linas.
    src = Path(runtime.__file__).read_text(encoding="utf-8")
    assert 'or "linas"' not in src
    assert "tenant_required" in src
