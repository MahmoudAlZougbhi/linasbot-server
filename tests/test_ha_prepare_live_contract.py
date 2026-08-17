"""Official live HA contract prep installs the rekey guard and quarantines leftovers."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def test_prepare_live_ha_contract_is_invoked_before_orchestrate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    helper = _helper()
    prepare = helper[
        helper.index("prepare_live_ha_contract_cluster() {") : helper.index("install_release_bundle_cluster() {")
    ]
    assert "prepare-live-ha-contract-cluster" in workflow
    assert workflow.index("prepare-live-ha-contract-cluster") < workflow.index("orchestrate-confirmed")
    assert '"$HELPER_PATH" prepare-live-ha-contract-cluster' in workflow
    assert "live HA contract prepared on node02 then node01" in prepare
    assert "credential rekey static guard is missing" in helper


def test_rekey_guard_install_uses_git_blob_excl_not_gnu_dd() -> None:
    helper = _helper()
    body = helper[
        helper.index("install_rekey_static_guard_from_target() {") : helper.index(
            "quarantine_untracked_owner_blockers() {"
        )
    ]
    assert '["git", "-C", repo, "cat-file", "blob", git_object]' in body
    assert "os.O_EXCL" in body
    assert "mktemp -d -p /run linasbot-rekey-guard." in body
    assert "oflag=excl" not in body
    assert "95-linasbot-credential-rekey-guard.conf" in body
    assert "systemctl daemon-reload" in body


def test_untracked_quarantine_moves_owner_blockers_without_rm() -> None:
    helper = _helper()
    body = helper[
        helper.index("quarantine_untracked_owner_blockers() {") : helper.index("prepare_live_ha_contract() {")
    ]
    assert "mv --" in body
    assert "untracked-quarantine" in body
    assert "post-quarantine" in body
    assert all(not line.lstrip().startswith("rm ") for line in body.splitlines())
