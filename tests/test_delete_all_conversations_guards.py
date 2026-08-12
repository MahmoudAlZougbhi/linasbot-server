"""Unit tests for destructive conversation-delete CLI guards (no Firestore)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "delete_all_conversations.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("delete_all_conversations_guards", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Avoid polluting sys.modules name clashes with future archive path.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_mod()


def test_resolve_mode_defaults_to_dry_run(mod):
    args = mod.build_parser().parse_args([])
    dry_run, execute = mod.resolve_mode(args)
    assert dry_run is True
    assert execute is False


def test_resolve_mode_explicit_dry_run(mod):
    args = mod.build_parser().parse_args(["--dry-run"])
    dry_run, execute = mod.resolve_mode(args)
    assert dry_run is True
    assert execute is False


def test_legacy_confirm_alone_does_not_execute(mod):
    args = mod.build_parser().parse_args(["--confirm"])
    dry_run, execute = mod.resolve_mode(args)
    assert dry_run is True
    assert execute is False


def test_execute_requires_exact_phrase(mod):
    with pytest.raises(SystemExit) as ei:
        mod.assert_execute_allowed(
            execute=True,
            confirm_phrase="yes",
            environ={},
            has_credentials=False,
        )
    assert "typed phrase" in str(ei.value).lower() or "I_UNDERSTAND" in str(ei.value)


def test_execute_blocked_when_prod_without_allow(mod):
    with pytest.raises(SystemExit) as ei:
        mod.assert_execute_allowed(
            execute=True,
            confirm_phrase=mod.CONFIRM_PHRASE,
            environ={"ENV": "production"},
            has_credentials=False,
        )
    assert "LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE" in str(ei.value)


def test_execute_blocked_when_creds_without_allow(mod):
    with pytest.raises(SystemExit) as ei:
        mod.assert_execute_allowed(
            execute=True,
            confirm_phrase=mod.CONFIRM_PHRASE,
            environ={"ENV": "development"},
            has_credentials=True,
        )
    assert "LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE" in str(ei.value)


def test_execute_allowed_with_phrase_and_allow_env(mod):
    mod.assert_execute_allowed(
        execute=True,
        confirm_phrase=mod.CONFIRM_PHRASE,
        environ={
            "ENV": "production",
            mod.ALLOW_ENV: "1",
        },
        has_credentials=True,
    )


def test_dry_run_skips_guards(mod):
    # Must not raise even in production-looking env.
    mod.assert_execute_allowed(
        execute=False,
        confirm_phrase="",
        environ={"ENV": "production"},
        has_credentials=True,
    )


def test_env_looks_like_production_helpers(mod):
    assert mod._env_looks_like_production({"ENVIRONMENT": "prod"}) is True
    assert mod._env_looks_like_production({"ENV": "development"}) is False
    assert mod._env_looks_like_production({"HOSTNAME": "linasaibot-prod"}) is True
