"""Instagram vs Facebook Meta secret separation: fail closed, never print values."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_instagram_login_config import instagram_login_config_status
from services.meta_surface_secret_separation import (
    COLLISION_EXIT,
    CONFIG_COLLISION_KEY,
    SIGNING_COLLISION,
    VERIFY_COLLISION,
    env_file_values,
    evaluate_meta_surface_secret_separation,
    require_separated_meta_surface_secrets,
    require_separated_meta_surface_secrets_for_update,
)

ROOT = Path(__file__).resolve().parents[1]
FB_SIGNING = "facebook-signing-secret-tests"
IG_SIGNING = "instagram-signing-secret-tests"
FB_VERIFY = "facebook-verify-token-tests"
IG_VERIFY = "instagram-verify-token-tests"

SEPARATED = {
    "META_APP_A_SECRET": FB_SIGNING,
    "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_VERIFY,
    "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGNING,
    "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
}


def _assert_no_secret_leak(haystack: str) -> None:
    for marker in (FB_SIGNING, IG_SIGNING, FB_VERIFY, IG_VERIFY, "shared-secret"):
        assert marker not in haystack


def test_valid_separation_is_ok() -> None:
    result = evaluate_meta_surface_secret_separation(SEPARATED)
    assert result.ok is True
    assert result.collisions == ()


@pytest.mark.parametrize(
    "missing_key",
    [
        "META_INSTAGRAM_LOGIN_APP_SECRET",
        "META_APP_A_SECRET",
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN",
        "META_APP_A_WEBHOOK_VERIFY_TOKEN",
    ],
)
def test_legacy_or_missing_side_is_not_a_collision(missing_key: str) -> None:
    values = dict(SEPARATED)
    values[missing_key] = ""
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is True
    assert result.collisions == ()


def test_signing_collision_uses_facebook_app_a_secret() -> None:
    values = dict(SEPARATED)
    values["META_INSTAGRAM_LOGIN_APP_SECRET"] = FB_SIGNING
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert result.collisions == (SIGNING_COLLISION,)


def test_signing_collision_uses_legacy_meta_app_secret_alias() -> None:
    values = {
        "META_APP_SECRET": "shared-secret-value-tests",
        "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_VERIFY,
        "META_INSTAGRAM_LOGIN_APP_SECRET": "shared-secret-value-tests",
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
    }
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert SIGNING_COLLISION in result.collisions


def test_verify_collision_uses_legacy_webhook_verify_alias() -> None:
    values = {
        "META_APP_A_SECRET": FB_SIGNING,
        "META_WEBHOOK_VERIFY_TOKEN": "shared-verify-token-tests",
        "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGNING,
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": "shared-verify-token-tests",
    }
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert result.collisions == (VERIFY_COLLISION,)


def test_both_signing_and_verify_collisions_are_reported() -> None:
    values = {
        "META_APP_A_SECRET": "shared-secret-value-tests",
        "META_APP_A_WEBHOOK_VERIFY_TOKEN": "shared-verify-token-tests",
        "META_INSTAGRAM_LOGIN_APP_SECRET": "shared-secret-value-tests",
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": "shared-verify-token-tests",
    }
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert result.collisions == (SIGNING_COLLISION, VERIFY_COLLISION)


def test_require_separated_exits_without_secret_values() -> None:
    values = dict(SEPARATED)
    values["META_INSTAGRAM_LOGIN_APP_SECRET"] = FB_SIGNING
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_separated_meta_surface_secrets(values)
    _assert_no_secret_leak(str(raised.value))


def test_apply_update_merges_existing_env_and_rejects_collision(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"META_APP_A_SECRET={FB_SIGNING}\nMETA_APP_A_WEBHOOK_VERIFY_TOKEN={FB_VERIFY}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_separated_meta_surface_secrets_for_update(
            env_path,
            {"META_INSTAGRAM_LOGIN_APP_SECRET": FB_SIGNING},
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_file_values(env_path)["META_APP_A_SECRET"] == FB_SIGNING


def test_apply_update_allows_distinct_instagram_secrets(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"META_APP_A_SECRET={FB_SIGNING}\nMETA_WEBHOOK_VERIFY_TOKEN={FB_VERIFY}\n",
        encoding="utf-8",
    )
    require_separated_meta_surface_secrets_for_update(env_path, SEPARATED)


def _instagram_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", FB_SIGNING)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", FB_VERIFY)
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", IG_SIGNING)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", IG_VERIFY)
    monkeypatch.setenv(
        "META_INSTAGRAM_LOGIN_REDIRECT_URI",
        "https://www.linasaibot.com/oauth/instagram/callback",
    )
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/instagram-login")
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")


def test_instagram_config_accepts_distinct_facebook_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instagram_config_env(monkeypatch)
    status = instagram_login_config_status()
    assert status.configured is True
    assert CONFIG_COLLISION_KEY not in status.missing


def test_instagram_config_fails_closed_on_signing_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instagram_config_env(monkeypatch)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", FB_SIGNING)
    status = instagram_login_config_status()
    assert status.configured is False
    assert CONFIG_COLLISION_KEY in status.missing
    _assert_no_secret_leak(" ".join(status.reasons.values()))


def test_instagram_config_fails_closed_on_verify_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instagram_config_env(monkeypatch)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", FB_VERIFY)
    status = instagram_login_config_status()
    assert status.configured is False
    assert CONFIG_COLLISION_KEY in status.missing
    _assert_no_secret_leak(" ".join(status.reasons.values()))


def test_apply_and_preflight_scripts_call_the_separation_gate() -> None:
    paths = [
        ROOT / "scripts" / "prod_apply_instagram_login_secrets.sh",
        ROOT / "scripts" / "prod_apply_meta_social_secrets.sh",
        ROOT / "scripts" / "prod_apply_meta_multi_app.sh",
        ROOT / "scripts" / "prod_set_meta_verify_token.sh",
        ROOT / "scripts" / "prod_preflight_readonly.sh",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "meta_surface_secret_separation" in source, path.name
        assert COLLISION_EXIT not in source or path.name != "prod_preflight_readonly.sh"
        for marker in (FB_SIGNING, IG_SIGNING):
            assert marker not in source
