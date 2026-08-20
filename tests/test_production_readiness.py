"""Platform readiness is independent of tenant channel connection state."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse

from modules import dashboard_api_health
from scripts.ha.integration_capability_preflight import evaluate_deploy_preflight
from services.channel_health import evaluate_channel_health
from services.meta_app_registry import (
    APP_A_KEY,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    META_PLATFORM_READINESS_KEYS,
    MetaAppRegistry,
    get_meta_app_configs,
    get_meta_registry_readiness,
)
from tests.meta_app_registry_helpers import _credential

pytest_plugins = ("tests.meta_app_registry_fixtures",)

ROOT = Path(__file__).resolve().parents[1]


def _activate(registry: MetaAppRegistry, channel: str):
    app_a_id = get_meta_app_configs()[APP_A_KEY].app_id
    asset_id = LINAS_PAGE_ID if channel == "facebook" else LINAS_INSTAGRAM_ACCOUNT_ID
    return registry.activate_binding(
        tenant_id="linas",
        channel=channel,
        asset_id=asset_id,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner",
    )


def _stub_platform_dependencies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)
    monkeypatch.delenv("LINAS_MAINTENANCE_DRAIN_FILE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("WHATSAPP_DISABLED", "true")
    monkeypatch.setenv("META_SOCIAL_MESSAGING_ENABLED", "true")
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setattr(
        dashboard_api_health,
        "PERSISTENT_MAINTENANCE_DRAIN_FILE",
        str(tmp_path / "absent-maintenance"),
    )
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: object())
    settings = tmp_path / "settings"
    settings.mkdir()
    monkeypatch.setattr("storage.persistent_storage.SETTINGS_DIR", settings)
    monkeypatch.setattr("storage.persistent_storage.ensure_dirs", lambda: None)


async def _ready_payload(monkeypatch: pytest.MonkeyPatch, registry: MetaAppRegistry) -> tuple[int, dict]:
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    response = await dashboard_api_health.ready()
    assert isinstance(response, JSONResponse)
    return response.status_code, json.loads(response.body)


def test_facebook_only_keeps_platform_ready(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    _activate(registry, "facebook")
    ready, checks = get_meta_registry_readiness(registry)
    health = evaluate_channel_health(registry=registry)
    assert ready is True
    assert set(checks) == set(META_PLATFORM_READINESS_KEYS)
    assert all(checks[key] is True for key in META_PLATFORM_READINESS_KEYS)
    assert health["facebook"]["status"] == "PASS"
    assert health["instagram"]["status"] == "WARNING"
    assert health["instagram"]["reason"] == "no_active_binding"
    assert health["lb_gate"] is False


def test_instagram_only_keeps_platform_ready(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    _activate(registry, "instagram")
    ready, checks = get_meta_registry_readiness(registry)
    health = evaluate_channel_health(registry=registry)
    assert ready is True
    assert set(checks) == set(META_PLATFORM_READINESS_KEYS)
    assert all(checks[key] is True for key in META_PLATFORM_READINESS_KEYS)
    assert health["instagram"]["status"] == "PASS"
    assert health["facebook"]["status"] == "WARNING"


def test_no_meta_connections_keeps_platform_ready(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    ready, checks = get_meta_registry_readiness(registry)
    health = evaluate_channel_health(registry=registry)
    assert ready is True
    assert set(checks) == set(META_PLATFORM_READINESS_KEYS)
    assert all(checks[key] is True for key in META_PLATFORM_READINESS_KEYS)
    assert health["facebook"]["status"] == "WARNING"
    assert health["instagram"]["status"] == "WARNING"


def test_expired_instagram_token_fails_channel_health_only(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    app_a_id = get_meta_app_configs()[APP_A_KEY].app_id
    registry.activate_binding(
        tenant_id="linas",
        channel="instagram",
        asset_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=replace(_credential(app_a_id, LINAS_PAGE_ID), expires_at=1),
        actor_id="owner",
    )
    ready, checks = get_meta_registry_readiness(registry)
    health = evaluate_channel_health(registry=registry)
    assert ready is True
    assert "active_credentials_valid" not in checks
    assert all(checks[key] is True for key in META_PLATFORM_READINESS_KEYS)
    assert health["instagram"]["status"] == "FAIL"
    assert health["instagram"]["connected"] is True
    assert health["instagram"]["reason"] == "expired_token"


def test_facebook_disconnect_does_not_fail_platform(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    binding = _activate(registry, "facebook")
    registry.disconnect_binding_statuses(
        (binding.binding_id,),
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        actor_id="owner",
    )
    ready, checks = get_meta_registry_readiness(registry)
    health = evaluate_channel_health(registry=registry)
    assert ready is True
    assert "linas_facebook_app_a_active" not in checks
    assert all(checks[key] is True for key in META_PLATFORM_READINESS_KEYS)
    assert health["facebook"]["status"] == "WARNING"
    assert health["facebook"]["reason"] == "no_active_binding"


@pytest.mark.asyncio
async def test_ready_http_facebook_only_is_200(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _stub_platform_dependencies(monkeypatch, tmp_path)
    _activate(registry, "facebook")
    status, body = await _ready_payload(monkeypatch, registry)
    assert status == 200
    assert body["ok"] is True
    assert "linas_instagram_app_a_active" not in body["checks"]["meta_social_messaging"]
    assert "linas_facebook_app_a_active" not in body["checks"]["meta_social_messaging"]
    assert "active_credentials_valid" not in body["checks"]["meta_social_messaging"]


@pytest.mark.asyncio
async def test_ready_http_no_channels_is_200(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _stub_platform_dependencies(monkeypatch, tmp_path)
    status, body = await _ready_payload(monkeypatch, registry)
    assert status == 200
    assert body["ok"] is True
    assert body["role"] == "readiness"


@pytest.mark.asyncio
async def test_channel_health_http_is_never_an_lb_gate(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules import channel_health_api

    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    response = await channel_health_api.channel_health()
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["role"] == "channel_health"
    assert payload["lb_gate"] is False


def test_deploy_preflight_passes_without_connected_users() -> None:
    report = evaluate_deploy_preflight(
        source_root=ROOT,
        env_values={
            "META_CREDENTIAL_ENCRYPTION_KEY": "x" * 32,
            "META_APP_A_ID": "2963733803971681",
            "META_APP_A_SECRET": "app-secret",
            "META_APP_A_WEBHOOK_VERIFY_TOKEN": "verify",
            "META_REGISTRY_BACKEND": "file",
        },
    )
    assert report["ok"] is True
    assert report["blocking"] == []


def test_deploy_preflight_fails_when_connect_route_missing(tmp_path: Path) -> None:
    broken = tmp_path / "modules"
    broken.mkdir()
    (broken / "meta_connections_api.py").write_text("# oauth callback removed\n", encoding="utf-8")
    report = evaluate_deploy_preflight(source_root=tmp_path, check_env=False)
    assert report["ok"] is False
    assert any(item["reason"] == "connect_route_missing" for item in report["blocking"])


def test_deploy_preflight_source_never_reads_tenant_bindings() -> None:
    source = (ROOT / "scripts" / "ha" / "integration_capability_preflight.py").read_text(encoding="utf-8")
    assert "list_bindings" not in source
    assert "linas_facebook_app_a_active" not in source
    assert "linas_instagram_app_a_active" not in source


def test_ready_and_preflight_never_inspect_tenant_bindings() -> None:
    ready_source = inspect.getsource(get_meta_registry_readiness)
    health_source = (ROOT / "modules" / "dashboard_api_health.py").read_text(encoding="utf-8")
    preflight_source = (ROOT / "scripts" / "ha" / "integration_capability_preflight.py").read_text(encoding="utf-8")
    for source in (ready_source, health_source, preflight_source):
        assert "list_bindings" not in source
        assert "linas_facebook_app_a_active" not in source
        assert "linas_instagram_app_a_active" not in source
        assert "active_credentials_valid" not in source


def test_ha_lb_deploy_rollback_never_use_channel_health() -> None:
    for rel in (
        "scripts/ha/deploy_meta_release_ha.sh",
        "scripts/ha/release_verify_server.py",
        "scripts/ha/do_lb_ready_contract.py",
        "scripts/ha/manage_do_lb_ready_healthcheck.py",
        "scripts/ha/verify_meta_release_ha.sh",
        "scripts/ha/controlled_meta_failover.py",
        "scripts/ha/public_ready_lb_wait_contract.py",
    ):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "channel-health" not in source
        assert "channel_health" not in source
        assert "evaluate_channel_health" not in source


def test_new_readiness_modules_stay_under_500_lines() -> None:
    for rel in (
        "services/channel_health.py",
        "services/meta_app_registry.py",
        "modules/dashboard_api_health.py",
        "scripts/ha/integration_capability_preflight.py",
        "modules/channel_health_api.py",
        "tests/test_production_readiness.py",
    ):
        assert len((ROOT / rel).read_text(encoding="utf-8").splitlines()) < 500
