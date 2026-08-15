"""Repository-level policy for production application release entrypoints."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
DEPLOY_WORKFLOW = WORKFLOW_DIR / "deploy.yml"
SECURITY_WORKFLOW = WORKFLOW_DIR / "security-checks.yml"
HA_HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
BREAK_GLASS = ROOT / "scripts" / "ha" / "release_break_glass.sh"
TWO_NODE_POLICY = ROOT / "docs" / "release" / "TWO_NODE_RELEASE_POLICY.md"

ALL_WORKFLOWS = frozenset(
    {
        "cm-linas-content-audit.yml",
        "cm-production-cutover.yml",
        "copilot-v2-flags-apply.yml",
        "dashboard-auth-secret-apply.yml",
        "deploy.yml",
        "ha-infra-ssh-bootstrap.yml",
        "instagram-login-secrets-apply.yml",
        "meta-app-a-login-config-apply.yml",
        "meta-app-a-scope-audit.yml",
        "meta-app-webhooks-reconcile.yml",
        "meta-comment-runtime-probe.yml",
        "meta-comment-webhooks-reconcile.yml",
        "meta-inbound-payload-retention.yml",
        "meta-multi-app-secrets-apply.yml",
        "meta-page-subscription-subscribe.yml",
        "meta-social-atomic-cutover.yml",
        "meta-social-rollback-restore.yml",
        "meta-social-rollback-snapshot.yml",
        "meta-social-secrets-apply.yml",
        "meta-social-token-validate.yml",
        "meta-webhook-nginx-setup.yml",
        "model-routing-policy-apply.yml",
        "openai-api-key-apply.yml",
        "prod-preflight-readonly.yml",
        "provision-python-runtime-ha.yml",
        "quality-gates.yml",
        "resend-secrets-apply.yml",
        "security-checks.yml",
        "subscription-exempt-probe.yml",
        "wa-app-review-connection-source-migrate.yml",
        "wa-cloud-webhook-readonly-probe.yml",
        "whatsapp-cloud-phase1-apply.yml",
    }
)

# Every workflow with a production SSH/SCP execution surface must be reviewed
# into this closed inventory. A new remote workflow cannot silently become an
# alternate release lane.
REMOTE_WORKFLOWS = frozenset(
    {
        "cm-linas-content-audit.yml",
        "cm-production-cutover.yml",
        "deploy.yml",
        "instagram-login-secrets-apply.yml",
        "meta-app-a-login-config-apply.yml",
        "meta-app-a-scope-audit.yml",
        "meta-app-webhooks-reconcile.yml",
        "meta-comment-runtime-probe.yml",
        "meta-comment-webhooks-reconcile.yml",
        "meta-inbound-payload-retention.yml",
        "meta-multi-app-secrets-apply.yml",
        "meta-page-subscription-subscribe.yml",
        "meta-social-rollback-snapshot.yml",
        "meta-social-secrets-apply.yml",
        "meta-social-token-validate.yml",
        "meta-webhook-nginx-setup.yml",
        "prod-preflight-readonly.yml",
        "provision-python-runtime-ha.yml",
        "subscription-exempt-probe.yml",
        "wa-app-review-connection-source-migrate.yml",
        "wa-cloud-webhook-readonly-probe.yml",
    }
)
REMOTE_ACCESS = re.compile(
    r"appleboy/(?:ssh|scp)-action|^\s*(?:/usr/bin/)?(?:ssh|scp|rsync)(?:\s|\\)",
    flags=re.MULTILINE,
)
DIRECT_RELEASE_MARKERS = (
    "deploy_meta_release_ha.sh",
    "/opt/linasbot/deploy.sh",
    "install-release-bundle-cluster",
    "install-lb-attestation-cluster",
    "orchestrate-confirmed",
    "orchestrate-reconcile",
    "commit-target-confirmed",
    "recover-confirmed",
    "retry-reconcile-confirmed",
)
GIT_HEAD_MUTATION = re.compile(
    r"\bgit\b[^\n]{0,240}\b(?:fetch|pull|reset|restore|checkout|switch|clean|read-tree|merge|rebase|cherry-pick)\b"
)
FORBIDDEN_REMOTE_RELEASE = (
    re.compile(r"\bdeploy_meta_release_ha\.sh\b"),
    re.compile(r"(?:^|[\s\"'])/?opt/linasbot/deploy\.sh(?:$|[\s\"'])"),
    GIT_HEAD_MUTATION,
    re.compile(r"\bsystemctl\s+(?:start|restart)\s+linasbot(?:\.service)?\b"),
    re.compile(r"\brsync\b[^\n]{0,240}/opt/linasbot(?:/|\s|$)"),
)
DEPLOY_INPUTS = {
    "BOOTSTRAP_PLAN_SHA256",
    "COMMIT_CONFIRM",
    "DEPLOY_CONFIRM",
    "DEPLOY_OPERATION",
    "LB_ATTESTATION_BASE64",
    "LB_ATTESTATION_SHA256",
    "LB_INSTALL_CONFIRM",
    "LB_OWNER_CONFIRM",
    "LB_READY_PROJECTION_SHA256",
    "NODE01_BASELINE_SHA",
    "NODE02_BASELINE_SHA",
    "PROTECTION_CONFIRM",
    "QUALITY_GATES_RUN_ID",
    "RECONCILE_CONFIRM",
    "RECOVERY_CONFIRM",
    "RECOVERY_JOURNAL_SHA256",
    "RELEASE_ARTIFACT_API_SHA256",
    "RELEASE_ARTIFACT_ID",
    "RELEASE_INSTALL_CONFIRM",
    "RELEASE_MANIFEST_SHA256",
    "RELEASE_RUN_ATTEMPT",
    "RELEASE_TARGET_TREE_SHA",
    "RETRY_RECONCILE_CONFIRM",
    "TARGET_SHA",
}
DEPLOY_TOMBSTONE = """#!/bin/bash
# The standalone production deploy path is intentionally retired.
# Production releases require the protected, exact-artifact, two-node workflow.

