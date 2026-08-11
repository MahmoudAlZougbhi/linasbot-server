"""Deploy script checks for App A Facebook-only login configuration apply."""

from __future__ import annotations

from pathlib import Path


def test_prod_apply_meta_app_a_login_config_script_exists() -> None:
    script = Path("scripts/prod_apply_meta_app_a_login_config.sh")
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID" in text
    assert "1057282070324984" in text  # refused for Facebook Connect
    assert "seed_meta_app_a_registry" not in text
    assert "systemctl restart linasbot" in text
    workflow = Path(".github/workflows/meta-app-a-login-config-apply.yml")
    assert workflow.is_file()
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID" in workflow_text
