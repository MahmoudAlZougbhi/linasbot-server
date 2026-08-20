"""Target-SHA platform readiness breaks the old tenant-binding deploy deadlock."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse

from modules import dashboard_api_health
from scripts.ha.target_platform_readiness_preflight import (
    COMPACT_ARCHIVE_PATHS,
    assert_platform_readiness_contract,
    evaluate_target_platform_ready,
    failing_platform_checks,
    live_ready_is_platform_admissible,
    materialize_target_archive,
    reclaim_volatile_target_ready,
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
    assert 'mktemp -p "$META_HA_STATE_ROOT" linasbot-target-platform-ready.XXXXXXXX' in preflight_helper
    assert "--repo-dir" in preflight_helper
    assert '--state-root "$META_HA_STATE_ROOT"' in preflight_helper
    assert "mktemp -d -p /run linasbot-target-ready" not in preflight_helper
    assert "git archive --format=tar" not in preflight_helper
    evaluator = (ROOT / "scripts/ha/target_platform_readiness_preflight.py").read_text(encoding="utf-8")
    assert "COMPACT_ARCHIVE_PATHS" in evaluator
    assert COMPACT_ARCHIVE_PATHS == (
        "modules",
        "services",
        "utils",
        "handlers",
        "storage",
        "db",
        "config.py",
    )
    assert "reclaim_volatile_target_ready" in evaluator
    assert "shutil.rmtree" in evaluator
    assert 'Path("/var/lib/linasbot/meta-ha")' in evaluator
    assert 'Path("/run")' in evaluator
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
    assert "assert_serving_ready_for_sha" in serving
    assert "assert_ready" not in serving
    assert "assert_target_platform_readiness_preflight" not in serving
    assert "assert_target_platform_readiness_preflight" not in rollback
    assert 'update_deploy_journal "preflight-proven"' in source
    assert "assert_fresh_lb_ready_attestation" in preflight


def test_live_facebook_only_503_is_admissible_for_target_preflight() -> None:
    ok, failing = live_ready_is_platform_admissible(
        503,
        {
            "ok": False,
            "role": "readiness",
            "checks": {
                "firestore": {"ok": True},
                "meta_social_messaging": {
                    "ok": False,
                    "encryption_key_configured": True,
                    "app_a_configured": True,
                    "registry_backend_ready": True,
                    "linas_facebook_app_a_active": True,
                    "linas_instagram_app_a_active": False,
                },
            },
        },
    )
    assert ok is True
    assert set(failing) == {"meta_social_messaging"}


def test_live_firestore_503_is_not_admissible_for_target_preflight() -> None:
    ok, failing = live_ready_is_platform_admissible(
        503,
        {
            "ok": False,
            "role": "readiness",
            "checks": {
                "firestore": {"ok": False, "error": "ModuleNotFoundError"},
                "meta_social_messaging": {"ok": True},
            },
        },
    )
    assert ok is False
    assert "firestore" in failing


def test_reclaim_removes_leftover_target_ready_trees(tmp_path: Path) -> None:
    leftover = tmp_path / "linasbot-target-ready.abcdefgh"
    leftover.mkdir()
    (leftover / "modules").mkdir()
    (leftover / "modules" / "stale.py").write_text("stale\n", encoding="utf-8")
    script = tmp_path / "linasbot-target-platform-ready.py"
    script.write_text("# leftover\n", encoding="utf-8")
    other = tmp_path / "keep-me"
    other.mkdir()
    reclaimed = reclaim_volatile_target_ready(run_dir=tmp_path, require_root=False)
    assert leftover.exists() is False
    assert script.exists() is False
    assert other.exists() is True
    assert str(leftover) in reclaimed
    assert str(script) in reclaimed


def test_reclaim_refuses_symlink_leftovers(tmp_path: Path) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "linasbot-target-ready.symlink1"
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="symlink"):
        reclaim_volatile_target_ready(run_dir=tmp_path, require_root=False)


def test_compact_archive_stays_off_tmpfs_and_contains_platform_modules(tmp_path: Path) -> None:
    sha = subprocess.check_output(
        ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    destination = tmp_path / "archive"
    destination.mkdir()
    materialize_target_archive(ROOT, sha, destination)
    assert (destination / "modules" / "dashboard_api_health.py").is_file()
    assert (destination / "services" / "meta_app_registry.py").is_file()
    assert (destination / "tests").exists() is False


def test_workflow_reclaims_target_ready_tmpfs_before_helper_copy() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    reclaim = workflow.index("reclaimed volatile target-ready tmpfs")
    helper_root = workflow.index('HELPER_ROOT="$(sudo mktemp -d -p /run linasbot-ha-deploy.XXXXXXXX)"')
    assert reclaim < helper_root
    assert "shutil.rmtree" in workflow[workflow.index("volatile target-ready reclaim root is unsafe") : helper_root]


def _commit_ready_tree(tmp_path: Path, registry: str, health: str = "# health\n") -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "services").mkdir(parents=True)
    (repo / "modules").mkdir()
    (repo / "services" / "meta_app_registry.py").write_text(registry, encoding="utf-8")
    (repo / "modules" / "dashboard_api_health.py").write_text(health, encoding="utf-8")
    git = [
        "/usr/bin/git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "user.email=ha@linasbot.test",
        "-c",
        "user.name=HA",
        "-c",
        "commit.gpgsign=false",
    ]
    env = {
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run([*git, "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run([*git, "add", "services", "modules"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run([*git, "commit", "-m", "ready"], cwd=repo, check=True, capture_output=True, env=env)
    sha = subprocess.check_output(
        [*git, "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        env=env,
    ).strip()
    return repo, sha


def test_legacy_sha_has_tenant_ready_gates_platform_sha_does_not(tmp_path: Path) -> None:
    from scripts.ha.live_ready_admission import sha_has_tenant_ready_gates

    legacy_repo, legacy_sha = _commit_ready_tree(
        tmp_path / "legacy",
        "def get_meta_registry_readiness():\n    return False, {'linas_instagram_app_a_active': False}\n",
    )
    platform_repo, platform_sha = _commit_ready_tree(
        tmp_path / "platform",
        "META_PLATFORM_READINESS_KEYS = ('encryption_key_configured',)\n"
        "def get_meta_registry_readiness():\n"
        "    return True, {'encryption_key_configured': True}\n",
    )
    assert sha_has_tenant_ready_gates(legacy_repo, legacy_sha) is True
    assert sha_has_tenant_ready_gates(platform_repo, platform_sha) is False


def test_admit_live_ready_accepts_facebook_only_503_on_legacy_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ha import live_ready_admission

    repo, sha = _commit_ready_tree(
        tmp_path,
        "def get_meta_registry_readiness():\n"
        "    return False, {'linas_facebook_app_a_active': True, "
        "'linas_instagram_app_a_active': False}\n",
    )
    payload = {
        "ok": False,
        "role": "readiness",
        "checks": {
            "firestore": {"ok": True},
            "meta_social_messaging": {
                "ok": False,
                "encryption_key_configured": True,
                "app_a_configured": True,
                "registry_backend_ready": True,
                "linas_facebook_app_a_active": True,
                "linas_instagram_app_a_active": False,
            },
        },
    }
    monkeypatch.setattr(live_ready_admission, "fetch_live_ready", lambda url="": (503, payload))
    status, admitted = live_ready_admission.admit_live_ready_for_sha(repo, sha)
    assert status == 503
    assert admitted["ok"] is False


def test_admit_live_ready_refuses_firestore_503_on_legacy_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ha import live_ready_admission

    repo, sha = _commit_ready_tree(
        tmp_path,
        "def get_meta_registry_readiness():\n    return False, {'linas_instagram_app_a_active': False}\n",
    )
    payload = {
        "ok": False,
        "role": "readiness",
        "checks": {
            "firestore": {"ok": False, "error": "ModuleNotFoundError"},
            "meta_social_messaging": {"ok": True},
        },
    }
    monkeypatch.setattr(live_ready_admission, "fetch_live_ready", lambda url="": (503, payload))
    with pytest.raises(RuntimeError, match="platform-admissible"):
        live_ready_admission.admit_live_ready_for_sha(repo, sha)


def test_admit_live_ready_requires_200_on_platform_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ha import live_ready_admission

    repo, sha = _commit_ready_tree(
        tmp_path,
        "def get_meta_registry_readiness():\n    return True, {}\n",
    )
    monkeypatch.setattr(
        live_ready_admission,
        "fetch_live_ready",
        lambda url="": (503, {"ok": False, "role": "readiness", "checks": {}}),
    )
    with pytest.raises(RuntimeError, match="not healthy"):
        live_ready_admission.admit_live_ready_for_sha(repo, sha)


def test_helper_uses_sha_aware_serving_and_later_helper_rollback_phase() -> None:
    source = HELPER.read_text(encoding="utf-8")
    serving = source[source.index("node_assert_serving_contract() {") : source.index("node_assert_release_ready() {")]
    clear = source[source.index("node_clear_maintenance() {") : source.index("node_assert_release_drained() {")]
    later = source[source.index("assert_later_dispatch_helper() {") : source.index("assert_public_ready() {")]
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    orchestrate = source[source.index("orchestrate() {") :]
    assert "assert_serving_ready_for_sha" in serving
    assert "probe_serving_ready_for_sha" in clear
    assert "grep -q '\"ok\"[[:space:]]*:[[:space:]]*true'" not in clear
    assert "automatic-rollback-both-nodes-drained" in later
    assert "linas_instagram_app_a_active" in later
    assert 'assert_public_ready_for_sha "$previous_sha"' in orchestrate
    assert 'assert_public_ready_for_sha "$previous_sha"' in recover


def test_transition_helper_stays_under_500_lines() -> None:
    assert (
        len((ROOT / "scripts/ha/target_platform_readiness_preflight.py").read_text(encoding="utf-8").splitlines()) < 500
    )
    assert len((ROOT / "scripts/ha/live_ready_admission.py").read_text(encoding="utf-8").splitlines()) < 500
    assert len((ROOT / "tests/test_ha_platform_readiness_transition.py").read_text(encoding="utf-8").splitlines()) < 500
