"""Static release-pinning contracts for privileged Meta workflows."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
PINNED_SSH_ACTION = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
RETIRED_META_WORKFLOWS = frozenset(
    {
        "meta-social-atomic-cutover.yml",
        "meta-social-rollback-restore.yml",
    }
)


def _meta_workflows() -> list[Path]:
    workflows = sorted(
        {
            *WORKFLOW_DIR.glob("meta-*.yml"),
            WORKFLOW_DIR / "instagram-login-secrets-apply.yml",
        }
    )
    assert workflows
    assert all(path.is_file() for path in workflows)
    return [path for path in workflows if path.name not in RETIRED_META_WORKFLOWS]


def test_every_meta_workflow_is_pinned_to_the_exact_deployed_release() -> None:
    for workflow in _meta_workflows():
        source = workflow.read_text(encoding="utf-8")
        assert "group: meta-social-cutover" in source, workflow.name
        assert "cancel-in-progress: false" in source, workflow.name
        assert "environment: meta-social-cutover" in source, workflow.name
        assert "exec 9>/run/lock/linasbot-meta-live.lock" in source, workflow.name
        assert source.index("flock -x 9") < source.index("verify_meta_release_ha.sh"), workflow.name
        if workflow.name == "meta-app-a-login-config-maintenance-recover.yml":
            assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" not in source
            assert "a2ba8d63265504ded18b6d4bd70219628c4d8533" in source
            assert source.count("verify_meta_release_ha.sh") == 1
            continue
        assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" in source, workflow.name
        assert 'DEPLOYED_RELEASE_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"' in source, workflow.name
        assert '[ "$DEPLOYED_RELEASE_SHA" != "$EXPECTED_RELEASE_SHA" ]' in source, workflow.name
        assert 'git -C "$REPO_DIR" diff --quiet "$DEPLOYED_RELEASE_SHA" --' in source, workflow.name
        assert 'git -C "$REPO_DIR" diff --cached --quiet "$DEPLOYED_RELEASE_SHA" --' in source, workflow.name
        assert source.count("verify_meta_release_ha.sh") >= 2, workflow.name


def test_privileged_meta_ssh_action_is_pinned_to_an_immutable_commit() -> None:
    for workflow in _meta_workflows():
        source = workflow.read_text(encoding="utf-8")
        assert PINNED_SSH_ACTION in source, workflow.name
        assert "appleboy/ssh-action@v" not in source, workflow.name
    deploy = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert "appleboy/" not in deploy
    assert "/usr/bin/ssh" in deploy and "/usr/bin/scp" in deploy


def test_retired_app_mutation_workflows_expose_no_ssh_or_secrets() -> None:
    for name in RETIRED_META_WORKFLOWS:
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        assert source.startswith("name: RETIRED -")
        assert "appleboy/ssh-action" not in source
        assert "secrets." not in source
        assert "exit 1" in source
        assert "environment: meta-social-cutover" in source


def test_meta_workflows_never_replace_deployed_scripts_from_a_moving_ref() -> None:
    forbidden = (
        "origin/main",
        "git fetch",
        "git show",
        "git checkout",
        "scp-action",
        "linaslaserbot-2.7.22",
    )
    for workflow in _meta_workflows():
        source = workflow.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in source, f"{workflow.name}: {fragment}"


def test_graph_operations_run_from_the_verified_production_tree() -> None:
    for name in (
        "meta-app-webhooks-reconcile.yml",
        "meta-comment-webhooks-reconcile.yml",
        "meta-social-token-validate.yml",
    ):
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        assert "actions/checkout" not in source
        assert "actions/setup-python" not in source
        assert "${{ github.workspace }}" not in source
        assert "run_with_canonical_meta_env.py" in source
        assert "secrets.META_" not in source


def test_deploy_uses_the_authorized_sha_and_requires_both_nodes() -> None:
    source = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh").read_text(encoding="utf-8")
    assert "group: meta-social-cutover" in source
    assert "cancel-in-progress: false" in source
    assert "environment: meta-social-cutover" in source
    assert "workflow_dispatch:" in source
    assert "workflow_run:" not in source
    assert "github.event.workflow_run" not in source
    assert "TARGET_SHA: ${{ inputs.TARGET_SHA }}" in source
    assert "artifact-ids: ${{ inputs.RELEASE_ARTIFACT_ID }}" in source
    assert "materialize_recovery_helper" in source
    assert '"$HELPER_PATH" orchestrate-confirmed' in source
    assert '"$HELPER_PATH" orchestrate-reconcile' in source
    assert '"$HELPER_PATH" commit-target-confirmed' in source
    assert '"$HELPER_PATH" recover-confirmed' in source
    assert '"$HELPER_PATH" retry-reconcile-confirmed' in source
    assert 'git -C "$REPO_DIR" reset --hard "$target_sha"' in helper
    assert 'git -C "$REPO_DIR" reset --hard "$previous_sha"' in helper
    assert "git reset --hard origin/main" not in source
    assert "Peer deploy failed" not in source
    assert "Peer deploy skipped" not in source
    assert "StrictHostKeyChecking=yes" in helper
    assert "verify_meta_release_ha.sh" in helper
    assert "node01" in helper and "node02" in helper
    node_dispatch = helper[helper.index("node_dispatch() {") : helper.index("reject_self_peer() {")]
    orchestrate = helper[helper.index("orchestrate() {") :]
    assert node_dispatch.index("acquire_meta_live_lock") < node_dispatch.index('case "$phase" in')
    assert orchestrate.index("acquire_meta_live_lock") < orchestrate.index(
        'remote_node "$peer_host" activate "$target_sha"'
    )
    assert "flock -x 9" in helper


def test_manual_reconciliation_cannot_bypass_quality_gates_or_bootstrap_proof() -> None:
    source = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    for contract in (
        "DEPLOY_OPERATION",
        "reconcile_exact",
        "QUALITY_GATES_RUN_ID",
        "NODE01_BASELINE_SHA",
        "NODE02_BASELINE_SHA",
        "BOOTSTRAP_PLAN_SHA256",
        "I_UNDERSTAND_RECONCILING_DISTINCT_HA_BASELINES",
        '"repos/$GITHUB_REPOSITORY/actions/runs/$QUALITY_GATES_RUN_ID"',
        '[ "$RUN_HEAD_SHA" = "$TARGET_SHA" ]',
        '[ "$RUN_HEAD_BRANCH" = main ]',
        '[ "$RUN_CONCLUSION" = success ]',
        "RUN_WORKFLOW_ID",
        "EXPECTED_QG_WORKFLOW_ID",
        "actions/workflows/quality-gates.yml",
        '[ "$RUN_WORKFLOW_ID" = "$EXPECTED_QG_WORKFLOW_ID" ]',
        '[ "$RUN_WORKFLOW_PATH" = .github/workflows/quality-gates.yml ]',
        '[ "$RUN_EVENT" = push ]',
        '[ "$TARGET_SHA" = "$DISPATCH_SHA" ]',
        "environment: meta-social-cutover",
        "META_HA_PROTECTED_ENVIRONMENT_APPROVED",
        "environments/meta-social-cutover",
        'select(.type == "required_reviewers")',
        "PREVENT_SELF_REVIEW",
        "I_CONFIRMED_META_SOCIAL_CUTOVER_HAS_REQUIRED_REVIEWERS",
        "DEPLOY_${TARGET_SHA}_LB_${LB_PREFIX}_WITH_HA_PREFLIGHT_BACKUPS_AND_ROLLBACK",
        "commit_exact",
        "COMMIT_CONFIRM",
        "recover_exact",
        "retry_reconcile_exact",
        "RECOVERY_JOURNAL_SHA256",
        "RECOVERY_CONFIRM",
        "RETRY_RECONCILE_CONFIRM",
    ):
        assert contract in source
    assert "EMERGENCY_DEPLOY_CONFIRM" not in source
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "workflow_run:" not in source
    assert source.index('if [ "$DEPLOY_OPERATION" = steady ]') < source.index(
        'elif [ "$DEPLOY_OPERATION" = reconcile_exact ]'
    )
    steady_gate = source[
        source.index('if [ "$DEPLOY_OPERATION" = steady ]') : source.index(
            'elif [ "$DEPLOY_OPERATION" = reconcile_exact ]'
        )
    ]
    assert '[[ "$BOOTSTRAP_PLAN_SHA256" =~ ^[0-9a-f]{64}$ ]]' in steady_gate
    assert '[ -z "$RECONCILE_CONFIRM$RECOVERY_JOURNAL_SHA256" ]' in steady_gate
    steady_call = source[
        source.index('"$HELPER_PATH" orchestrate-confirmed') : source.index(
            'elif [ "$DEPLOY_OPERATION" = reconcile_exact ]', source.index('"$HELPER_PATH" orchestrate-confirmed')
        )
    ]
    assert ('"$NODE02_BASELINE_SHA" \\\n                "$BOOTSTRAP_PLAN_SHA256" "$DEPLOY_CONFIRM"') in steady_call


def test_same_name_alternate_workflow_cannot_authorize_deployment() -> None:
    source = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    # Display names are intentionally not authority. The immutable repository
    # workflow ID, canonical workflow path, run identity, and target SHA are.
    assert "RUN_NAME" not in source
    assert '[ "$RUN_WORKFLOW_ID" = "$EXPECTED_QG_WORKFLOW_ID" ]' in source
    assert '[ "$RUN_WORKFLOW_PATH" = .github/workflows/quality-gates.yml ]' in source
    assert '[ "$RUN_HEAD_SHA" = "$TARGET_SHA" ]' in source


def test_ha_verifier_proves_live_api_and_worker_processes() -> None:
    source = (ROOT / "scripts" / "ha" / "verify_meta_release_ha.sh").read_text(encoding="utf-8")
    for queue in ("high_priority", "interactive", "background", "expensive"):
        assert queue in source
    for contract in (
        "WorkingDirectory",
        "ExecStart",
        "EnvironmentFiles",
        "MainPID",
        "/proc/$main_pid/environ",
        'Path("/proc") / pid',
        'proc / "cwd"',
        'proc / "cmdline"',
        'proc / "exe"',
        "scripts/run_queue_worker.py",
        "--queue",
        "/api/ready",
        "/api/queue/ready",
        "linas_ai_bot.service",
        "legacy port 8000 listener",
        "deploy/nginx-linasaibot.conf",
        "deploy/nginx-privacy-log.conf",
        "dotenv_values",
        "StrictHostKeyChecking=yes",
        "untracked runtime source exists",
        "legacy nested runtime still exists",
        "cluster Meta environment mismatch",
        "HA peer is unavailable or resolves to this node",
        "META_DELETION_NODE_ID",
        "META_DELETION_REQUIRED_NODES",
        'required != {"node01", "node02"}',
        "META_REGISTRY_BACKEND",
        'registry_backend != "postgres"',
        "operator_gate_allows_separation",
        "COLLISION_EXIT",
    ):
        assert contract in source
    assert ("META_APP_" + "REGISTRY_BACKEND") not in source


def test_meta_environment_mutations_sync_the_peer_then_require_parity() -> None:
    for name in (
        "instagram-login-secrets-apply.yml",
        "meta-app-a-login-config-apply.yml",
        "meta-multi-app-secrets-apply.yml",
        "meta-social-secrets-apply.yml",
        "meta-webhook-nginx-setup.yml",
    ):
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        preflight = source.index("cluster-release-only")
        stage_only = source.index('META_HA_STAGE_ONLY: "true"')
        maintenance = source.index("/var/lib/linasbot/meta-ha")
        recovery = source.index("--recover-only")
        registration = source.index("--register-prestage-backup")
        backup = source.index('ENV_BACKUP="$META_HA_STATE_ROOT/env.before"')
        sync = source.index("--local-prestage-backup")
        finalize = source.index("--finalize", sync)
        final_proof = source.rindex("verify_meta_release_ha.sh")
        complete = source.index("TRANSACTION_COMPLETE=true")
        assert (
            stage_only
            < maintenance
            < recovery
            < preflight
            < registration
            < backup
            < sync
            < finalize
            < final_proof
            < complete
        ), name
        assert "--maintenance-active" in source, name
        assert "--register-prestage-backup" in source, name
        assert "PERSISTENT_MAINTENANCE_FILE" in source, name
        assert "install -d -m 0700 -o root -g root" in source, name
        assert "exact pre-stage backup retained" in source, name
        assert "HA maintenance retained after uncertain transaction" in source, name
        assert "StrictHostKeyChecking=yes" in source, name


def test_release_only_preflight_enables_recovery_but_mutations_end_with_strict_proof() -> None:
    verifier = (ROOT / "scripts" / "ha" / "verify_meta_release_ha.sh").read_text(encoding="utf-8")
    assert 'if [ "$verify_runtime_state" = "1" ]; then\n    verify_local_readiness' in verifier
    assert 'if [ "$verify_meta_environment" != "1" ]; then' in verifier
    assert 'VERIFY_MODE" = "cluster-release-only"' in verifier
    assert "operator_gate_allows_separation" in verifier
    assert "verify_mode = sys.argv[3]" in verifier
    for name in (
        "instagram-login-secrets-apply.yml",
        "meta-app-a-login-config-apply.yml",
        "meta-multi-app-secrets-apply.yml",
        "meta-social-secrets-apply.yml",
        "meta-webhook-nginx-setup.yml",
    ):
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        recovery = source.index("--recover-only")
        release_only = source.index("cluster-release-only")
        activation = source.index("--local-prestage-backup")
        finalize = source.index("--finalize", activation)
        strict = source.rindex('verify_meta_release_ha.sh" "$EXPECTED_RELEASE_SHA"')
        complete = source.index("TRANSACTION_COMPLETE=true")
        assert recovery < release_only < activation < finalize < strict < complete, name


def test_meta_apply_scripts_are_static_stage_only_writers() -> None:
    scripts = (
        "prod_apply_instagram_login_secrets.sh",
        "prod_apply_meta_app_a_login_config.sh",
        "prod_apply_meta_multi_app.sh",
        "prod_apply_meta_social_secrets.sh",
        "prod_set_meta_verify_token.sh",
    )
    forbidden_runtime_commands = (
        "systemctl restart",
        "systemctl reload",
        "nginx -t",
        "nginx -T",
        "urllib.request",
        "journalctl",
        "curl -",
    )
    for name in scripts:
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert 'META_HA_STAGE_ONLY:-}" != "true"' in source, name
        assert "from scripts.ha.meta_env_file import atomic_update_env" in source, name
        assert "atomic_update_env(ENV_PATH" in source, name
        assert "static_environment_valid=true" in source, name
        for command in forbidden_runtime_commands:
            assert command not in source, f"{name}: {command}"


def test_meta_apply_scripts_reject_direct_non_transactional_invocation() -> None:
    for name in (
        "prod_apply_instagram_login_secrets.sh",
        "prod_apply_meta_app_a_login_config.sh",
        "prod_apply_meta_multi_app.sh",
        "prod_apply_meta_social_secrets.sh",
        "prod_set_meta_verify_token.sh",
    ):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / name)],
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": os.environ["PATH"]},
        )
        assert result.returncode != 0, name
        assert "META_HA_STAGE_ONLY=true is required" in result.stderr, name


def test_public_callback_probes_run_only_after_ha_sync_and_strict_proof() -> None:
    for name in (
        "instagram-login-secrets-apply.yml",
        "meta-multi-app-secrets-apply.yml",
        "meta-social-secrets-apply.yml",
        "meta-webhook-nginx-setup.yml",
    ):
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        sync = source.index("sync_meta_env_to_peer.py")
        final_proof = source.rindex("verify_meta_release_ha.sh")
        public_probe = source.index("https://www.linasaibot.com/webhook/", final_proof)
        assert sync < final_proof < public_probe, name


def test_verify_token_apply_does_not_mutate_node_local_nginx() -> None:
    workflow = (WORKFLOW_DIR / "meta-webhook-nginx-setup.yml").read_text(encoding="utf-8")
    apply_script = (ROOT / "scripts" / "prod_set_meta_verify_token.sh").read_text(encoding="utf-8")
    for source in (workflow, apply_script):
        assert "systemctl reload nginx" not in source
        assert "sed -i" not in source
        assert "cp -a" not in source
    assert "Nginx is deployed from the" in workflow


def test_production_meta_ops_never_select_the_legacy_nested_runtime() -> None:
    paths = [
        ROOT / "deploy.sh",
        ROOT / "scripts" / "prod_apply_instagram_login_secrets.sh",
        ROOT / "scripts" / "prod_apply_meta_app_a_login_config.sh",
        ROOT / "scripts" / "prod_apply_meta_multi_app.sh",
        ROOT / "scripts" / "prod_apply_meta_social_secrets.sh",
        ROOT / "scripts" / "prod_restore_meta_social_rollback.sh",
        ROOT / "scripts" / "prod_set_meta_verify_token.sh",
        ROOT / "scripts" / "prod_snapshot_meta_social_rollback.sh",
        *list(_meta_workflows()),
    ]
    for path in paths:
        assert "linaslaserbot-2.7.22" not in path.read_text(encoding="utf-8"), path.name


def test_app_webhook_reconcile_names_dm_and_comments() -> None:
    source = (WORKFLOW_DIR / "meta-app-webhooks-reconcile.yml").read_text(encoding="utf-8")
    assert "RECONCILE_META_SOCIAL_WEBHOOKS" in source
    assert "RECONCILE_META_DM_WEBHOOKS" not in source
    assert "DM + comment" in source


def test_direct_instagram_approval_apply_is_fail_closed_and_explicit() -> None:
    source = (WORKFLOW_DIR / "instagram-login-secrets-apply.yml").read_text(encoding="utf-8")
    apply_script = (ROOT / "scripts" / "prod_apply_instagram_login_secrets.sh").read_text(encoding="utf-8")
    assert 'default: "false"' in source
    assert "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED: ${{ inputs.advanced_access_approved }}" in source
    assert "CONFIRM_DIRECT_IG_META_APPROVAL" in source
    assert "false|true) ;;" in source
    assert "${{ inputs.APPROVAL_CONFIRM }}" in source
    assert "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED:-false" in apply_script
    assert 'ADVANCED_ACCESS_KEY = "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED"' in apply_script
    assert "false|true) ;;" in apply_script
    assert "CONFIRM_DIRECT_IG_META_APPROVAL" in apply_script
    assert "secrets.token_urlsafe" not in apply_script
    assert ".linasbot-instagram-login-verify-token-once" not in apply_script
