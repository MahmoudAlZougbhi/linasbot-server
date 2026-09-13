"""HA deploy wiring for Meta comment permission backfill gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def test_deploy_runs_backfill_after_alembic_before_readiness() -> None:
    source = _helper()
    verify_start = source[source.index("start_target_runtime() {") : source.index("activate_impl() {")]
    backfill_fn = source[
        source.index("run_target_comment_permission_backfill() {") : source.index("run_target_readiness_probe() {")
    ]
    assert "RELEASE_COMMENT_BACKFILL_REPO_PATH" in source
    assert "linasbot-ha-comment-backfill.service" in backfill_fn
    assert verify_start.index("run_target_alembic_migrate") < verify_start.index(
        "run_target_comment_permission_backfill"
    )
    assert verify_start.index("run_target_comment_permission_backfill") < verify_start.index(
        "run_target_readiness_probe"
    )


def test_backfill_block_exit_uses_fail_closed_die_message() -> None:
    source = _helper()
    backfill_fn = source[
        source.index("run_target_comment_permission_backfill() {") : source.index("run_target_readiness_probe() {")
    ]
    assert '[ "$rc" -eq 2 ]' in backfill_fn
    assert "comment permission backfill blocked: unknown active bindings remain" in backfill_fn


def test_activate_failure_triggers_automatic_rollback_path() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    automatic = orchestrate[orchestrate.index("rollback_transaction() {") : orchestrate.index("on_exit() {")]
    activate = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    assert 'start_target_runtime "$tx_dir"' in activate
    assert "rollback_transaction" in orchestrate
    assert "node_clear_maintenance" in automatic
    assert "rollback-complete" in automatic
    assert "ROLLBACK PARITY IS UNCERTAIN" in automatic


def test_ha_backfill_runner_returns_exit_code_2(monkeypatch) -> None:
    import scripts.ha.run_meta_comment_permission_backfill as runner

    sha = "a" * 40
    monkeypatch.setenv("LINAS_HA_VERIFY_RELEASE_SHA", sha)
    monkeypatch.setattr(runner, "REPO", ROOT)
    monkeypatch.setattr(runner, "BACKFILL", ROOT / "scripts/backfill_meta_comment_permission_verification.py")

    def _fake_run(cmd, **kwargs):
        if cmd[0:3] == ["git", "-C", str(ROOT)] and cmd[3] == "rev-parse" and cmd[4] == "HEAD":
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{sha}\n", stderr="")
        if cmd[0:3] == ["git", "-C", str(ROOT)] and cmd[3] == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, stdout="blobsha\n", stderr="")
        if cmd[0:3] == ["git", "-C", str(ROOT)] and cmd[3] == "hash-object":
            return subprocess.CompletedProcess(cmd, 0, stdout="blobsha\n", stderr="")
        return subprocess.CompletedProcess(cmd, 2, stdout='{"pending_unknown_active_after":1}\n', stderr="")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    assert runner.main() == 2
