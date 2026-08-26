"""Fail-closed contracts for the temporary WhatsApp App Review token writer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/meta-whatsapp-app-review-token-apply.yml"
SCRIPT = ROOT / "scripts/prod_apply_meta_whatsapp_app_review_token.sh"


def test_workflow_is_protected_exact_release_two_node_transaction() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.safe_load(source)
    job = payload["jobs"]["apply"]

    assert payload["concurrency"] == {"group": "meta-social-cutover", "cancel-in-progress": False}
    assert job["environment"] == "meta-social-cutover"
    assert "github.ref == 'refs/heads/main'" in str(job["if"])
    assert "INSTALL_META_WHATSAPP_APP_REVIEW_TOKEN" in source
    assert "REMOVE_META_WHATSAPP_APP_REVIEW_TOKEN" in source
    assert "secrets.META_WHATSAPP_APP_REVIEW_BIND_TOKEN" in source
    assert 'META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS: "1409769574350248"' in source
    assert "exec 9>/run/lock/linasbot-meta-live.lock" in source
    assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in source
    assert "cluster-release-only" in source
    assert "--register-prestage-backup" in source
    assert "--local-prestage-backup" in source
    assert "--finalize" in source
    assert source.count("verify_meta_release_ha.sh") >= 2
    assert "COMPLETE_OK action=" in source
    assert "node02" not in source.replace("nodes=2", "")


def test_stage_writer_never_prints_or_generates_the_token() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'META_HA_STAGE_ONLY:-}" != "true"' in source
    assert "--verify-stage-authority" in source
    assert "from scripts.ha.meta_env_file import atomic_update_env" in source
    assert "atomic_update_env(ENV_PATH" in source
    assert "hmac.compare_digest" in source
    assert "secrets.token" not in source
    assert "print(updates" not in source
    assert "print(os.environ" not in source
    assert "static_environment_valid=true" in source


def test_stage_writer_rejects_direct_invocation() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"]},
    )
    assert result.returncode != 0
    assert "META_HA_STAGE_ONLY=true is required" in result.stderr
