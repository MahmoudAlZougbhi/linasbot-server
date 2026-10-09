from __future__ import annotations

import logging

from utils.host_timezone import log_if_host_timezone_is_not_utc


def test_utc_host_is_quiet(monkeypatch, caplog) -> None:
    monkeypatch.setenv("TZ", "UTC")
    with caplog.at_level(logging.ERROR):
        assert log_if_host_timezone_is_not_utc() == "UTC"
    assert caplog.records == []


def test_non_utc_host_logs(monkeypatch, caplog) -> None:
    monkeypatch.setenv("TZ", "Asia/Beirut")
    with caplog.at_level(logging.ERROR):
        assert log_if_host_timezone_is_not_utc() == "Asia/Beirut"
    assert "host_timezone_not_utc" in caplog.text
