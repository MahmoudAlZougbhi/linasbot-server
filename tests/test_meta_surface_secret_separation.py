"""Instagram vs Facebook Meta secret separation: closed-set aliases, never print values."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_instagram_login_config import instagram_login_config_status
from services.meta_messaging import get_meta_messaging_settings
from services.meta_surface_secret_separation import (
    COLLISION_EXIT,
    CONFIG_COLLISION_KEY,
    FACEBOOK_SIGNING_ALIAS_MISMATCH,
    FACEBOOK_VERIFY_ALIAS_MISMATCH,
    SIGNING_COLLISION,
    VERIFY_COLLISION,
    converge_facebook_surface_secret_updates,
    env_file_values,
    evaluate_meta_surface_secret_separation,
    require_separated_meta_surface_secrets,
    require_separated_meta_surface_secrets_for_update,
)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "services" / "meta_surface_secret_separation.py"

FB_CANON_SIGN = "fb-canon-sign-secret-001"
FB_LEGACY_SIGN = "fb-legacy-sign-secret-01"
IG_SIGN = "ig-login-sign-secret-001"
SHARED_SIGN = "shared-sign-secret-value"
FB_CANON_VERIFY = "fb-canon-verify-00000001"
FB_LEGACY_VERIFY = "fb-legacy-verify-0000001"
FB_APP_B_SIGN = "fb-app-b-sign-secret-001"
FB_APP_B_VERIFY = "fb-app-b-verify-00000001"
IG_VERIFY = "ig-login-verify-00000001"
SHARED_VERIFY = "shared-verify-0000000001"

SEPARATED = {
    "META_APP_A_SECRET": FB_CANON_SIGN,
    "META_APP_SECRET": FB_CANON_SIGN,
    "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
    "META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
    "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGN,
    "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
    "META_APP_B_SECRET": FB_APP_B_SIGN,
    "META_APP_B_WEBHOOK_VERIFY_TOKEN": FB_APP_B_VERIFY,
}

SECRET_MARKERS = (
    FB_CANON_SIGN,
    FB_LEGACY_SIGN,
    IG_SIGN,
    SHARED_SIGN,
    FB_CANON_VERIFY,
    FB_LEGACY_VERIFY,
    FB_APP_B_SIGN,
    FB_APP_B_VERIFY,
    IG_VERIFY,
    SHARED_VERIFY,
)


def _values(**overrides: str) -> dict[str, str]:
    merged = dict(SEPARATED)
    merged.update(overrides)
    return merged


def _assert_no_secret_leak(haystack: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in haystack


def test_helper_does_not_use_first_present_precedence() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "_first_present" not in source
    assert "_present_secrets" in source
    assert "_cross_surface_collision" in source
    assert "FACEBOOK_APP_B_SIGNING_KEYS" in source
    assert "FACEBOOK_APP_B_VERIFY_KEYS" in source


def test_valid_simultaneous_agreeing_aliases_are_ok() -> None:
    result = evaluate_meta_surface_secret_separation(SEPARATED)
    assert result.ok is True
    assert result.collisions == ()


def test_distinct_app_b_allowed_without_matching_app_a() -> None:
    values = _values(
        META_APP_A_SECRET=FB_CANON_SIGN,
        META_APP_SECRET=FB_CANON_SIGN,
        META_APP_B_SECRET=FB_APP_B_SIGN,
        META_APP_B_WEBHOOK_VERIFY_TOKEN=FB_APP_B_VERIFY,
    )
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is True
    assert result.collisions == ()


def test_app_b_signing_collision_with_instagram_is_fail_closed() -> None:
    values = _values(META_APP_B_SECRET=SHARED_SIGN, META_INSTAGRAM_LOGIN_APP_SECRET=SHARED_SIGN)
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert result.collisions == (SIGNING_COLLISION,)


def test_app_b_verify_collision_with_instagram_is_fail_closed() -> None:
    values = _values(
        META_APP_B_WEBHOOK_VERIFY_TOKEN=SHARED_VERIFY,
        META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN=SHARED_VERIFY,
    )
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert result.collisions == (VERIFY_COLLISION,)


def test_app_b_collision_exit_is_value_free() -> None:
    values = _values(META_APP_B_SECRET=SHARED_SIGN, META_INSTAGRAM_LOGIN_APP_SECRET=SHARED_SIGN)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_separated_meta_surface_secrets(values)
    _assert_no_secret_leak(str(raised.value))


NEW_SIGN = "rotated-fb-sign-secret-99"


def test_app_a_alias_convergence_does_not_mirror_into_app_b() -> None:
    existing = {
        "META_APP_A_SECRET": FB_CANON_SIGN,
        "META_APP_SECRET": FB_LEGACY_SIGN,
        "META_APP_B_SECRET": FB_APP_B_SIGN,
        "META_APP_B_WEBHOOK_VERIFY_TOKEN": FB_APP_B_VERIFY,
    }
    converged = converge_facebook_surface_secret_updates(
        existing,
        {"META_APP_SECRET": NEW_SIGN},
    )
    assert converged["META_APP_A_SECRET"] == NEW_SIGN
    assert converged["META_APP_SECRET"] == NEW_SIGN
    assert "META_APP_B_SECRET" not in converged
    assert "META_APP_B_WEBHOOK_VERIFY_TOKEN" not in converged


@pytest.mark.parametrize(
    ("overrides", "collisions"),
    [
        ({"META_APP_A_SECRET": ""}, ()),
        ({"META_APP_SECRET": ""}, ()),
        ({"META_APP_A_WEBHOOK_VERIFY_TOKEN": ""}, ()),
        ({"META_WEBHOOK_VERIFY_TOKEN": ""}, ()),
        ({"META_INSTAGRAM_LOGIN_APP_SECRET": ""}, ()),
        ({"META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": ""}, ()),
        ({"META_APP_A_SECRET": "", "META_APP_SECRET": ""}, ()),
        ({"META_APP_A_WEBHOOK_VERIFY_TOKEN": "", "META_WEBHOOK_VERIFY_TOKEN": ""}, ()),
        ({"META_APP_SECRET": FB_CANON_SIGN}, ()),
        ({"META_APP_SECRET": FB_LEGACY_SIGN}, (FACEBOOK_SIGNING_ALIAS_MISMATCH,)),
        ({"META_WEBHOOK_VERIFY_TOKEN": FB_LEGACY_VERIFY}, (FACEBOOK_VERIFY_ALIAS_MISMATCH,)),
        (
            {
                "META_APP_A_SECRET": SHARED_SIGN,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
            (FACEBOOK_SIGNING_ALIAS_MISMATCH, SIGNING_COLLISION),
        ),
        (
            {
                "META_APP_SECRET": SHARED_SIGN,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
            (FACEBOOK_SIGNING_ALIAS_MISMATCH, SIGNING_COLLISION),
        ),
        (
            {
                "META_APP_A_SECRET": SHARED_SIGN,
                "META_APP_SECRET": SHARED_SIGN,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
            (SIGNING_COLLISION,),
        ),
        (
            {
                "META_APP_A_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (FACEBOOK_VERIFY_ALIAS_MISMATCH, VERIFY_COLLISION),
        ),
        (
            {
                "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (FACEBOOK_VERIFY_ALIAS_MISMATCH, VERIFY_COLLISION),
        ),
        (
            {
                "META_APP_A_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (VERIFY_COLLISION,),
        ),
        (
            {
                "META_APP_SECRET": SHARED_SIGN,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
                "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (
                FACEBOOK_SIGNING_ALIAS_MISMATCH,
                FACEBOOK_VERIFY_ALIAS_MISMATCH,
                SIGNING_COLLISION,
                VERIFY_COLLISION,
            ),
        ),
        (
            {
                "META_APP_A_SECRET": SHARED_SIGN,
                "META_APP_SECRET": "",
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
            (SIGNING_COLLISION,),
        ),
        (
            {
                "META_APP_A_SECRET": "",
                "META_APP_SECRET": SHARED_SIGN,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
            (SIGNING_COLLISION,),
        ),
        (
            {
                "META_APP_A_WEBHOOK_VERIFY_TOKEN": "",
                "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (VERIFY_COLLISION,),
        ),
        (
            {
                "META_APP_A_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
                "META_WEBHOOK_VERIFY_TOKEN": "",
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            },
            (VERIFY_COLLISION,),
        ),
    ],
)
def test_closed_set_alias_matrix(overrides: dict[str, str], collisions: tuple[str, ...]) -> None:
    result = evaluate_meta_surface_secret_separation(_values(**overrides))
    assert result.ok is (not collisions)
    assert result.collisions == collisions


def test_require_separated_exits_without_secret_values() -> None:
    values = _values(META_APP_SECRET=SHARED_SIGN, META_INSTAGRAM_LOGIN_APP_SECRET=SHARED_SIGN)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_separated_meta_surface_secrets(values)
    _assert_no_secret_leak(str(raised.value))


def test_apply_update_merges_existing_env_and_rejects_legacy_collision(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"META_APP_A_SECRET={FB_CANON_SIGN}",
                f"META_APP_SECRET={SHARED_SIGN}",
                f"META_APP_A_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_WEBHOOK_VERIFY_TOKEN={FB_LEGACY_VERIFY}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_separated_meta_surface_secrets_for_update(
            env_path,
            {"META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN},
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_file_values(env_path)["META_APP_A_SECRET"] == FB_CANON_SIGN
    assert env_file_values(env_path)["META_APP_SECRET"] == SHARED_SIGN


def test_apply_update_allows_distinct_instagram_secrets(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"META_APP_A_SECRET={FB_CANON_SIGN}\nMETA_WEBHOOK_VERIFY_TOKEN={FB_LEGACY_VERIFY}\n",
        encoding="utf-8",
    )
    require_separated_meta_surface_secrets_for_update(env_path, SEPARATED)


def _instagram_config_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", FB_CANON_SIGN)
    monkeypatch.setenv("META_APP_SECRET", FB_CANON_SIGN)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", IG_SIGN)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", IG_VERIFY)
    monkeypatch.setenv(
        "META_INSTAGRAM_LOGIN_REDIRECT_URI",
        "https://www.linasaibot.com/oauth/instagram/callback",
    )
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/instagram-login")
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    for key, value in overrides.items():
        if value == "":
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_instagram_config_accepts_simultaneous_agreeing_facebook_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instagram_config_env(monkeypatch)
    status = instagram_login_config_status()
    assert status.configured is True
    assert CONFIG_COLLISION_KEY not in status.missing


@pytest.mark.parametrize(
    "overrides",
    [
        {"META_APP_SECRET": SHARED_SIGN, "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN},
        {"META_APP_A_SECRET": SHARED_SIGN, "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN},
        {"META_APP_SECRET": FB_LEGACY_SIGN},
        {
            "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
        },
        {
            "META_APP_A_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
            "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
        },
    ],
)
def test_instagram_config_fails_closed_on_any_present_alias_collision(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, str],
) -> None:
    _instagram_config_env(monkeypatch, **overrides)
    status = instagram_login_config_status()
    assert status.configured is False
    assert CONFIG_COLLISION_KEY in status.missing
    _assert_no_secret_leak(" ".join(status.reasons.values()))


def test_meta_messaging_consumes_legacy_aliases_not_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_APP_A_SECRET", FB_CANON_SIGN)
    monkeypatch.setenv("META_APP_SECRET", FB_LEGACY_SIGN)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", FB_LEGACY_VERIFY)
    settings = get_meta_messaging_settings()
    assert settings.app_secret == FB_LEGACY_SIGN
    assert settings.verify_token == FB_LEGACY_VERIFY
