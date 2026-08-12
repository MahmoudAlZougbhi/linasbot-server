"""Verify Resend (Svix) webhook signatures without logging secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections.abc import Mapping


class WebhookSignatureError(ValueError):
    pass


def resend_webhook_secret() -> str:
    return (os.getenv("RESEND_WEBHOOK_SECRET") or "").strip()


def verify_resend_webhook(
    *,
    payload: bytes | str,
    headers: Mapping[str, str],
    secret: str | None = None,
    tolerance_seconds: int = 300,
) -> dict:
    """
    Verify Svix-signed Resend webhook.

    Expects headers: svix-id, svix-timestamp, svix-signature (v1,...).
    Returns parsed JSON object on success; raises WebhookSignatureError otherwise.
    """
    import json

    whsec = (secret if secret is not None else resend_webhook_secret()).strip()
    if not whsec:
        raise WebhookSignatureError("webhook_secret_missing")

    hdrs = {str(k).lower(): str(v) for k, v in headers.items()}
    msg_id = (hdrs.get("svix-id") or "").strip()
    timestamp = (hdrs.get("svix-timestamp") or "").strip()
    signature_header = (hdrs.get("svix-signature") or "").strip()
    if not msg_id or not timestamp or not signature_header:
        raise WebhookSignatureError("missing_svix_headers")

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise WebhookSignatureError("invalid_timestamp") from exc
    if abs(int(time.time()) - ts) > max(60, int(tolerance_seconds)):
        raise WebhookSignatureError("timestamp_out_of_tolerance")

    body = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
    signed_content = f"{msg_id}.{timestamp}.{body}".encode()

    raw_secret = whsec
    if raw_secret.startswith("whsec_"):
        raw_secret = raw_secret[len("whsec_") :]
    try:
        key = base64.b64decode(raw_secret)
    except Exception as exc:
        raise WebhookSignatureError("invalid_webhook_secret") from exc

    digest = hmac.new(key, signed_content, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")

    candidates: list[str] = []
    for part in signature_header.split(" "):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            version, value = part.split(",", 1)
            if version.strip() == "v1":
                candidates.append(value.strip())
        else:
            candidates.append(part)

    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise WebhookSignatureError("invalid_signature")

    try:
        data = json.loads(body)
    except Exception as exc:
        raise WebhookSignatureError("invalid_json") from exc
    if not isinstance(data, dict):
        raise WebhookSignatureError("invalid_payload")
    return data
