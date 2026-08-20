"""Target-SHA platform readiness breaks the old tenant-binding deploy deadlock."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.responses import JSONResponse

from modules import dashboard_api_health
from scripts.ha.target_platform_readiness_preflight import (
    assert_platform_readiness_contract,
    evaluate_target_platform_ready,
    failing_platform_checks,
)
from services.meta_app_registry import MetaAppRegistry
from tests.test_production_readiness import _activate, _stub_platform_dependencies

pytest_plugins = ("tests.meta_app_registry_fixtures",)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _legacy_all_flags_ready(*, facebook_active: bool, instagram_active: bool, platform_ok: bool) -> bool:
    checks = {
        "encryption_key_configured": platform_ok,
        "app_a_configured": platform_ok,
        "linas_facebook_app_a_active": facebook_active,
        "linas_instagram_app_a_active": instagram_active,
        "active_indexes_exclusive": True,
        "active_credentials_valid": True,
        "app_b_not_active_on_linas": True,
        "registry_backend_ready": platform_ok,
    }
    return all(checks.values())


def test_pre_split_ready_gate_failed_closed_on_facebook_only() -> None:
    # Production-old get_meta_registry_readiness returned all(checks.values()),
    # so Instagram inactive made /api/ready 503 even when Facebook and platform
    # secrets were healthy.
    assert _legacy_all_flags_ready(facebook_active=True, instagram_active=True, platform_ok=True) is True
    assert _legacy_all_flags_ready(facebook_active=True, instagram_active=False, platform_ok=True) is False
    assert _legacy_all_flags_ready(facebook_active=False, instagram_active=True, platform_ok=True) is False


def test_facebook_only_old_ready_is_503_target_artifact_is_200(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    _activate(registry, "facebook")
    assert _legacy_all_flags_ready(facebook_active=True, instagram_active=False, platform_ok=True) is False
    _stub_platform_dependencies(monkeypatch, tmp_path)
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    report = evaluate_target_platform_ready(ROOT)
    assert report["ok"] is True
    assert report["status_code"] == 200
    assert report["lb_gate"] is False
    assert report["failing"] == {}
    assert "linas_instagram_app_a_active" not in report["meta_social_messaging"]


@pytest.mark.asyncio
async def test_target_http_ready_stays_200_when_instagram_is_inactive(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import json

    _stub_platform_dependencies(monkeypatch, tmp_path)
    _activate(registry, "facebook")
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    response = await dashboard_api_health.ready()
    assert isinstance(response, JSONResponse)
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["ok"] is True


def test_platform_contract_rejects_registry_that_lists_bindings(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    services = tmp_path / "services"
    modules.mkdir()
    services.mkdir()
    (modules / "dashboard_api_health.py").write_text("# platform health\n", encoding="utf-8")
    (services / "meta_app_registry.py").write_text(
        "META_PLATFORM_READINESS_KEYS = ('encryption_key_configured',)\n"
        "def get_meta_registry_readiness(registry=None):\n"
        "    bindings = registry.list_bindings(include_inactive=False)\n"
        "    return True, {}\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="tenant bindings"):
        assert_platform_readiness_contract(tmp_path)


def test_failing_platform_checks_omits_healthy_entries() -> None:
    assert failing_platform_checks(
        {
            "firestore": {"ok": True},
            "job_queue": {"ok": False, "error": "ConnectionError"},
            "meta_social_messaging": {"ok": True, "app_a_configured": True},
        }
    ) == {"job_queue": {"ok": False, "error": "ConnectionError"}}


def test_current_tree_matches_platform_readiness_contract() -> None:
    assert_platform_readiness_contract(ROOT)


def test_preflight_uses_target_evaluator_after_artifact_verification() -> None:
    source = HELPER.read_text(encoding="utf-8")
    preflight = source[source.index("node_preflight() {") : source.index("capture_service_state() {")]
    serving = source[source.index("node_assert_serving_contract() {") : source.index("node_assert_release_ready() {")]
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    target = preflight.index('assert_target_object "$target_sha" "$expected_helper_hash"')
    capability = preflight.index('assert_integration_capability_preflight "$target_sha"')
    gate = preflight.index('assert_target_platform_readiness_preflight "$target_sha"')
    assert target < capability < gate
    preflight_helper = source[
        source.index("assert_target_platform_readiness_preflight() {") : source.index("assert_health_while_drained() {")
    ]
    assert 'git -C "$REPO_DIR" archive --format=tar "$target_sha"' in preflight_helper
    assert "modules services utils handlers storage db config.py" in preflight_helper
    assert (
        'git -C "$REPO_DIR" archive --format=tar'
        in source[source.index("assert_target_platform_readiness_preflight() {") :]
    )
    assert (
        "list_bindings"
        not in source[
            source.index("assert_target_platform_readiness_preflight() {") : source.index(
                "assert_health_while_drained() {"
            )
        ]
    )
    assert "assert_ready" in preflight
    assert "assert_lb_ready" in preflight
    assert "assert_ready" in serving
    assert "assert_target_platform_readiness_preflight" not in serving
    assert "assert_target_platform_readiness_preflight" not in rollback
    assert 'update_deploy_journal "preflight-proven"' in source
    assert "assert_fresh_lb_ready_attestation" in preflight


def test_transition_helper_stays_under_500_lines() -> None:
    assert (
        len((ROOT / "scripts/ha/target_platform_readiness_preflight.py").read_text(encoding="utf-8").splitlines()) < 500
    )
    assert len((ROOT / "tests/test_ha_platform_readiness_transition.py").read_text(encoding="utf-8").splitlines()) < 500
