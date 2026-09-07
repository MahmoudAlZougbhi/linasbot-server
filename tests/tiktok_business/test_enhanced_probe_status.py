"""A/L: capability probe cache, no identity HTTP without advertiser token, status UX."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.tiktok_business.capabilities import ENHANCED_LABEL, user_message_for
from services.tiktok_business.capability_probe import probe_enhanced_capabilities
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.status import tiktok_integration_row
from tests.tiktok_business.conftest import seed_connection, seed_enhanced_binding


@pytest.mark.asyncio
async def test_a_no_advertiser_token_skips_identity_and_bc_http(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    hits: list[str] = []

    async def _forbidden(**_k):
        hits.append("called")
        raise AssertionError("Marketing API must not be called without an advertiser token")

    monkeypatch.setattr("services.tiktok_business.capability_probe.advertiser_get", _forbidden)
    monkeypatch.setattr("services.tiktok_business.capability_probe.bc_get", _forbidden)
    monkeypatch.setattr("services.tiktok_business.capability_probe.identity_get", _forbidden)
    repo = TikTokEnhancedRepository(tt_db)
    out = await probe_enhanced_capabilities(
        repo=repo,
        tenant_id="linas",
        connection_id=connection.id,
        username="linas_tt",
        display_name="Linas TT",
        granted_scopes=list(connection.granted_scopes or []),
        force=True,
    )
    assert hits == []
    assert out["reason_code"] == "authorization_required"
    assert out["status"] == "authorization_required"


@pytest.mark.asyncio
async def test_l_waiting_for_permission_then_active(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    seed_enhanced_binding(
        tt_db,
        connection,
        status="waiting_for_permission",
        reason_code="permission_not_approved",
        advertiser_token="ads",
        capabilities={"identity_query": False},
    )
    binding = TikTokEnhancedRepository(tt_db).get_binding(tenant_id="linas", connection_id=connection.id)
    assert binding is not None
    binding.probe_cooldown_until = datetime.now(UTC) + timedelta(hours=3)
    tt_db.commit()

    async def _forbidden(**_k):
        raise AssertionError("cooldown must skip Marketing API")

    monkeypatch.setattr("services.tiktok_business.capability_probe.advertiser_get", _forbidden)
    cached = await probe_enhanced_capabilities(
        repo=TikTokEnhancedRepository(tt_db),
        tenant_id="linas",
        connection_id=connection.id,
        username="linas_tt",
        display_name="Linas TT",
        granted_scopes=list(connection.granted_scopes or []),
        force=False,
    )
    assert cached["cached"] is True
    assert cached["status"] == "waiting_for_permission"

    async def _advertisers(**_k):
        return {"advertisers": [{"advertiser_id": "adv-1", "advertiser_name": "Linas"}]}

    async def _bc(**_k):
        return {"business_centers": []}

    async def _identities(**_k):
        return {
            "identities": [
                {
                    "identity_id": "idn-1",
                    "identity_type": "TT_USER",
                    "display_name": "linas_tt",
                    "username": "linas_tt",
                    "identity_authorized_bc_id": "",
                }
            ]
        }

    monkeypatch.setattr("services.tiktok_business.capability_probe.advertiser_get", _advertisers)
    monkeypatch.setattr("services.tiktok_business.capability_probe.bc_get", _bc)
    monkeypatch.setattr("services.tiktok_business.capability_probe.identity_get", _identities)
    live = await probe_enhanced_capabilities(
        repo=TikTokEnhancedRepository(tt_db),
        tenant_id="linas",
        connection_id=connection.id,
        username="linas_tt",
        display_name="Linas TT",
        granted_scopes=list(connection.granted_scopes or []),
        force=True,
    )
    assert live["status"] == "active"
    assert live["identity_id"] == "idn-1"
    assert live["capabilities"]["identity_query"] is True
    assert live["capabilities"]["identity_video_query"] is True


@pytest.mark.asyncio
async def test_permission_denied_classified_and_cached(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    seed_enhanced_binding(tt_db, connection, advertiser_token="ads")

    async def _denied(**_k):
        raise TikTokApiError("No permission", tiktok_code=40001, request_id="r1")

    monkeypatch.setattr("services.tiktok_business.capability_probe.advertiser_get", _denied)
    out = await probe_enhanced_capabilities(
        repo=TikTokEnhancedRepository(tt_db),
        tenant_id="linas",
        connection_id=connection.id,
        username="linas_tt",
        display_name="Linas TT",
        granted_scopes=list(connection.granted_scopes or []),
        force=True,
    )
    assert out["status"] == "waiting_for_permission"
    assert out["reason_code"] == "permission_not_approved"
    binding = TikTokEnhancedRepository(tt_db).get_binding(tenant_id="linas", connection_id=connection.id)
    assert binding is not None
    assert binding.probe_cooldown_until is not None


def test_status_row_has_enhanced_video_context(tt_db) -> None:
    seed_connection(tt_db)
    row = tiktok_integration_row("linas")
    assert row["post_context"]["level"] == "basic"
    enhanced = row["enhanced_video_context"]
    assert enhanced["label"] == ENHANCED_LABEL
    assert enhanced["status"] == "authorization_required"
    assert enhanced["user_message"] == user_message_for("authorization_required")
    assert enhanced["can_authorize"] is True
