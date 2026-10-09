"""Log when the host timezone is not UTC.

Customer-facing times stay in the tenant timezone. The host clock must be UTC.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_UTC_NAMES = frozenset({"utc", "etc/utc", "etc/universal", "zulu"})


def host_timezone_name() -> str:
    configured = (os.environ.get("TZ") or "").strip()
    if configured:
        return configured
    try:
        return Path("/etc/timezone").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def log_if_host_timezone_is_not_utc() -> str:
    name = host_timezone_name()
    if name.lower() not in _UTC_NAMES:
        logger.error("host_timezone_not_utc tz=%s", name or "unset")
    return name
