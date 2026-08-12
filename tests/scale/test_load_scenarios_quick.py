"""CI-friendly quick load scenarios (mocked providers / fakeredis)."""

from __future__ import annotations

from scripts.loadtest.run_scale_scenarios import (
    scenario_a_mobile,
    scenario_b_ingress,
    scenario_c_100k,
    scenario_d_provider_slowdown,
    scenario_e_node_failure,
)


def test_scenario_a_quick():
    r = scenario_a_mobile(100)
    assert r.passed, r


def test_scenario_b_ingress():
    r = scenario_b_ingress(events=200, conversations=20)
    assert r.passed, r


def test_scenario_c_burst():
    r = scenario_c_100k(conversations=1000, burst=500)
    assert r.passed, r


def test_scenario_d_backpressure():
    r = scenario_d_provider_slowdown()
    assert r.passed, r


def test_scenario_e_drain():
    r = scenario_e_node_failure()
    assert r.passed, r
