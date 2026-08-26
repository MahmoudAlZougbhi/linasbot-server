"""Safe redaction for WhatsApp Cloud diagnostics — never log tokens or full numbers."""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"EAA[A-Za-z0-9]+")
_LONG_DIGIT_RE = re.compile(r"(?<!\d)(\d{8,15})(?!\d)")


def redact_whatsapp_text(value: str) -> str:
    text = str(value or "")
    text = _TOKEN_RE.sub("[redacted-token]", text)
    text = _LONG_DIGIT_RE.sub(lambda match: f"***{match.group(1)[-4:]}", text)
    return text


def assert_payload_has_no_secrets(payload: Any) -> None:
    blob = str(payload)
    if "EAA" in blob:
        raise AssertionError("payload contains a token-like value")
    lowered = blob.lower()
    if "app_secret" in lowered and "present" not in lowered:
        # Presence booleans are allowed; raw secrets are not.
        if re.search(r"app_secret['\"]?\s*[:=]\s*['\"][^'\"]{8,}", lowered):
            raise AssertionError("payload appears to include an app secret")
