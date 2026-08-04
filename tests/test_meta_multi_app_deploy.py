"""Static safety gates for the canonical two-app production workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_multi_app_apply_script_is_valid_and_fails_back_to_legacy() -> None:
    script = ROOT / "scripts/prod_apply_meta_multi_app.sh"
    subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True, text=True)
    source = script.read_text(encoding="utf-8")
    assert "set -x" not in source
    assert 'echo "$META_' not in source
    assert "META_MULTI_APP_REGISTRY_ENABLED=false" in source
    assert "registry readiness failed; restoring legacy router" in source
    assert "python3 -m scripts.seed_meta_app_a_registry" in source
    assert "sensitive_credentials_in_logs=false" in source
    assert "META_APP_B_LINAS_CUTOVER_APPROVED" in source


def test_multi_app_workflow_uses_only_canonical_secret_names_and_no_auto_approval() -> None:
    source = (ROOT / ".github/workflows/meta-multi-app-secrets-apply.yml").read_text(encoding="utf-8")
    for secret_name in (
        "META_APP_ID",
        "META_APP_SECRET",
        "META_PAGE_ACCESS_TOKEN",
        "META_WEBHOOK_VERIFY_TOKEN",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "META_APP_B_ID",
        "META_APP_B_SECRET",
        "META_APP_B_WEBHOOK_VERIFY_TOKEN",
        "META_APP_B_LOGIN_CONFIG_ID",
    ):
        assert f"secrets.{secret_name}" in source
    assert 'META_APP_B_ADVANCED_ACCESS_APPROVED: "false"' in source
    assert "META_APP_B_LINAS_CUTOVER_APPROVED" not in source
    assert "sudo -E bash /opt/linasbot/scripts/prod_apply_meta_multi_app.sh" in source


def test_registry_seed_script_never_renders_credentials() -> None:
    source = (ROOT / "scripts/seed_meta_app_a_registry.py").read_text(encoding="utf-8")
    assert "print(page_token" not in source
    assert "print(app.app_secret" not in source
    assert 'print(f"{page_token' not in source
    assert 'print(f"{app.app_secret' not in source
    assert "app_a_id_match=true" in source
    assert "instagram_account_id_match=true" in source
