from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse

from modules import dashboard_api_health
from services.scale import readiness_roles


@pytest.mark.asyncio
async def test_root_owned_maintenance_marker_fails_readiness_before_dependency_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "maintenance"
    marker.write_text("meta-ha-maintenance\n", encoding="utf-8")
    monkeypatch.setenv("LINAS_MAINTENANCE_DRAIN_FILE", str(marker))
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)

    response = await dashboard_api_health.ready()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    payload = json.loads(response.body)
    assert payload == {
        "ok": False,
        "role": "readiness",
        "checks": {"maintenance": {"ok": False}},
    }


@pytest.mark.asyncio
async def test_persistent_marker_keeps_readiness_failed_after_run_marker_is_lost_on_reboot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    volatile = tmp_path / "run" / "linasbot-maintenance"
    persistent = tmp_path / "var" / "lib" / "linasbot" / "meta-ha" / "maintenance"
    persistent.parent.mkdir(parents=True)
    persistent.write_text("meta-ha-maintenance\n", encoding="utf-8")
    persistent.chmod(0o600)
    monkeypatch.setenv("LINAS_MAINTENANCE_DRAIN_FILE", str(volatile))
    monkeypatch.setattr(
        dashboard_api_health,
        "PERSISTENT_MAINTENANCE_DRAIN_FILE",
        str(persistent),
    )
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)

    response = await dashboard_api_health.ready()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert json.loads(response.body)["checks"] == {"maintenance": {"ok": False}}
    assert not volatile.exists()


@pytest.mark.asyncio
async def test_internal_ha_probe_runs_dependency_path_but_public_ready_stays_drained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "maintenance"
    marker.write_text("meta-ha-maintenance\n", encoding="utf-8")
    marker.chmod(0o600)
    monkeypatch.setenv("LINAS_MAINTENANCE_DRAIN_FILE", str(marker))
    monkeypatch.setattr(dashboard_api_health, "PERSISTENT_MAINTENANCE_DRAIN_FILE", str(marker))
    monkeypatch.setenv("LINAS_HA_VERIFY_ONLY", "true")
    monkeypatch.setenv("LINAS_SERVICE_ROLE", "verification-test")
    calls: list[str] = []

    def dependency_probe(role: str) -> dict[str, object]:
        calls.append(role)
        return {"ok": True, "role": "readiness", "checks": {"dependency": {"ok": True}}}

    monkeypatch.setattr(readiness_roles, "readiness_for_role", dependency_probe)

    public_response = await dashboard_api_health.ready()
    internal_response = await dashboard_api_health.readiness_for_ha_verification()

    assert public_response.status_code == 503
    assert internal_response.status_code == 200
    assert calls == ["verification-test"]


@pytest.mark.asyncio
async def test_internal_ha_probe_fails_when_real_dependency_path_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "maintenance"
    marker.write_text("meta-ha-maintenance\n", encoding="utf-8")
    marker.chmod(0o600)
    monkeypatch.setenv("LINAS_MAINTENANCE_DRAIN_FILE", str(marker))
    monkeypatch.setattr(dashboard_api_health, "PERSISTENT_MAINTENANCE_DRAIN_FILE", str(marker))
    monkeypatch.setenv("LINAS_HA_VERIFY_ONLY", "true")
    monkeypatch.setenv("LINAS_SERVICE_ROLE", "verification-test")
    monkeypatch.setattr(
        readiness_roles,
        "readiness_for_role",
        lambda _role: {"ok": False, "role": "readiness", "checks": {"dependency": {"ok": False}}},
    )

    response = await dashboard_api_health.readiness_for_ha_verification()

    assert response.status_code == 503
    assert json.loads(response.body)["ok"] is False
