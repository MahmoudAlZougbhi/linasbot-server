"""Official TikTok-Signature verification (HMAC-SHA256 over timestamp.body)."""

from __future__ import annotations

import hashlib
import hmac
import time

from services.tiktok_business.config import WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS, require_tiktok_settings
from services.tiktok_business.errors import TikTokBusinessError


def parse_tiktok_signature_header(header: str) -> tuple[str, str]:
    timestamp = ""
    signature = ""
    for part in str(header or "").split(","):
        item = part.strip()
        if "=" not in item:
            continue
        prefix, value = item.split("=", 1)
        key = prefix.strip().lower()
        if key == "t":
            timestamp = value.strip()
        elif key == "s":
            signature = value.strip()
    if not timestamp or not signature:
        raise TikTokBusinessError("TikTok-Signature header is invalid", code="TIKTOK_SIGNATURE_INVALID", http_status=403)
    return timestamp, signature


def verify_tiktok_signature(*, raw_body: bytes, header: str, now: int | None = None) -> None:
    settings = require_tiktok_settings()
    timestamp, signature = parse_tiktok_signature_header(header)
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise TikTokBusinessError("TikTok-Signature timestamp is invalid", code="TIKTOK_SIGNATURE_INVALID", http_status=403) from exc
    current = int(now if now is not None else time.time())
    if abs(current - ts) > WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS:
        raise TikTokBusinessError("TikTok-Signature timestamp is stale", code="TIKTOK_SIGNATURE_STALE", http_status=403)
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(settings.client_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise TikTokBusinessError("TikTok-Signature mismatch", code="TIKTOK_SIGNATURE_INVALID", http_status=403)
