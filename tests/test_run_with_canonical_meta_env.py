from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha import run_with_canonical_meta_env as runner


def test_canonical_meta_values_replace_all_ambient_meta_settings(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ENVIRONMENT=production\nMETA_APP_ID=2963733803971681\nMETA_APP_SECRET=canonical-secret\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    result = runner._build_environment(
        env_path=env_path,
        ambient={
            "PATH": "/usr/bin",
            "META_APP_SECRET": "stale-github-secret",
            "META_STALE_ALIAS": "must-disappear",
        },
        passthrough=(),
    )

    assert result["META_APP_SECRET"] == "canonical-secret"
    assert result["META_APP_ID"] == "2963733803971681"
    assert "META_STALE_ALIAS" not in result
    assert result["PATH"] == "/usr/bin"


def test_only_allowlisted_boolean_controls_can_override_canonical_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "META_APP_ID=2963733803971681\nMETA_RECONCILE_PAGE_SUBSCRIPTION=false\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    result = runner._build_environment(
        env_path=env_path,
        ambient={"META_RECONCILE_PAGE_SUBSCRIPTION": "TRUE"},
        passthrough=("META_RECONCILE_PAGE_SUBSCRIPTION",),
    )

    assert result["META_RECONCILE_PAGE_SUBSCRIPTION"] == "true"

    with pytest.raises(RuntimeError, match="not allowlisted"):
        runner._build_environment(
            env_path=env_path,
            ambient={"META_APP_SECRET": "injected"},
            passthrough=("META_APP_SECRET",),
        )
    with pytest.raises(RuntimeError, match="value is invalid"):
        runner._build_environment(
            env_path=env_path,
            ambient={"META_RECONCILE_PAGE_SUBSCRIPTION": "$(unsafe)"},
            passthrough=("META_RECONCILE_PAGE_SUBSCRIPTION",),
        )
