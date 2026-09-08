"""Safe structured diagnostics for Meta webhook HMAC checks.

Never log app secrets, access tokens, or the full signature digest.
"""

from __future__ import annotations

import logging
from typing import Any

_runtime_logger = logging.getLogger("uvicorn.error")


def signature_header_meta(signature_header: str | None) -> dict[str, Any]:
    raw = str(signature_header or "").strip()
    if not raw:
        return {"signature_present": False, "signature_algorithm": "missing"}
    algorithm = raw.split("=", 1)[0].strip().lower() or "other"
    return {"signature_present": True, "signature_algorithm": algorithm}


def log_webhook_signature_result(
    *,
    endpoint: str,
    selector: str,
    configured_app: str,
    ok: bool,
    reason: str,
    signature_header: str | None,
) -> None:
    meta = signature_header_meta(signature_header)
    _runtime_logger.info(
        "[meta-webhook-sig] endpoint=%s selector=%s configured_app=%s result=%s reason=%s "
        "signature_present=%s algorithm=%s",
        endpoint,
        selector,
        configured_app,
        "pass" if ok else "fail",
        reason,
        meta["signature_present"],
        meta["signature_algorithm"],
    )
