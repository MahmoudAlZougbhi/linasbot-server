"""Backoff for database/Redis outages must not spin."""

from __future__ import annotations

from services.scale.retry_backoff import retry_delay_seconds


def test_infra_errors_have_a_floor() -> None:
    delay = retry_delay_seconds(attempts=1, error="OperationalError: server closed the connection")
    assert delay >= 5.0
    assert delay <= 30.0


def test_ordinary_errors_use_exponential() -> None:
    delay = retry_delay_seconds(attempts=3, error="ValueError: bad payload")
    assert delay == 8.0
