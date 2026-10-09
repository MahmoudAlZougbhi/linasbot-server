"""JSON logs for containers. The default text format stays unless this is enabled."""

from __future__ import annotations

import json
import logging
import os
from typing import Any


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "tenant_id": getattr(record, "tenant_id", ""),
            "request_id": getattr(record, "request_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
        }
        return json.dumps(payload, separators=(",", ":"))


def json_logs_enabled() -> bool:
    return (os.getenv("LINAS_LOG_FORMAT") or "").strip().lower() == "json"


def configure_json_logs() -> None:
    if not json_logs_enabled():
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
