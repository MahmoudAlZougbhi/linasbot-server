"""Short-lived HMAC resource URLs for Web Chat cards. No private keys in payloads."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

from services.cm.article_media import load_media_bytes, load_media_meta
from services.cm.setup_resources import resolve_published_resource

TOKEN_TTL_SECONDS = 600


def _secret() -> bytes:
    raw = (os.getenv("DASHBOARD_AUTH_SECRET") or "").strip()
    if not raw:
        raise RuntimeError("DASHBOARD_AUTH_SECRET required for web chat resource URLs")
    return raw.encode("utf-8")


def mint_resource_card(
    *,
    tenant_id: str,
    resource_ref: str,
    title: str,
    description: str,
    resource_type: str,
    now: int | None = None,
) -> dict[str, str]:
    exp = int(now if now is not None else time.time()) + TOKEN_TTL_SECONDS
    body = f"{tenant_id}|{resource_ref}|{exp}"
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode("ascii").rstrip("=")
    return {
        "resource_ref": resource_ref,
        "type": resource_type,
        "title": title,
        "description": description,
        "url": f"/web-chat/resources/{token}",
    }


def verify_resource_token(token: str) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw:
        return {"ok": False, "error": "token_required"}
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + pad).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "error": "token_invalid"}
    parts = decoded.split("|")
    if len(parts) != 4:
        return {"ok": False, "error": "token_invalid"}
    tenant_id, resource_ref, exp_s, sig = parts
    body = f"{tenant_id}|{resource_ref}|{exp_s}"
    expected = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return {"ok": False, "error": "token_invalid"}
    try:
        exp = int(exp_s)
    except ValueError:
        return {"ok": False, "error": "token_invalid"}
    if exp < int(time.time()):
        return {"ok": False, "error": "token_expired"}
    return {"ok": True, "tenant_id": tenant_id, "resource_ref": resource_ref}


def load_verified_resource_bytes(token: str) -> dict[str, Any]:
    parsed = verify_resource_token(token)
    if not parsed.get("ok"):
        return parsed
    tenant_id = str(parsed["tenant_id"])
    ref = str(parsed["resource_ref"])
    hit = resolve_published_resource(tenant_id=tenant_id, resource_ref=ref)
    if not hit.get("ok"):
        return {"ok": False, "error": str(hit.get("error") or "resource_not_found")}
    record = dict(hit.get("resource") or {})
    if str(record.get("resource_type") or "") == "link":
        return {"ok": False, "error": "link_has_no_bytes"}
    media_id = str(record.get("storage_key") or ref)
    meta = load_media_meta(tenant_id=tenant_id, media_id=media_id)
    raw = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
    if not meta or raw is None:
        return {"ok": False, "error": "media_bytes_missing"}
    return {
        "ok": True,
        "bytes": raw,
        "mime": str(meta.get("mime") or "application/octet-stream"),
        "filename": str(meta.get("filename") or media_id),
    }


def cards_for_delivery(*, tenant_id: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        ref = str(item.get("resource_ref") or "").strip()
        if not ref:
            continue
        hit = resolve_published_resource(tenant_id=tenant_id, resource_ref=ref)
        if not hit.get("ok"):
            continue
        record = dict(hit.get("resource") or {})
        kind = str(record.get("resource_type") or "file")
        if kind == "link":
            url = str(record.get("external_url") or "").strip()
            if not url:
                continue
            out.append(
                {
                    "resource_ref": ref,
                    "type": "link",
                    "title": str(record.get("title") or ref),
                    "description": str(record.get("description") or ""),
                    "url": url,
                }
            )
            continue
        out.append(
            mint_resource_card(
                tenant_id=tenant_id,
                resource_ref=ref,
                title=str(record.get("title") or ref),
                description=str(record.get("description") or ""),
                resource_type=kind,
            )
        )
    blob = str(out)
    if "BEGIN " in blob or "PRIVATE KEY" in blob:
        raise RuntimeError("resource cards must not contain private keys")
    return out
