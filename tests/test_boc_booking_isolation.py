"""Phase 8: BOC / LinasLaser Agent booking isolation (default OFF)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.product_features import (
    BOC_BOOKING_DISABLED_CODE,
    BOC_BOOKING_ENABLED_ENV,
    LEGACY_BOOKING_TOOL_NAMES,
    boc_appointment_jobs_allowed,
    boc_booking_enabled,
    boc_booking_readiness,
    boc_disabled_response,
    boc_job_skipped_response,
    legacy_booking_tools_disabled,
)
from utils.utils import get_openai_tools_schema


@pytest.fixture(autouse=True)
def _boc_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BOC_BOOKING_ENABLED_ENV, raising=False)


def test_boc_gate_defaults_off() -> None:
    assert boc_booking_enabled() is False
    assert legacy_booking_tools_disabled() is True
    assert boc_appointment_jobs_allowed() is False


def test_boc_gate_explicit_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BOC_BOOKING_ENABLED_ENV, "true")
    assert boc_booking_enabled() is True
    assert legacy_booking_tools_disabled() is False
    assert boc_appointment_jobs_allowed() is True


def test_disabled_response_is_honest_not_fallback() -> None:
    payload = boc_disabled_response(operation="GET branches")
    assert payload["success"] is False
    assert payload["error"] == BOC_BOOKING_DISABLED_CODE
    assert payload["boc_booking_enabled"] is False
    assert "No network call" in payload["message"]
    assert "fallback" not in payload["message"].lower()


def test_legacy_booking_tools_hidden_when_disabled() -> None:
    assert legacy_booking_tools_disabled() is True
    tools = get_openai_tools_schema(excluded_tool_names=set(LEGACY_BOOKING_TOOL_NAMES))
    names = {t["function"]["name"] for t in tools}
    for banned in ("submit_booking_intent", "create_appointment", "get_available_slots", "get_branches"):
        assert banned not in names
        assert banned in LEGACY_BOOKING_TOOL_NAMES


@pytest.mark.asyncio
async def test_make_api_request_zero_http_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import api_integrations_http as http_mod

    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client.post = AsyncMock()
    monkeypatch.setattr(http_mod, "api_client", mock_client)

    result = await http_mod._make_api_request("GET", "branches")
    assert result["success"] is False
    assert result["error"] == BOC_BOOKING_DISABLED_CODE
    mock_client.get.assert_not_called()
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_make_api_request_calls_http_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import api_integrations_http as http_mod

    monkeypatch.setenv(BOC_BOOKING_ENABLED_ENV, "true")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "data": []}
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(http_mod, "api_client", mock_client)

    result = await http_mod._make_api_request("GET", "branches")
    assert result.get("success") is True
    mock_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_status_zero_http_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import api_integrations_http as http_mod

    mock_client = MagicMock()
    mock_client.post = AsyncMock()
    monkeypatch.setattr(http_mod, "api_client", mock_client)

    result = await http_mod._post_update_status_logged("https://example.com/api/x", {"ids": [1]})
    assert result["error"] == BOC_BOOKING_DISABLED_CODE
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_appointment_jobs_do_not_start_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import appointment_scheduler as aps
    from services import appointment_scheduler_followups as followups
    from services import appointment_scheduler_missed as missed

    http_spy = AsyncMock(side_effect=AssertionError("BOC HTTP must not run when disabled"))
    monkeypatch.setattr("services.api_integrations.send_appointment_reminders", http_spy)
    monkeypatch.setattr("services.api_integrations.get_paused_appointments_between_dates", http_spy)

    for coro in (
        aps.populate_scheduled_messages_from_appointments(),
        followups.populate_missed_yesterday_messages(),
        followups.populate_one_month_followups(),
        missed.populate_missed_month_messages(),
    ):
        out = await coro
        assert out["job_started"] is False
        assert out["skipped"] is True
        assert out["error"] == BOC_BOOKING_DISABLED_CODE

    http_spy.assert_not_called()


@pytest.mark.asyncio
async def test_populate_job_wrappers_no_start_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules import event_handlers_populate_jobs as jobs

    called = {"n": 0}

    async def _boom() -> dict:
        called["n"] += 1
        raise AssertionError("populate must not start when BOC is off")

    monkeypatch.setattr(jobs, "populate_scheduled_messages_from_appointments", _boom)
    monkeypatch.setattr(jobs, "populate_one_month_followups", _boom)
    monkeypatch.setattr(jobs, "populate_missed_month_messages", _boom)
    monkeypatch.setattr(jobs, "populate_missed_yesterday_messages", _boom)

    await jobs.populate_messages_job()
    await jobs.populate_one_month_job()
    await jobs.populate_missed_month_job()
    await jobs.populate_missed_yesterday_job()
    assert called["n"] == 0


def test_readiness_healthy_without_boc_token_or_booking_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINASLASER_API_TOKEN", raising=False)
    monkeypatch.delenv("EXTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("LINASLASER_API_BASE_URL", raising=False)
    monkeypatch.delenv("EXTERNAL_API_BASE_URL", raising=False)

    check = boc_booking_readiness()
    assert check["ok"] is True
    assert check["enabled"] is False
    assert check["token_required"] is False
    assert check["booking_ids_required"] is False
    assert check["jobs_allowed"] is False


def test_ready_endpoint_includes_boc_off_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv(BOC_BOOKING_ENABLED_ENV, raising=False)

        from fastapi.testclient import TestClient

        import modules.dashboard_api  # noqa: F401
        from modules.core import app

        client = TestClient(app)
        r = client.get("/api/ready")
        body = r.json()
        assert "boc_booking" in body["checks"]
        boc = body["checks"]["boc_booking"]
        assert boc["enabled"] is False
        assert boc["ok"] is True
        assert boc["booking_ids_required"] is False
        assert boc["token_required"] is False
        # BOC-off must not be the reason for 503
        if r.status_code == 503:
            assert body["checks"]["boc_booking"]["ok"] is True
    finally:
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.mark.asyncio
async def test_submit_booking_intent_blocked_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.booking.intent_pipeline import handle_submit_booking_intent

    create_spy = AsyncMock(side_effect=AssertionError("create_appointment must not run"))
    monkeypatch.setattr("services.api_integrations.create_appointment", create_spy)

    out = await handle_submit_booking_intent(
        user_id="u1",
        phone="96170000000",
        current_gender="female",
        user_input="book laser",
        function_args={"service_id": 1, "branch_id": 1, "date": "2026-08-20", "time": "10:00"},
    )
    assert out["error"] == BOC_BOOKING_DISABLED_CODE
    create_spy.assert_not_called()


def test_no_silent_fallback_payload() -> None:
    skipped = boc_job_skipped_response(operation="populate_messages_job")
    assert skipped["success"] is False
    assert skipped["job_started"] is False
    assert skipped["error"] == BOC_BOOKING_DISABLED_CODE
    # Explicit refusal — not an alternate booking backend name
    assert "requests" not in skipped["message"].lower()
    assert "monty" not in skipped["message"].lower()


def test_enabled_readiness_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BOC_BOOKING_ENABLED_ENV, "true")
    monkeypatch.delenv("LINASLASER_API_TOKEN", raising=False)
    monkeypatch.delenv("EXTERNAL_API_TOKEN", raising=False)
    monkeypatch.setenv("LINASLASER_API_BASE_URL", "https://example.com/agent/")
    check = boc_booking_readiness()
    assert check["enabled"] is True
    assert check["token_required"] is True
    assert check["booking_ids_required"] is True
    assert check["ok"] is False
