"""Executable LB-convergence and successor-control tests for orphan recovery."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import stat
import subprocess
import sys
import urllib
import urllib.error
import urllib.request

import pytest

from scripts.ha.do_lb_ready_contract import LB_HEALTH_CONTRACT
from scripts.ha.public_ready_lb_wait_contract import public_ready_wait_timeout_seconds
from tests.test_meta_app_a_login_config_maintenance_recover import (
    BASELINE_SHA,
    FAILED_RUN_ID,
    _helper_python,
    _script,
)

PRIOR_CONTROL = "706c14ab1a11d57f6caf2de1107a2cb8cd149334"
CURRENT_CONTROL = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SCHEMA = "linas-orphan-maintenance-recovery-v1"
WINDOW_MSG = "public load-balancer readiness did not become healthy within the LB health window"


def _ns() -> dict:
    helper = _helper_python()
    start = helper.index("def fsync_dir")
    end = helper.index("if cmd == ")
    globs: dict = {
        "json": json,
        "os": os,
        "stat": stat,
        "hashlib": hashlib,
        "hmac": hmac,
        "subprocess": subprocess,
        "sys": sys,
        "urllib": urllib,
    }
    exec(compile(helper[start:end], "<helper>", "exec"), globs)
    return globs


def _phase(control: str, phase: str) -> dict:
    return {
        "schema": SCHEMA,
        "baseline": BASELINE_SHA,
        "failed_run": FAILED_RUN_ID,
        "control_sha": control,
        "phase": phase,
    }


def test_empty_httperror_is_sanitized_probe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    ns = _ns()

    def boom(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://www.linasaibot.com/api/ready",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b""),
        )

    monkeypatch.setattr(ns["urllib"].request, "urlopen", boom)
    status, body = ns["fetch_probe"]("https://www.linasaibot.com/api/ready")
    assert status == 503
    assert body is None
    with pytest.raises(SystemExit, match="probe status or JSON is invalid") as exc:
        ns["probe"]("https://www.linasaibot.com/api/ready", 200, "ready-ok")
    assert exc.value.code != 0
    assert "Traceback" not in str(exc.value)
    assert not isinstance(exc.value, json.JSONDecodeError)


def test_non_json_503_is_not_public_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ns = _ns()

    def boom(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://www.linasaibot.com/api/ready",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b"no healthy backends"),
        )

    monkeypatch.setattr(ns["urllib"].request, "urlopen", boom)
    status, body = ns["fetch_probe"]("https://www.linasaibot.com/api/ready")
    assert status == 503 and body is None


def test_fetch_probe_catches_only_urlerror_and_timeout() -> None:
    helper = _helper_python()
    body = helper[helper.index("def fetch_probe") : helper.index("def public_ok")]
    assert "except Exception" not in body
    assert "urllib.error.URLError, TimeoutError" in body
    assert "HTTPError" in body


def test_span_tick_allows_initial_503_then_full_stable_drain_window() -> None:
    tick = _ns()["span_tick"]
    drain = 30
    converge = public_ready_wait_timeout_seconds(
        int(LB_HEALTH_CONTRACT["check_interval_seconds"]),
        int(LB_HEALTH_CONTRACT["healthy_threshold"]),
    )
    assert converge == 5 * 2 + 90
    start = 1_000_000
    assert tick(start, start, 0, False, drain) == "0"
    assert tick(start, start + 10, 0, False, drain) == "0"
    stable = int(tick(start, start + 15, 0, True, drain))
    assert stable == start + 15
    assert tick(start, start + 15 + drain - 1, stable, True, drain) == str(stable)
    assert tick(start, start + 15 + drain, stable, True, drain) == "done"


def test_span_tick_flapping_public_resets_stable_window() -> None:
    tick = _ns()["span_tick"]
    start = 1_000_000
    drain = 30
    stable = int(tick(start, start + 5, 0, True, drain))
    assert tick(start, start + 10, stable, False, drain) == "0"
    again = int(tick(start, start + 12, 0, True, drain))
    assert again == start + 12
    assert tick(start, start + 12 + drain - 1, again, True, drain) != "done"
    assert tick(start, start + 12 + drain, again, True, drain) == "done"


def _converge() -> int:
    timeout = public_ready_wait_timeout_seconds(
        int(LB_HEALTH_CONTRACT["check_interval_seconds"]),
        int(LB_HEALTH_CONTRACT["healthy_threshold"]),
    )
    assert timeout == 5 * 2 + 90
    return timeout


def _drive(samples: list[bool], *, start: int = 1_000_000, step: int = 5, drain: int = 30) -> tuple[str, int]:
    tick = _ns()["span_tick"]
    now = start
    stable = 0
    for pub_ok in samples:
        try:
            out = tick(start, now, stable, pub_ok, drain)
        except SystemExit:
            return "timeout", now
        if out == "done":
            return "done", now
        stable = int(out)
        now += step
    return "open", now


def test_public_ok_keeps_ready_ok_semantics_not_ok_true_alone() -> None:
    public_ok = _ns()["public_ok"]
    ready = {"ok": True, "role": "readiness", "checks": {"maintenance": {"ok": True}}}
    assert public_ok(200, ready) is True
    assert public_ok(200, {"ok": True}) is False
    assert public_ok(200, {"ok": True, "role": "readiness", "checks": {"x": {"ok": False}}}) is False
    assert public_ok(503, ready) is False


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), urllib.error.URLError("down")])
def test_timeout_and_urlerror_are_soft_public_not_ready(exc: BaseException, monkeypatch: pytest.MonkeyPatch) -> None:
    ns = _ns()

    def boom(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(ns["urllib"].request, "urlopen", boom)
    status, body = ns["fetch_probe"]("https://www.linasaibot.com/api/ready")
    assert status == 0 and body is None
    assert ns["public_ok"](status, body) is False


def test_span_tick_regression_after_converge_resets_inside_total_budget() -> None:
    tick = _ns()["span_tick"]
    start, drain, converge = 1_000_000, 30, _converge()
    assert tick(start, start + converge, 0, False, drain) == "0"
    assert tick(start, start + converge + 5, 0, False, drain) == "0"
    assert tick(start, start + converge + 5, 0, True, drain) == str(start + converge + 5)


def test_span_tick_exact_deadline_evaluates_success_before_timeout() -> None:
    tick = _ns()["span_tick"]
    start, drain, converge = 1_000_000, 30, _converge()
    stable = start + converge
    deadline = start + converge + drain
    assert tick(start, stable, 0, True, drain) == str(stable)
    assert tick(start, deadline, stable, True, drain) == "done"
    with pytest.raises(SystemExit, match=WINDOW_MSG):
        tick(start, deadline, stable + 1, True, drain)


def test_span_tick_late_success_after_deadline_fails() -> None:
    tick = _ns()["span_tick"]
    start, drain, converge = 1_000_000, 30, _converge()
    deadline = start + converge + drain
    stable = start + 25
    assert stable + drain > deadline
    with pytest.raises(SystemExit, match=WINDOW_MSG):
        tick(start, stable + drain, stable, True, drain)


def test_span_tick_monotonic_initial_503_then_done_at_exact_deadline() -> None:
    converge, drain, step = _converge(), 30, 5
    samples = [False] * (converge // step) + [True] * (drain // step + 1)
    outcome, now = _drive(samples, drain=drain, step=step)
    assert outcome == "done"
    assert now == 1_000_000 + converge + drain


def test_span_tick_monotonic_flap_after_converge_continues_until_budget() -> None:
    converge, drain, step = _converge(), 30, 5
    samples = [True, True, True, False, False, False] + [True] * (drain // step)
    outcome, now = _drive(samples, drain=drain, step=step)
    assert outcome == "timeout"
    assert now == 1_000_000 + converge + drain


def test_span_tick_timeout_only_at_total_budget() -> None:
    tick = _ns()["span_tick"]
    start, drain, converge = 1_000_000, 30, _converge()
    assert tick(start, start + converge, 0, False, drain) == "0"
    with pytest.raises(SystemExit, match=WINDOW_MSG):
        tick(start, start + converge + drain, 0, False, drain)
    with pytest.raises(SystemExit, match=WINDOW_MSG):
        tick(start, start + converge + drain, 0, True, drain)


def test_span_public_samples_now_after_public_probe() -> None:
    span = _script()
    body = span[span.index("span_public() {") : span.index('prove_release "$REPO_DIR"')]
    start_at = body.index("start=$(date +%s)")
    loop = body.index("while :; do")
    pub = body.index('hp public "$PUB"')
    now_at = body.index("now=$(date +%s)")
    tick = body.index("span-tick")
    assert start_at < loop < pub < now_at < tick
    assert body.count("now=$(date +%s)") == 1


def test_s1_resume_still_runs_full_span_before_local_unlink() -> None:
    script = _script()
    s1 = script.index('if [ "$PHASE" = "S1" ]; then')
    span = script.index("span_public 503 ready-maint", s1)
    local_vol = script.index('hp unlink "$VOL"', s1)
    assert "span-tick" in script[script.index("span_public() {") : s1]
    assert s1 < span < local_vol
    assert "unlink" not in script[s1:span]


def test_successor_control_adopts_exact_prior_s1_then_rewrites_current_before_unlink() -> None:
    ns = _ns()
    script = _script()
    helper = _helper_python()
    assert (
        ns["admit_phase"](_phase(PRIOR_CONTROL, "S1"), SCHEMA, BASELINE_SHA, FAILED_RUN_ID, CURRENT_CONTROL)
        == "ADOPT-S1"
    )
    assert (
        ns["admit_phase"](_phase(CURRENT_CONTROL, "S1"), SCHEMA, BASELINE_SHA, FAILED_RUN_ID, CURRENT_CONTROL) == "S1"
    )
    assert "ADOPT-S1" in script
    all_four = script[
        script.index('[ "$lv" -eq 1 ] && [ "$lp" -eq 1 ] && [ "$pv" -eq 1 ] && [ "$pp" -eq 1 ]') : script.index(
            "PHASE=S0"
        )
    ]
    assert "MODE=drain" in all_four
    assert "MODE=exact" in all_four
    assert "MODE=recent" not in all_four
    adopt = script.index('if [ "$SAVED_PHASE" = "ADOPT-S1" ]')
    phase_s0 = script.index("PHASE=S0", adopt)
    write_current = script.index(
        'hp write-phase "$PHASE_FILE" "$PHASE_SCHEMA" "$REQUIRED_SHA" "$REQUIRED_RUN_ID" "$REQUIRED_CONTROL_SHA" "$PHASE"',
        phase_s0,
    )
    first_unlink = script.index('peer_hp unlink "$VOL"', write_current)
    assert adopt < phase_s0 < write_current < first_unlink
    assert PRIOR_CONTROL in helper
    assert "REQUIRED_CONTROL_SHA" in script[write_current : write_current + 160]


def test_admit_phase_rejects_prior_s0_s2_and_other_controls() -> None:
    ns = _ns()
    with pytest.raises(SystemExit, match="phase authority is not bound to this recovery"):
        ns["admit_phase"](_phase(PRIOR_CONTROL, "S0"), SCHEMA, BASELINE_SHA, FAILED_RUN_ID, CURRENT_CONTROL)
    with pytest.raises(SystemExit, match="phase authority is not bound to this recovery"):
        ns["admit_phase"](_phase(PRIOR_CONTROL, "S2"), SCHEMA, BASELINE_SHA, FAILED_RUN_ID, CURRENT_CONTROL)
    with pytest.raises(SystemExit, match="phase authority is not bound to this recovery"):
        ns["admit_phase"](
            _phase("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "S1"),
            SCHEMA,
            BASELINE_SHA,
            FAILED_RUN_ID,
            CURRENT_CONTROL,
        )
    with pytest.raises(SystemExit, match="phase authority is not bound to this recovery"):
        ns["admit_phase"](_phase(PRIOR_CONTROL, "S1"), SCHEMA, BASELINE_SHA, "0", CURRENT_CONTROL)
