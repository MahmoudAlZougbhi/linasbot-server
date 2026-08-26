"""Fail-closed contract for the fixed WhatsApp App Review test bind."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from scripts.ha import production_mutation_guard as guard

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wa-app-review-bind.yml"
SCRIPT = ROOT / "scripts" / "prod_wa_app_review_bind.sh"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"


def test_workflow_is_main_only_protected_serialized_and_release_pinned() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)
    job = parsed["jobs"]["run"]

    assert parsed["concurrency"] == {
        "group": "meta-social-cutover",
        "cancel-in-progress": False,
    }
    assert job["environment"] == "meta-social-cutover"
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" in source
    assert PINNED_SSH in source
    assert "production_mutation_guard.py" in source
    assert '--expected-sha "$EXPECTED_RELEASE_SHA"' in source
    assert "scripts/prod_wa_app_review_bind.sh" in source
    assert "DRY_RUN_WA_APP_REVIEW_BIND" in source
    assert "BIND_LINAS_WABA_1409769574350248_PHONE_1322897994230591" in source
    assert "case " not in source
    assert ";;" not in source
    assert 'if [ "$PHASE" = DRY_RUN ]' in source
    assert 'elif [ "$PHASE" = BIND ]' in source
    assert '[ "$CONFIRM" = DRY_RUN_WA_APP_REVIEW_BIND ]' in source
    assert '[ "$CONFIRM" = BIND_LINAS_WABA_1409769574350248_PHONE_1322897994230591 ]' in source


def test_workflow_has_no_asset_selectors_token_transport_or_source_transport() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)
    inputs = parsed[True]["workflow_dispatch"]["inputs"]

    assert set(inputs) == {"PHASE", "CONFIRM"}
    assert inputs["PHASE"] == {
        "description": "Validate the fixed Meta asset or bind it to tenant linas",
        "required": True,
        "type": "choice",
        "options": ["DRY_RUN", "BIND"],
    }
    assert inputs["CONFIRM"]["required"] is True
    assert inputs["CONFIRM"]["type"] == "string"
    assert "META_WHATSAPP_APP_REVIEW_BIND_TOKEN" not in source
    assert "Authorization:" not in source
    assert "Bearer " not in source
    assert "curl " not in source
    assert "actions/checkout" not in source
    assert "git fetch" not in source
    assert "git show" not in source
    assert "git checkout" not in source
    assert "appleboy/scp-action" not in source
    assert "secrets.SSH_HOST" in source
    assert "secrets.SSH_USER" in source
    assert "secrets.SSH_PRIVATE_KEY" in source
    assert "secrets.META_" not in source


def test_script_is_guarded_fixed_asset_dry_run_first_and_redacted() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "linas_require_production_mutation_guard" in source
    assert 'TENANT_ID = "linas"' in source
    assert 'WABA_ID = "1409769574350248"' in source
    assert 'PHONE_NUMBER_ID = "1322897994230591"' in source
    assert 'EXPECTED_APP_ID = "2963733803971681"' in source
    assert 'EXPECTED_LAST4 = "4285"' in source
    assert "allowed != {WABA_ID}" in source
    assert source.count("access_token=None") == 2
    assert source.index("dry_run=True") < source.index("dry_run=False")
    assert "public_availability_must_remain_false" in source
    assert "recording_runtime_flags_not_enabled" in source
    assert "history_sync_must_remain_false" in source
    assert "pilot_entitlement_gate_must_remain_enabled" in source
    assert "dry_run_existing_credential_mismatch" in source
    assert "bind_raw_active_count_mismatch" in source
    assert "bind_raw_connection_id_mismatch" in source
    assert "bind_raw_webhook_fields_mismatch" in source
    assert "bind_raw_history_sync_mismatch" in source
    assert "bind_credential_mismatch" in source
    assert "bind_pilot_missing" in source
    assert "DRY_RUN_OK" in source
    assert "BIND_COMPLETE_OK" in source
    assert "COMPLETE_OK" in source
    assert "print(token" not in source
    assert "print(payload" not in source
    assert "print(public" not in source
    assert "traceback" not in source.lower()
    assert "except Exception as exc:" in source
    assert "BIND_ATTEMPTED = True" in source
    assert "BIND_COMMITTED_POSTCHECK_FAILED" in source
    assert "BIND_OUTCOME_UNCERTAIN" in source


def test_script_orders_guard_cluster_proofs_mutation_and_final_success() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    guard_pos = source.index("linas_require_production_mutation_guard")
    first_verify = source.index("verify_meta_release_ha.sh")
    python_start = source.index("<<'PY'")
    dry_run = source.index("dry_run=True")
    dry_run_barrier = source.index('if sys.argv[1] == "dry-run":\n        return')
    bind = source.index("dry_run=False")
    second_verify = source.rindex("verify_meta_release_ha.sh")
    complete = source.index('echo "[wa-app-review-bind] COMPLETE_OK mode=$MODE"')

    assert source.count("verify_meta_release_ha.sh") == 2
    assert guard_pos < first_verify < python_start < dry_run < dry_run_barrier < bind < second_verify < complete


def test_inline_python_compiles() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    marker = "<<'PY'\n"
    body = source.split(marker, 1)[1].split("\nPY\n", 1)[0]
    compile(body, str(SCRIPT), "exec")


def test_script_is_allowlisted_as_shared_database_mutation_not_env_transaction() -> None:
    entrypoint = "scripts/prod_wa_app_review_bind.sh"
    assert entrypoint in guard.ALLOWED_SCRIPTS
    assert entrypoint not in guard.TWO_NODE_ENV_TRANSACTION_REQUIRED


def test_script_has_valid_shell_syntax() -> None:
    completed = subprocess.run(
        ["/bin/bash", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
