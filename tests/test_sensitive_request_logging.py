"""Regression coverage for secret-free request and application logs."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from services.sensitive_request_logging import (
    SensitiveQueryLogFilter,
    install_sensitive_query_log_filter,
    redact_sensitive_query_text,
)

ROOT = Path(__file__).resolve().parents[1]


def test_sensitive_query_values_are_redacted() -> None:
    marker = "do-not-store-this-verification-secret"
    source = f"/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token={marker}&access_token=another-secret&ok=yes"

    rendered = redact_sensitive_query_text(source)

    assert marker not in rendered
    assert "another-secret" not in rendered
    assert "hub.verify_token=[REDACTED]" in rendered
    assert "access_token=[REDACTED]" in rendered
    assert "ok=yes" in rendered


def test_application_log_filter_scrubs_format_arguments() -> None:
    marker = "unique-sensitive-log-marker"
    record = logging.LogRecord(
        "linasbot.test",
        logging.INFO,
        __file__,
        1,
        "request URL: %s",
        (f"/webhook/meta-messaging?hub.verify_token={marker}",),
        None,
    )

    assert SensitiveQueryLogFilter().filter(record) is True
    rendered = record.getMessage()
    assert marker not in rendered
    assert "hub.verify_token=[REDACTED]" in rendered


def test_record_factory_scrubs_handlers_created_after_install() -> None:
    marker = "late-handler-sensitive-marker"
    install_sensitive_query_log_filter()
    record = logging.getLogRecordFactory()(
        "third.party.late",
        logging.WARNING,
        __file__,
        1,
        "request=%s",
        (f"/callback?code={marker}",),
        None,
        None,
    )

    assert marker not in record.getMessage()
    assert "code=[REDACTED]" in record.getMessage()


@pytest.mark.asyncio
async def test_real_verification_handler_never_logs_token(monkeypatch, caplog, capsys) -> None:
    from modules import meta_messaging_webhook

    marker = "real-handler-secret-must-not-appear"
    query = urlencode(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": marker,
            "hub.challenge": "proof-challenge",
        }
    ).encode("ascii")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/webhook/meta-messaging",
            "query_string": query,
            "headers": [],
        }
    )
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(verify_token=marker),
    )
    caplog.set_level(logging.DEBUG)

    response = await meta_messaging_webhook.verify_meta_messaging_webhook(request)

    assert response.status_code == 200
    assert bytes(response.body) == b"proof-challenge"
    captured = capsys.readouterr()
    assert marker not in caplog.text
    assert marker not in captured.out
    assert marker not in captured.err


def test_uvicorn_access_log_is_fail_closed() -> None:
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    docker_source = (ROOT / "backend" / "Dockerfile.simple").read_text(encoding="utf-8")
    production_docker_source = (ROOT / "backend" / "Dockerfile.prod").read_text(encoding="utf-8")

    assert "access_log=False" in main_source
    assert "--no-access-log" in docker_source
    assert '"--access-logfile", "/dev/null"' in production_docker_source


def test_nginx_access_logs_never_include_query_or_header_surfaces() -> None:
    raw_log_config = (ROOT / "deploy" / "nginx-privacy-log.conf").read_text(encoding="utf-8")
    log_config = "\n".join(line for line in raw_log_config.splitlines() if not line.lstrip().startswith("#"))
    site_config = (ROOT / "deploy" / "nginx-linasaibot.conf").read_text(encoding="utf-8")
    include_config = (ROOT / "deploy" / "nginx-api-include.conf").read_text(encoding="utf-8")

    assert "$uri" in log_config
    for unsafe_variable in ("$request ", "$request_uri", "$args", "$query_string", "$http_"):
        assert unsafe_variable not in log_config
    assert "linasbot_safe" in site_config
    assert site_config.count("access_log off;") >= 2
    assert include_config.count("access_log off;") >= 2
    assert site_config.count("linasaibot-sensitive.error.log crit;") >= 2
    assert include_config.count("linasaibot-sensitive.error.log crit;") >= 2


def test_production_challenge_probe_keeps_tokens_out_of_process_arguments() -> None:
    source = (ROOT / "scripts" / "prod_verify_webhook_challenge.sh").read_text(encoding="utf-8")

    assert "urllib.parse.urlencode" in source
    assert "sensitive_probe_present_in_logs=false" in source
    assert "journalctl -u linasbot" in source
    assert "hub.verify_token=${" not in source
    assert "curl" not in source
