"""Wave 0 / membership-v1: plan economics, platform_owner role."""

from __future__ import annotations

import pytest
from fastapi.responses import JSONResponse

from services.plan_economics import PLAN_PRICES_USD, build_economics_report, recommend_allowance
from services.role_assignment import RoleAssignmentError, assert_assignable_role


def test_plan_prices_fixed() -> None:
    assert PLAN_PRICES_USD == {
        "lite": 9.99,
        "starter": 25.0,
        "growth": 59.0,
        "pro": 109.0,
        "max": 259.0,
    }


def test_economics_report_margin_ok() -> None:
    report = build_economics_report()
    assert report["report_version"] == "membership-v1"
    assert len(report["plans"]) == 5
    for plan in report["plans"]:
        assert plan["flag_negative_economics"] is False
        assert len(plan["scenarios"]) == 3


def test_recommend_allowance_starter_has_no_creative() -> None:
    a = recommend_allowance("starter")
    assert a.included_images == 0
    assert a.included_videos == 0
    assert a.included_credits == 17500


def test_platform_owner_not_assignable_via_tenant() -> None:
    with pytest.raises(RoleAssignmentError):
        assert_assignable_role("platform_owner", created_by="user-123")
    with pytest.raises(RoleAssignmentError):
        assert_assignable_role("platform_owner", created_by="cli-provision")
    assert assert_assignable_role("platform_owner", created_by="cli-provision-platform-owner") == "platform_owner"
    assert assert_assignable_role("admin", created_by="anyone") == "admin"


def test_settings_ai_limits_post_gone() -> None:
    import asyncio

    from modules import settings_api

    result = asyncio.run(settings_api.update_ai_limits_removed())
    assert isinstance(result, JSONResponse)
    assert result.status_code == 410
