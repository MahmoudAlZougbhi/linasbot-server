"""Pre-mutation HA drain must measure cluster env from the imported target."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


def test_pre_mutation_process_env_uses_imported_target_helper() -> None:
    source = HELPER.read_text(encoding="utf-8")
    capture = source[
        source.index("assert_service_state_capture_is_pre_mutation() {") : source.index("disable_runtime_autostart() {")
    ]
    assert 'helper_source_sha="$(target_sha_from_tx "$tx_dir")"' in capture
    assert "current_head" not in capture
    assert (
        'assert_active_runtime_process_env_contract "$helper_source_sha" "$helper_source_sha" "$node_id"'
    ) in capture
    assert 'assert_service_state_capture_is_pre_mutation "$tx_dir"' in source
    assert "assert_service_state_capture_is_pre_mutation\n" not in source


def test_orchestrate_exit_trap_survives_destroyed_locals() -> None:
    source = HELPER.read_text(encoding="utf-8")
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    assert "HA_ORCHESTRATE_TX_STARTED=1" in orchestrate
    assert "HA_ORCHESTRATE_TX_SUCCEEDED=1" in orchestrate
    assert '"${HA_ORCHESTRATE_TX_STARTED:-0}"' in orchestrate
    assert "EXIT traps run outside orchestrate locals" in orchestrate
    assert 'if [ -z "${tx_dir:-}" ]' in orchestrate


def test_pre_mutation_recovery_may_run_a_later_helper_blob() -> None:
    source = HELPER.read_text(encoding="utf-8")
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    installer = source[
        source.index("install_lb_ready_attestation() {") : source.index("assert_lb_observation_strictly_newer() {")
    ]
    collision = source[
        source.index("assert_lb_attestation_install_collision_contract() {") : source.index(
            "install_lb_ready_attestation() {"
        )
    ]
    later_helper_phases = "preflight-proven|peer-mark-started|recovery-lb-attested|recovery-started"
    assert later_helper_phases in recover
    assert later_helper_phases in installer
    assert "later exact blob than the open pre-mutation journal" in recover
    assert "print-deploy-journal-identity)" in source
    assert "print_deploy_journal_identity() {" in source
    assert '[ "$operation" = recover ]' in installer
    assert '[ "$expected_node_id" = node01 ]' in installer
    assert "LB installer is a later exact blob than the open pre-mutation journal" in installer
    assert "LB attestation installer is not the exact authorized target helper" in installer
    assert 'if [ "$(configured_node_id)" = node01 ]; then' in collision
    assert "node02 deploy journal differs from the owner-confirmed snapshot" in collision
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source


def test_deploy_workflow_exposes_journal_identity_and_dispatch_helper_recover() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "- recovery_status" in source
    assert "print-deploy-journal-identity" in source
    assert "INSTALL_STATUS_LB_" in source
    assert "RECOVER_DISPATCH_HELPER=1" in source
    assert (
        "(inputs.DEPLOY_OPERATION == 'recover_exact' || inputs.DEPLOY_OPERATION == 'recovery_status') && github.sha"
        in source
    )
    assert '[ "$DEPLOY_OPERATION" = recover_exact ] || [ "$DEPLOY_OPERATION" = recovery_status ]' in source
    assert "TRANSFER_FILES=(transfer/deploy_meta_release_ha.sh)" in source
    assert "TRANSFER_FILES=()" not in source
    assert '[ "$ARTIFACT_NAME" = "linasbot-release-$DISPATCH_SHA" ]' in source
    assert '[ "$RUN_HEAD_SHA" = "$TARGET_SHA" ]' in source
    assert "materialize_recovery_helper" in source
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "--skip" not in source
