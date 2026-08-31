"""Regression coverage for bounded HA post-admission readiness retries."""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _ready_assertion_source() -> str:
    source = HELPER.read_text(encoding="utf-8")
    return source[source.index("assert_serving_ready_for_sha() {") : source.index("assert_public_ready() {")]


def test_live_ready_fetch_normalizes_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ha import target_platform_readiness_preflight as mod

    def timeout(*_args: object, **_kwargs: object) -> object:
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", timeout)
    with pytest.raises(RuntimeError, match="could not be reached"):
        mod.fetch_live_ready()


def test_serving_ready_assertion_retries_transient_probe_failure() -> None:
    expected_sha = "a" * 40
    script = f"""
probe_count=0
probe_serving_ready_for_sha() {{
  probe_count=$((probe_count + 1))
  test "$probe_count" -ge 2
}}
sleep() {{ :; }}
die() {{ return 1; }}
{_ready_assertion_source()}
assert_serving_ready_for_sha "{expected_sha}"
test "$probe_count" = 2
"""
    subprocess.run(["bash", "-c", script], check=True)


def test_serving_ready_assertion_stays_bounded_when_probe_never_recovers() -> None:
    expected_sha = "a" * 40
    script = f"""
probe_count=0
sleep_count=0
probe_serving_ready_for_sha() {{
  probe_count=$((probe_count + 1))
  return 1
}}
sleep() {{ sleep_count=$((sleep_count + 1)); }}
die() {{ return 1; }}
{_ready_assertion_source()}
if assert_serving_ready_for_sha "{expected_sha}"; then
  exit 1
fi
test "$probe_count" = 36
test "$sleep_count" = 35
"""
    subprocess.run(["bash", "-c", script], check=True)