set -euo pipefail

printf '%s\\n' \\
  'Standalone deploy.sh is disabled.' \\
  'Use the manual protected .github/workflows/deploy.yml transaction.' \\
  'Single-node release break-glass is disabled in product code.' >&2
exit 2
"""
BREAK_GLASS_TOMBSTONE = """#!/bin/bash
# Deliberately non-operational marker for the production release break-glass path.
# A repository checkout must never be sufficient to obtain single-node deploy authority.

set -euo pipefail

printf '%s\\n' \\
  'BLOCKED: product code contains no single-node production release bypass.' \\
  'Break-glass access is disabled by default and must be granted live, out of band, with both nodes drained.' \\
  'See docs/release/TWO_NODE_RELEASE_POLICY.md.' >&2
exit 2
"""


def _workflows() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _minimal_env() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    }


def test_official_workflow_inventory_is_closed() -> None:
    assert {workflow.name for workflow in _workflows()} == ALL_WORKFLOWS


def test_security_check_context_is_unique_for_branch_protection() -> None:
    source = SECURITY_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(
        r"^  secret-scan:\n    name: security-secret-scan$",
        source,
        flags=re.MULTILINE,
    )
    assert "name: security-secret-scan" not in (WORKFLOW_DIR / "quality-gates.yml").read_text(encoding="utf-8")


def test_remote_production_workflow_inventory_is_closed() -> None:
    found = {workflow.name for workflow in _workflows() if REMOTE_ACCESS.search(workflow.read_text(encoding="utf-8"))}
    assert found == REMOTE_WORKFLOWS


def test_only_deploy_workflow_contains_application_release_protocol() -> None:
    found: dict[str, list[str]] = {}
    for workflow in _workflows():
        source = workflow.read_text(encoding="utf-8")
        markers = [marker for marker in DIRECT_RELEASE_MARKERS if marker in source]
        if markers:
            found[workflow.name] = markers
    assert set(found) == {"deploy.yml", "quality-gates.yml"}
    assert "deploy_meta_release_ha.sh" in found["deploy.yml"]
    assert "orchestrate-confirmed" in found["deploy.yml"]
    # Quality Gates may name the protected helper only to test/package it; it
    # has no production remote-access surface.
    assert not REMOTE_ACCESS.search((WORKFLOW_DIR / "quality-gates.yml").read_text(encoding="utf-8"))


def test_every_non_release_workflow_is_free_of_application_release_mutations() -> None:
    for workflow in _workflows():
        if workflow.name == "deploy.yml":
            continue
        source = workflow.read_text(encoding="utf-8")
        patterns = FORBIDDEN_REMOTE_RELEASE
        if workflow.name == "quality-gates.yml":
            # Quality Gates packages and statically checks the helper but has no
            # production transport, host, or deploy credentials.
            patterns = FORBIDDEN_REMOTE_RELEASE[1:]
        for pattern in patterns:
            assert pattern.search(source) is None, (workflow.name, pattern.pattern)


def test_non_release_remote_workflows_cannot_add_source_transport() -> None:
    allowed_scp = {"deploy.yml", "provision-python-runtime-ha.yml"}
    for name in REMOTE_WORKFLOWS - {"deploy.yml"}:
        source = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        if name not in allowed_scp:
            assert "appleboy/scp-action" not in source, name
            assert "actions/checkout" not in source, name


def test_deploy_workflow_exposes_no_single_node_or_host_selector() -> None:
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    input_region = source[source.index("    inputs:") : source.index("concurrency:")]
    input_names = set(re.findall(r"^      ([A-Z][A-Z0-9_]+):$", input_region, flags=re.MULTILINE))
    assert input_names == DEPLOY_INPUTS
    assert "host: ${{ inputs." not in source
    assert '"$HELPER_PATH" install-release-bundle-cluster' in source
    assert '"$HELPER_PATH" install-lb-attestation-cluster' in source
    assert '"$HELPER_PATH" orchestrate-confirmed' in source
    assert '"$HELPER_PATH" orchestrate-reconcile' in source
    assert re.search(r'"\$HELPER_PATH"\s+install-release-bundle(?:\s|$)', source) is None
    assert re.search(r'"\$HELPER_PATH"\s+install-lb-attestation(?:\s|$)', source) is None


def test_only_ha_helper_can_change_the_deployed_git_head() -> None:
    candidates = [ROOT / "deploy.sh"]
    candidates.extend(
        path for path in (ROOT / "scripts").rglob("*") if path.is_file() and path.suffix in {".py", ".sh", ".bash"}
    )
    mutators = {
        path.relative_to(ROOT).as_posix()
        for path in candidates
        if GIT_HEAD_MUTATION.search(path.read_text(encoding="utf-8"))
    }
    assert mutators == {"scripts/ha/deploy_meta_release_ha.sh"}


def test_deploy_named_product_entrypoint_inventory_is_closed() -> None:
    found = {
        path.relative_to(ROOT).as_posix()
        for path in [ROOT / "deploy.sh", *(ROOT / "scripts").rglob("*")]
        if path.is_file() and "deploy" in path.name.lower() and path.suffix in {".py", ".sh", ".bash"}
    }
    assert found == {"deploy.sh", "scripts/ha/deploy_meta_release_ha.sh"}


def test_standalone_and_internal_single_node_release_entrypoints_fail_closed() -> None:
    assert (ROOT / "deploy.sh").read_text(encoding="utf-8") == DEPLOY_TOMBSTONE
    direct = subprocess.run(
        ["/bin/bash", str(ROOT / "deploy.sh")],
        cwd=ROOT,
        env=_minimal_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert direct.returncode == 2
    assert "Standalone deploy.sh is disabled." in direct.stderr
    assert "Single-node release break-glass is disabled" in direct.stderr

    for command in ("install-release-bundle", "install-lb-attestation", "node"):
        result = subprocess.run(
            ["/bin/bash", str(HA_HELPER), command],
            cwd=ROOT,
            env=_minimal_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, command
        assert "single-node release phases are internal-only" in result.stderr, command


def test_internal_node_protocol_requires_coordinator_marker() -> None:
    source = HA_HELPER.read_text(encoding="utf-8")
    assert "not a security boundary against root" in source
    assert "INTERNAL_NODE_DISPATCH_CONFIRM=LINAS_HA_COORDINATOR_INTERNAL_NODE_RPC_V1" in source
    assert '-s -- node \\\n    "$INTERNAL_NODE_DISPATCH_CONFIRM" "$@"' in source
    dispatch = source[source.index('case "${1:-}" in') :]
    for command in ("install-release-bundle", "install-lb-attestation"):
        branch = dispatch[dispatch.index(f"  {command})") :]
        branch = branch[: branch.index("    ;;")]
        assert 'require_internal_node_dispatch "${2:-}"' in branch
    node_branch = dispatch[dispatch.index("  node)") :]
    node_branch = node_branch[: node_branch.index("    ;;")]
    assert 'require_internal_node_dispatch "${1:-}"' in node_branch


def test_break_glass_is_explicit_and_non_operational_by_default() -> None:
    source = BREAK_GLASS.read_text(encoding="utf-8")
    assert source == BREAK_GLASS_TOMBSTONE
    result = subprocess.run(
        ["/bin/bash", str(BREAK_GLASS)],
        cwd=ROOT,
        env=_minimal_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "product code contains no single-node production release bypass" in result.stderr
    for forbidden in ("ssh ", "scp ", "git ", "systemctl ", "sudo ", "/opt/linasbot"):
        assert forbidden not in source

    policy = (ROOT / "docs" / "release" / "TWO_NODE_RELEASE_POLICY.md").read_text(encoding="utf-8")
    for required in (
        "can_admins_bypass=false",
        "Disable routine root SSH",
        "short-lived",
        "both nodes drained",
        "unrestricted host `root` can bypass",
        "Pin and verify both SSH host identities",
    ):
        assert required in policy


def test_instagram_schema_rollout_keeps_stage_a_as_the_rollback_runtime() -> None:
    policy = TWO_NODE_POLICY.read_text(encoding="utf-8")
    for required in (
        "`20260820_meta_ig_single` rollout is intentionally split",
        "Stage A contains",
        "does not contain that migration",
        "exact baseline on both nodes",
        "both nodes drained before its first target",
        "does not run an automatic Alembic",
        "Stage A is the reviewed forward-compatible runtime",
    ):
        assert required in policy
    assert "alembic downgrade" not in HA_HELPER.read_text(encoding="utf-8").lower()


def test_readonly_preflight_no_longer_advertises_retired_single_node_rollback() -> None:
    source = (ROOT / "scripts" / "prod_preflight_readonly.sh").read_text(encoding="utf-8")
    assert "git reset --hard" not in source
    assert "/opt/linasbot/deploy.sh" not in source
    assert "protected .github/workflows/deploy.yml recover_exact transaction" in source


def test_active_operator_docs_do_not_advertise_direct_per_node_release() -> None:
    paths = [ROOT / "docs" / "DEPLOY_AUTH_MIGRATION_CHECKLIST.md"]
    paths.extend((ROOT / "docs" / "release").glob("*.md"))
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "git reset --hard" not in source, path
        assert "sudo bash /opt/linasbot/deploy.sh" not in source, path
        assert "EMERGENCY_DEPLOY_CONFIRM" not in source, path
