"""Unit tests for durable CM_DISABLE_LINAS_LEGACY_BRIDGE preservation."""

from __future__ import annotations

from pathlib import Path

from services.cm.durable_flags import (
    CM_DISABLE_LINAS_LEGACY_BRIDGE,
    parse_env_bool,
    preserve_disable_linas_legacy_bridge,
    readiness_requires_disable_bridge,
    read_env_file_map,
    resolve_disable_bridge_value,
)


def test_resolve_prefers_true_when_any_path_true() -> None:
    value, reason = resolve_disable_bridge_value([None, True, False], linas_has_published_cm=True)
    assert value is True
    assert "true" in reason


def test_resolve_recovers_true_when_published_and_missing() -> None:
    value, reason = resolve_disable_bridge_value([None, None], linas_has_published_cm=True)
    assert value is True
    assert "recover" in reason


def test_resolve_keeps_unset_when_unpublished() -> None:
    value, reason = resolve_disable_bridge_value([None], linas_has_published_cm=False)
    assert value is None
    assert "unset" in reason


def test_preserve_syncs_dual_env_files(tmp_path: Path) -> None:
    root = tmp_path / "opt" / "linasbot"
    nested = root / "linaslaserbot-2.7.22"
    root.mkdir(parents=True)
    nested.mkdir(parents=True)
    (root / ".env").write_text("OPENAI_API_KEY=redacted\nCM_DISABLE_LINAS_LEGACY_BRIDGE=true\n", encoding="utf-8")
    (nested / ".env").write_text("OPENAI_API_KEY=redacted\n", encoding="utf-8")

    report = preserve_disable_linas_legacy_bridge(
        [root / ".env", nested / ".env"],
        linas_has_published_cm=True,
        dry_run=False,
    )
    assert report["ok"] is True
    assert report["effective"] is True
    assert parse_env_bool(read_env_file_map(nested / ".env").get(CM_DISABLE_LINAS_LEGACY_BRIDGE)) is True
    # Non-CM secrets remain present (not wiped).
    assert "OPENAI_API_KEY" in read_env_file_map(root / ".env")


def test_preserve_recovers_missing_flag_for_published_linas(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    env_path = app / ".env"
    env_path.write_text("CM_PUBLISH_ENABLED=true\n", encoding="utf-8")
    report = preserve_disable_linas_legacy_bridge(
        [env_path],
        linas_has_published_cm=True,
        dry_run=False,
    )
    assert report["ok"] is True
    assert report["reason"] == "recover_true_for_published_linas"
    assert parse_env_bool(read_env_file_map(env_path).get(CM_DISABLE_LINAS_LEGACY_BRIDGE)) is True


def test_readiness_fails_when_published_without_disable() -> None:
    gate = readiness_requires_disable_bridge(
        linas_has_published_cm=True,
        effective_disable_bridge=False,
    )
    assert gate["ok"] is False
    assert gate["failures"]


def test_readiness_passes_when_published_and_disabled() -> None:
    gate = readiness_requires_disable_bridge(
        linas_has_published_cm=True,
        effective_disable_bridge=True,
    )
    assert gate["ok"] is True
