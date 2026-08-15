"""Deploy script checks for App A Facebook-only login configuration apply."""

from __future__ import annotations

from pathlib import Path


def test_prod_apply_meta_app_a_login_config_script_exists() -> None:
    script = Path("scripts/prod_apply_meta_app_a_login_config.sh")
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID" in text
    assert "META_APP_A_LOGIN_CONFIG_ID" in text  # stripped as obsolete
    assert 'remove_keys = frozenset({"META_APP_A_LOGIN_CONFIG_ID"})' in text
    assert "seed_meta_app_a_registry" not in text
    assert "META_HA_STAGE_ONLY=true is required" in text
    assert "atomic_update_env" in text
    assert "systemctl" not in text
    workflow = Path(".github/workflows/meta-app-a-login-config-apply.yml")
    assert workflow.is_file()
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID" in workflow_text
    assert 'META_HA_STAGE_ONLY: "true"' in workflow_text
    assert "--maintenance-active" in workflow_text
