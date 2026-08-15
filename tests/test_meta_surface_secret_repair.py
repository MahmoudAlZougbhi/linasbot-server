"""Repair path: converge Facebook aliases without weakening runtime fail-closed."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_surface_secret_separation import (
    COLLISION_EXIT,
    FACEBOOK_SIGNING_ALIAS_MISMATCH,
    RELEASE_ONLY_VERIFY_MODES,
    SIGNING_COLLISION,
    VERIFY_COLLISION,
    env_file_values,
    evaluate_meta_surface_secret_separation,
    operator_gate_allows_separation,
    require_converged_meta_surface_secrets_for_update,
)
from tests.test_meta_surface_secret_separation import (
    FB_CANON_SIGN,
    FB_CANON_VERIFY,
    FB_LEGACY_SIGN,
    FB_LEGACY_VERIFY,
    IG_SIGN,
    IG_VERIFY,
    SECRET_MARKERS,
    SHARED_SIGN,
)

ROOT = Path(__file__).parents[1]
NEW_SIGN = "rotated-fb-sign-secret-99"
NEW_VERIFY = "rotated-fb-verify-token-9"


def _assert_no_secret_leak(haystack: str) -> None:
    for marker in (*SECRET_MARKERS, NEW_SIGN, NEW_VERIFY):
        assert marker not in haystack


def _disagreeing_signing_env() -> str:
    return (
        "\n".join(
            [
                f"META_APP_A_SECRET={FB_CANON_SIGN}",
                f"META_APP_SECRET={FB_LEGACY_SIGN}",
                f"META_APP_A_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_INSTAGRAM_LOGIN_APP_SECRET={IG_SIGN}",
                f"META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN={IG_VERIFY}",
            ]
        )
        + "\n"
    )


def _disagreeing_verify_env() -> str:
    return (
        "\n".join(
            [
                f"META_APP_A_SECRET={FB_CANON_SIGN}",
                f"META_APP_SECRET={FB_CANON_SIGN}",
                f"META_APP_A_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_WEBHOOK_VERIFY_TOKEN={FB_LEGACY_VERIFY}",
                f"META_INSTAGRAM_LOGIN_APP_SECRET={IG_SIGN}",
                f"META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN={IG_VERIFY}",
            ]
        )
        + "\n"
    )


def _collision_env() -> str:
    return (
        "\n".join(
            [
                f"META_APP_A_SECRET={SHARED_SIGN}",
                f"META_APP_SECRET={FB_LEGACY_SIGN}",
                f"META_APP_A_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_WEBHOOK_VERIFY_TOKEN={FB_CANON_VERIFY}",
                f"META_INSTAGRAM_LOGIN_APP_SECRET={SHARED_SIGN}",
                f"META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN={IG_VERIFY}",
            ]
        )
        + "\n"
    )


def test_runtime_still_fails_on_facebook_alias_disagreement(tmp_path: Path) -> None:
    values = env_file_values_from_text(_disagreeing_signing_env(), tmp_path)
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert FACEBOOK_SIGNING_ALIAS_MISMATCH in result.collisions


def test_runtime_still_fails_on_cross_surface_collision(tmp_path: Path) -> None:
    values = env_file_values_from_text(_collision_env(), tmp_path)
    result = evaluate_meta_surface_secret_separation(values)
    assert result.ok is False
    assert SIGNING_COLLISION in result.collisions


def test_operator_gate_allows_release_only_preflight_from_bad_state(tmp_path: Path) -> None:
    values = env_file_values_from_text(_disagreeing_signing_env(), tmp_path)
    for mode in RELEASE_ONLY_VERIFY_MODES:
        assert operator_gate_allows_separation(values, verify_mode=mode) is True


def test_operator_gate_blocks_bad_state_on_strict_cluster_verify(tmp_path: Path) -> None:
    values = env_file_values_from_text(_disagreeing_signing_env(), tmp_path)
    assert operator_gate_allows_separation(values, verify_mode="cluster") is False


def test_repair_converges_disagreeing_facebook_signing_aliases(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(_disagreeing_signing_env(), encoding="utf-8")
    before = env_path.read_text(encoding="utf-8")
    converged = require_converged_meta_surface_secrets_for_update(
        env_path,
        {"META_APP_SECRET": NEW_SIGN, "META_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY},
    )
    assert converged["META_APP_SECRET"] == NEW_SIGN
    assert converged["META_APP_A_SECRET"] == NEW_SIGN
    assert env_path.read_text(encoding="utf-8") == before
    merged = env_file_values(env_path)
    merged.update(converged)
    assert evaluate_meta_surface_secret_separation(merged).ok is True


def test_repair_converges_disagreeing_facebook_verify_aliases(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(_disagreeing_verify_env(), encoding="utf-8")
    converged = require_converged_meta_surface_secrets_for_update(
        env_path,
        {"META_WEBHOOK_VERIFY_TOKEN": NEW_VERIFY},
    )
    assert converged["META_WEBHOOK_VERIFY_TOKEN"] == NEW_VERIFY
    assert converged["META_APP_A_WEBHOOK_VERIFY_TOKEN"] == NEW_VERIFY
    merged = env_file_values(env_path)
    merged.update(converged)
    assert evaluate_meta_surface_secret_separation(merged).ok is True


def test_repair_rejects_rotation_that_preserves_cross_surface_collision(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(_collision_env(), encoding="utf-8")
    before = env_path.read_bytes()
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {"META_APP_SECRET": SHARED_SIGN, "META_APP_A_SECRET": SHARED_SIGN},
        )
    _assert_no_secret_leak(str(raised.value))
    assert env_path.read_bytes() == before


def test_repair_fixes_cross_surface_collision_with_distinct_rotation(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(_collision_env(), encoding="utf-8")
    converged = require_converged_meta_surface_secrets_for_update(
        env_path,
        {"META_APP_SECRET": NEW_SIGN, "META_APP_A_SECRET": NEW_SIGN},
    )
    merged = env_file_values(env_path)
    merged.update(converged)
    result = evaluate_meta_surface_secret_separation(merged)
    assert result.ok is True
    assert VERIFY_COLLISION not in result.collisions


def test_converge_failure_does_not_leak_secret_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(_collision_env(), encoding="utf-8")
    with pytest.raises(SystemExit, match=COLLISION_EXIT) as raised:
        require_converged_meta_surface_secrets_for_update(
            env_path,
            {"META_APP_SECRET": SHARED_SIGN, "META_APP_A_SECRET": SHARED_SIGN},
        )
    _assert_no_secret_leak(str(raised.value))


def test_ha_verifier_skips_separation_only_on_release_only_preflight() -> None:
    source = (ROOT / "scripts" / "ha" / "verify_meta_release_ha.sh").read_text(encoding="utf-8")
    assert "operator_gate_allows_separation" in source
    assert "RELEASE_ONLY_VERIFY_MODES" not in source
    assert "cluster-release-only" in source
    assert "local-release-only" in source
    assert "verify_mode = sys.argv[3]" in source


def env_file_values_from_text(text: str, tmp_path: Path) -> dict[str, str]:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return env_file_values(path)
