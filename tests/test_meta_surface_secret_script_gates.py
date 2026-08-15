"""Apply/preflight scripts fail closed on any present Facebook alias collision."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_surface_secret_separation import (
    COLLISION_EXIT,
    env_file_values,
    evaluate_meta_surface_secret_separation,
    require_converged_meta_surface_secrets_for_update,
)
from tests.test_meta_surface_secret_separation import (
    FB_APP_B_SIGN,
    FB_APP_B_VERIFY,
    FB_CANON_SIGN,
    FB_CANON_VERIFY,
    FB_LEGACY_SIGN,
    FB_LEGACY_VERIFY,
    IG_SIGN,
    IG_VERIFY,
    SECRET_MARKERS,
    SHARED_SIGN,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEW_SIGN = "rotated-fb-sign-secret-99"
NEW_VERIFY = "rotated-fb-verify-token-9"

SIMULTANEOUS_ENV = (
    "\n".join(
        [
            f"META_APP_A_SECRET={FB_CANON_SIGN}",
            f"META_APP_SECRET={FB_CANON_SIGN}",
            f"META_APP_A_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
            f"META_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
            f"META_INSTAGRAM_LOGIN_APP_SECRET={IG_SIGN}",
            f"META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN={IG_VERIFY}",
        ]
    )
    + "\n"
)

APPLY_SCRIPTS = (
    "prod_apply_instagram_login_secrets.sh",
    "prod_apply_meta_social_secrets.sh",
    "prod_apply_meta_multi_app.sh",
    "prod_set_meta_verify_token.sh",
)
PREFLIGHT = "prod_preflight_readonly.sh"


def _write_env(tmp_path: Path, text: str = SIMULTANEOUS_ENV) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(text, encoding="utf-8")
    return env_path


def _disagreeing_signing_env() -> str:
    return SIMULTANEOUS_ENV.replace(f"META_APP_SECRET={FB_CANON_SIGN}", f"META_APP_SECRET={FB_LEGACY_SIGN}")


def _disagreeing_verify_env() -> str:
    return SIMULTANEOUS_ENV.replace(
        f"META_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
        f"META_WEBHOOK_VERIFY_TOKEN={FB_LEGACY_VERIFY}",
    )


def _assert_no_secret_leak(haystack: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in haystack


def test_apply_and_preflight_scripts_call_the_separation_gate() -> None:
    for name in (*APPLY_SCRIPTS, PREFLIGHT):
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "meta_surface_secret_separation" in source, name
        assert "_first_present" not in source, name
        for marker in SECRET_MARKERS:
            assert marker not in source
        if name == PREFLIGHT:
            assert "evaluate_meta_surface_secret_separation" in source
            gate_at = source.index("evaluate_meta_surface_secret_separation")
            assert "INSTAGRAM_FACEBOOK_SECRET_COLLISION" in source[gate_at:]
            continue
        require_call = "require_converged_meta_surface_secrets_for_update(ENV_PATH, updates)"
        apply_call = "atomic_update_env(ENV_PATH, updates)"
        assign_call = "updates = require_converged_meta_surface_secrets_for_update(ENV_PATH, updates)"
        assert require_call in source, name
        assert assign_call in source, name
        assert apply_call in source, name
        assert source.index(assign_call) < source.index(apply_call), name


def test_instagram_apply_rejects_legacy_facebook_signing_collision(tmp_path: Path) -> None:
    env_path = _write_env(tmp_path)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {
                "META_INSTAGRAM_LOGIN_APP_ID": "1035856539045307",
                "META_INSTAGRAM_LOGIN_APP_SECRET": FB_CANON_SIGN,
                "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
                "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED": "false",
            },
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_file_values(env_path)["META_APP_SECRET"] == FB_CANON_SIGN


def test_instagram_apply_accepts_agreeing_canonical_and_legacy(tmp_path: Path) -> None:
    require_converged_meta_surface_secrets_for_update(
        _write_env(tmp_path),
        {
            "META_INSTAGRAM_LOGIN_APP_ID": "1035856539045307",
            "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGN,
            "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
            "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED": "false",
        },
    )


def test_social_secrets_apply_repairs_disagreeing_facebook_signing_aliases(tmp_path: Path) -> None:
    env_path = _write_env(
        tmp_path,
        _disagreeing_signing_env(),
    )
    converged = require_converged_meta_surface_secrets_for_update(
        env_path,
        {
            "META_APP_SECRET": NEW_SIGN,
            "META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
        },
    )
    assert converged["META_APP_A_SECRET"] == NEW_SIGN
    assert converged["META_APP_SECRET"] == NEW_SIGN


def test_verify_token_apply_repairs_disagreeing_facebook_verify_aliases(tmp_path: Path) -> None:
    env_path = _write_env(tmp_path, _disagreeing_verify_env())
    converged = require_converged_meta_surface_secrets_for_update(
        env_path,
        {"META_WEBHOOK_VERIFY_TOKEN": NEW_VERIFY},
    )
    assert converged["META_APP_A_WEBHOOK_VERIFY_TOKEN"] == NEW_VERIFY
    assert converged["META_WEBHOOK_VERIFY_TOKEN"] == NEW_VERIFY


def test_social_secrets_apply_rejects_legacy_signing_collision_with_distinct_canonical(
    tmp_path: Path,
) -> None:
    env_path = _write_env(tmp_path)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {
                "META_APP_SECRET": IG_SIGN,
                "META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
            },
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_file_values(env_path)["META_APP_A_SECRET"] == FB_CANON_SIGN


def test_social_secrets_apply_accepts_agreeing_legacy_facebook_aliases(tmp_path: Path) -> None:
    require_converged_meta_surface_secrets_for_update(
        _write_env(tmp_path),
        {
            "META_APP_SECRET": FB_CANON_SIGN,
            "META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
        },
    )


def test_multi_app_apply_rejects_copied_app_a_collision_with_instagram(tmp_path: Path) -> None:
    env_path = _write_env(tmp_path)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {
                "META_APP_SECRET": SHARED_SIGN,
                "META_APP_A_SECRET": SHARED_SIGN,
                "META_WEBHOOK_VERIFY_TOKEN": FB_LEGACY_VERIFY,
                "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
                "META_INSTAGRAM_LOGIN_APP_SECRET": SHARED_SIGN,
            },
        )
    _assert_no_secret_leak(str(raised.value))


def test_multi_app_apply_rejects_app_b_signing_collision_before_mutation(tmp_path: Path) -> None:
    env_path = _write_env(tmp_path)
    before = env_path.read_bytes()
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {
                "META_APP_B_ID": "998877665544",
                "META_APP_B_SECRET": IG_SIGN,
                "META_APP_B_WEBHOOK_VERIFY_TOKEN": FB_APP_B_VERIFY,
                "META_APP_B_LOGIN_CONFIG_ID": "config-b-tests",
            },
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_path.read_bytes() == before
    assert env_file_values(env_path)["META_INSTAGRAM_LOGIN_APP_SECRET"] == IG_SIGN


def test_multi_app_apply_rejects_app_b_verify_collision_before_mutation(tmp_path: Path) -> None:
    env_path = _write_env(tmp_path)
    before = env_path.read_bytes()
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {
                "META_APP_B_ID": "998877665544",
                "META_APP_B_SECRET": FB_APP_B_SIGN,
                "META_APP_B_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
                "META_APP_B_LOGIN_CONFIG_ID": "config-b-tests",
            },
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_path.read_bytes() == before
    assert env_file_values(env_path)["META_APP_A_WEBHOOK_VERIFY_TOKEN"] == FB_CANON_VERIFY
    assert env_file_values(env_path)["META_WEBHOOK_VERIFY_TOKEN"] == FB_CANON_VERIFY
    assert env_file_values(env_path)["META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN"] == IG_VERIFY


def test_multi_app_apply_accepts_agreeing_copied_aliases(tmp_path: Path) -> None:
    require_converged_meta_surface_secrets_for_update(
        _write_env(tmp_path),
        {
            "META_APP_SECRET": FB_LEGACY_SIGN,
            "META_APP_A_SECRET": FB_LEGACY_SIGN,
            "META_WEBHOOK_VERIFY_TOKEN": FB_LEGACY_VERIFY,
            "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_LEGACY_VERIFY,
        },
    )


def test_verify_token_apply_rejects_legacy_collision_with_distinct_canonical(
    tmp_path: Path,
) -> None:
    env_path = _write_env(tmp_path)
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {"META_WEBHOOK_VERIFY_TOKEN": IG_VERIFY},
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_file_values(env_path)["META_APP_A_WEBHOOK_VERIFY_TOKEN"] == FB_CANON_VERIFY


def test_verify_token_apply_accepts_agreeing_legacy_verify(tmp_path: Path) -> None:
    require_converged_meta_surface_secrets_for_update(
        _write_env(tmp_path),
        {"META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY},
    )


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (SIMULTANEOUS_ENV, True),
        (
            SIMULTANEOUS_ENV.replace(
                f"META_APP_SECRET={FB_CANON_SIGN}",
                f"META_APP_SECRET={IG_SIGN}",
            ),
            False,
        ),
        (
            SIMULTANEOUS_ENV.replace(
                f"META_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_WEBHOOK_VERIFY_TOKEN={IG_VERIFY}",
            ),
            False,
        ),
        (
            SIMULTANEOUS_ENV.replace(
                f"META_APP_A_SECRET={FB_CANON_SIGN}",
                f"META_APP_A_SECRET={IG_SIGN}",
            ),
            False,
        ),
        (
            "\n".join(
                [
                    f"META_APP_A_SECRET={FB_CANON_SIGN}",
                    f"META_INSTAGRAM_LOGIN_APP_SECRET={IG_SIGN}",
                ]
            )
            + "\n",
            True,
        ),
    ],
)
def test_readonly_preflight_closed_set_on_env_file(tmp_path: Path, text: str, ok: bool) -> None:
    env_path = _write_env(tmp_path, text)
    result = evaluate_meta_surface_secret_separation(env_file_values(env_path))
    assert result.ok is ok
    if not ok:
        assert result.collisions
