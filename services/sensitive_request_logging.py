"""Fail-closed redaction for sensitive values that appear in query strings.

Production HTTP access logs intentionally record paths but never query strings.
This filter is an additional application-log guardrail for code that might log a
URL or query string in the future.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)(?P<prefix>^|[?&;\s])(?P<key>(?:hub\.verify_token|access_token|api[_-]?key|"
    r"app_secret|client_secret|code|state|password|refresh_token|"
    r"signature|signed_request|token))=(?P<value>[^&\s\"']*)"
)


def redact_sensitive_query_text(value: str) -> str:
    """Return log-safe text with sensitive query values removed."""

    return _SENSITIVE_QUERY_VALUE.sub(r"\g<prefix>\g<key>=[REDACTED]", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_query_text(value)
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


class SensitiveQueryLogFilter(logging.Filter):
    """Scrub sensitive query values before a record reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        record.args = _redact_value(record.args)
        return True


_FILTER = SensitiveQueryLogFilter()
_RECORD_FACTORY_INSTALLED = False


def install_sensitive_query_log_filter() -> None:
    """Install the shared scrubber on application and server loggers/handlers."""

    global _RECORD_FACTORY_INSTALLED

    # Logger filters do not run on ancestor loggers for propagated records, and
    # Uvicorn can create handlers after application imports. A process-wide
    # record factory scrubs before any current or future handler can persist it.
    if not _RECORD_FACTORY_INSTALLED:
        original_factory = logging.getLogRecordFactory()

        def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = original_factory(*args, **kwargs)
            _FILTER.filter(record)
            return record

        logging.setLogRecordFactory(redacting_factory)
        _RECORD_FACTORY_INSTALLED = True

    logger_names = (
        "",
        "linasbot",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "starlette",
    )
    for logger_name in logger_names:
        logger = logging.getLogger(logger_name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
        for handler in logger.handlers:
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)
