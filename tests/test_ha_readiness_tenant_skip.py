"""HA /api/ready must not require a founder tenant slug after CLEAN FINISH G."""

from __future__ import annotations

import inspect

from modules.dashboard_api_health import tenant_runtime_config_readiness_check


def test_tenant_runtime_config_readiness_skips_file_migrate(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.tenant_runtime.tenant_runtime_config_backend.tenant_runtime_config_postgres_required",
        lambda: True,
    )

    def _ping() -> dict[str, bool]:
        return {"reachable": True}

    monkeypatch.setattr("db.session.ping_whatsapp_db", _ping)
    monkeypatch.delenv("LINASBOT_TENANT_ID", raising=False)
    monkeypatch.delenv("DEFAULT_TENANT_ID", raising=False)
    result = tenant_runtime_config_readiness_check()
    assert result["ok"] is True
    assert result["per_tenant_file_migrate"] == "skipped"
    assert "tenant_id required" not in str(result)
    src = inspect.getsource(tenant_runtime_config_readiness_check)
    assert "tenant env for HA maintenance only — not a single-tenant founder product" in src


def test_tenant_runtime_config_readiness_fails_when_postgres_down(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.tenant_runtime.tenant_runtime_config_backend.tenant_runtime_config_postgres_required",
        lambda: True,
    )
    monkeypatch.setattr("db.session.ping_whatsapp_db", lambda: {"reachable": False})
    result = tenant_runtime_config_readiness_check()
    assert result["ok"] is False
    assert result["db_reachable"] is False
