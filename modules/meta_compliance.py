"""Public compliance pages and Meta's authenticated data-deletion callback."""

from __future__ import annotations

import asyncio
import html
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from modules.api_security import _client_ip
from modules.core import app
from services.compliance_page_content import (
    data_deletion_body,
    privacy_policy_body,
    terms_of_service_body,
)
from services.meta_app_registry import (
    APP_A_EXPECTED_ID,
    APP_A_KEY,
    AuthFlow,
    MetaAppConfig,
    MetaRegistryError,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_data_deletion import (
    MetaDeletionStateError,
    MetaDeletionStoreUnavailableError,
    MetaSignedRequestError,
    delete_meta_social_user_data,
    read_deletion_status,
    verify_meta_deletion_signed_request,
)
from services.meta_instagram_login_config import (
    DEFAULT_INSTAGRAM_LOGIN_APP_ID,
    instagram_login_app_id,
    instagram_login_app_secret,
)
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionGuardError,
    acquire_meta_deauthorization_subject_guard,
    meta_deletion_subject_hmac,
)
from services.meta_surface_secret_separation import (
    environ_secret_values,
    evaluate_meta_surface_signing_separation,
)
from services.rate_limit_service import rate_limit_service

_CONTACT_EMAIL = "support@linasai.com"
_PUBLIC_BASE_URL = "https://www.linasaibot.com"
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
_CALLBACK_RATE_LIMIT = 120
_CALLBACK_RATE_WINDOW_SECONDS = 300
_STATUS_RATE_LIMIT = 30
_STATUS_RATE_WINDOW_SECONDS = 300


@dataclass(frozen=True)
class _MetaCallbackContext:
    app_key: str
    app_id: str
    app_secret: str
    auth_flow: AuthFlow


def _page(title: str, body: str, *, noindex: bool = False) -> HTMLResponse:
    robots = '<meta name="robots" content="noindex, nofollow">' if noindex else ""
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {robots}
  <title>{html.escape(title)} · Linas AI</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #fff7fb; color: #251a22; line-height: 1.65; }}
    main {{ width: min(860px, calc(100% - 40px)); margin: 48px auto; background: white;
      border: 1px solid #eadde5; border-radius: 18px; padding: clamp(24px, 5vw, 52px);
      box-shadow: 0 18px 50px rgba(72, 36, 59, .08); }}
    h1, h2 {{ line-height: 1.2; color: #6b234f; }}
    h1 {{ margin-top: 0; }} h2 {{ margin-top: 2rem; }}
    a {{ color: #8c2f68; }} .meta {{ color: #6f6069; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 32px; }}
    code {{ overflow-wrap: anywhere; }}
    .status-pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px;
      background: #f6e8f0; color: #6b234f; font-weight: 600; }}
  </style>
</head>
<body><main>
  <nav aria-label="Compliance pages">
    <a href="/">Home</a>
    <a href="/privacy-policy">Privacy Policy</a>
    <a href="/terms">Terms</a>
    <a href="/data-deletion">Data Deletion</a>
    <a href="/about">About</a>
    <a href="/contact">Contact</a>
  </nav>
  {body}
</main></body></html>"""
    return HTMLResponse(document, headers=_SECURITY_HEADERS)


def _status_url(confirmation_code: str) -> str:
    return f"{_PUBLIC_BASE_URL}/data-deletion/status/{confirmation_code}"


def _format_unix_date(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(int(timestamp), tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _enforce_rate_limit(request: Request, route: str, *, limit: int, window_seconds: int) -> None:
    ip = _client_ip(request)
    allowed, retry_after = rate_limit_service.hit(
        f"meta-compliance:{route}:{ip}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )


def _callback_health_response() -> JSONResponse:
    return JSONResponse({"status": "ok"}, headers=_SECURITY_HEADERS)


async def _extract_signed_request(request: Request) -> str:
    raw_body = await request.body()
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid request body") from exc
        return str(payload.get("signed_request") or "") if isinstance(payload, dict) else ""
    values = parse_qs(raw_body.decode("utf-8", errors="strict"), keep_blank_values=True)
    return str((values.get("signed_request") or [""])[0])


def _app_a_config() -> MetaAppConfig:
    config = get_meta_app_configs().get(APP_A_KEY)
    if config and config.enabled and config.app_secret:
        return config
    legacy_secret = (os.getenv("META_APP_SECRET") or "").strip()
    if legacy_secret:
        return MetaAppConfig(
            key=APP_A_KEY,
            app_id=(os.getenv("META_APP_ID") or os.getenv("META_APP_A_ID") or "legacy-app-a").strip(),
            app_secret=legacy_secret,
            verify_token="",
            graph_api_version=(os.getenv("META_GRAPH_API_VERSION") or "v24.0").strip(),
            classification="own_business",
            enabled=True,
        )
    raise MetaSignedRequestError("Meta App A is not configured")


def _app_a_callback_context() -> _MetaCallbackContext:
    config = _app_a_config()
    if config.app_id != APP_A_EXPECTED_ID:
        raise MetaSignedRequestError("Meta App A signing identity is unavailable")
    return _MetaCallbackContext(
        app_key=config.key,
        app_id=config.app_id,
        app_secret=config.app_secret,
        auth_flow="facebook_login",
    )


def _instagram_callback_context() -> _MetaCallbackContext:
    app_id = instagram_login_app_id()
    app_secret = instagram_login_app_secret()
    if app_id != DEFAULT_INSTAGRAM_LOGIN_APP_ID or not app_secret:
        raise MetaSignedRequestError("Instagram Login signing configuration is unavailable")
    return _MetaCallbackContext(
        app_key=APP_A_KEY,
        app_id=app_id,
        app_secret=app_secret,
        auth_flow="instagram_login",
    )


def _load_callback_context(*, instagram_login: bool) -> _MetaCallbackContext:
    try:
        if not evaluate_meta_surface_signing_separation(environ_secret_values()).ok:
            raise MetaSignedRequestError("Meta callback signing secrets must be distinct")
        return _instagram_callback_context() if instagram_login else _app_a_callback_context()
    except MetaSignedRequestError:
        raise HTTPException(status_code=503, detail="Meta callback is not configured") from None


async def _handle_meta_data_deletion(
    request: Request,
    *,
    context: _MetaCallbackContext,
) -> JSONResponse:
    _enforce_rate_limit(
        request,
        "data-deletion",
        limit=_CALLBACK_RATE_LIMIT,
        window_seconds=_CALLBACK_RATE_WINDOW_SECONDS,
    )
    try:
        signed_request = await _extract_signed_request(request)
        if not signed_request.strip():
            raise MetaSignedRequestError("Missing signed request")
        verified = verify_meta_deletion_signed_request(signed_request, context.app_secret)
    except (MetaSignedRequestError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid signed deletion request") from None

    try:
        result = await asyncio.to_thread(
            delete_meta_social_user_data,
            verified.meta_user_id,
            context.app_secret,
            app_key=context.app_key,
            signing_app_id=context.app_id,
            auth_flow=context.auth_flow,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Data deletion could not be completed") from None

    return JSONResponse(
        {
            "url": _status_url(result.confirmation_code),
            "confirmation_code": result.confirmation_code,
        },
        headers=_SECURITY_HEADERS,
    )


async def _handle_meta_deauthorization(
    request: Request,
    *,
    context: _MetaCallbackContext,
) -> JSONResponse:
    _enforce_rate_limit(
        request,
        "deauthorize",
        limit=_CALLBACK_RATE_LIMIT,
        window_seconds=_CALLBACK_RATE_WINDOW_SECONDS,
    )
    try:
        signed_request = await _extract_signed_request(request)
        if not signed_request.strip():
            raise MetaSignedRequestError("Missing signed request")
        verified = verify_meta_deletion_signed_request(signed_request, context.app_secret)
    except (MetaSignedRequestError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid signed deauthorization request") from None

    def _revoke_after_tombstone() -> None:
        subject_key = meta_deletion_subject_hmac(
            app_key=context.app_key,
            app_id=context.app_id,
            auth_flow=context.auth_flow,
            meta_user_id=verified.meta_user_id,
            app_secret=context.app_secret,
        )
        with acquire_meta_deauthorization_subject_guard(subject_key) as guard:
            guard.record_deauthorization(deauthorized_at=float(verified.issued_at))
            get_meta_app_registry().revoke_authorization(
                app_key=context.app_key,
                auth_flow=context.auth_flow,
                authorized_meta_user_id=verified.meta_user_id,
                authorized_before=float(verified.issued_at),
            )

    try:
        await asyncio.to_thread(_revoke_after_tombstone)
    except (MetaRegistryError, MetaSubjectDeletionGuardError):
        raise HTTPException(status_code=503, detail="Meta deauthorization could not be completed") from None
    return JSONResponse({"success": True}, headers=_SECURITY_HEADERS)


@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    return _page(
        "Privacy Policy",
        privacy_policy_body(contact_email=_CONTACT_EMAIL, public_base_url=_PUBLIC_BASE_URL),
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service() -> HTMLResponse:
    return _page(
        "Terms of Service",
        terms_of_service_body(contact_email=_CONTACT_EMAIL, public_base_url=_PUBLIC_BASE_URL),
    )


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion_page() -> HTMLResponse:
    return _page(
        "User Data Deletion",
        data_deletion_body(contact_email=_CONTACT_EMAIL, public_base_url=_PUBLIC_BASE_URL),
    )


@app.get("/data-deletion/status/{confirmation_code}", response_class=HTMLResponse)
async def data_deletion_status_page(confirmation_code: str, request: Request) -> HTMLResponse:
    _enforce_rate_limit(
        request,
        "status",
        limit=_STATUS_RATE_LIMIT,
        window_seconds=_STATUS_RATE_WINDOW_SECONDS,
    )
    try:
        status = read_deletion_status(confirmation_code)
    except (MetaDeletionStateError, MetaDeletionStoreUnavailableError):
        raise HTTPException(status_code=503, detail="Deletion status is temporarily unavailable") from None
    safe_code = html.escape(str(confirmation_code or "").strip())
    if status is None:
        body = f"""
<h1>Deletion Request Status</h1>
<p class="meta">Confirmation code: <code>{safe_code}</code></p>
<p>We could not find a deletion request for this confirmation code. Check the link returned by
Meta or contact <a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a> if you need help.</p>
"""
        return _page("Deletion Request Status", body, noindex=True)

    status_value = str(status.get("status") or "pending")
    requested_at = _format_unix_date(status.get("requested_at"))
    completed_at = _format_unix_date(status.get("completed_at"))
    status_messages = {
        "received": "Your authenticated Meta deletion request was received and is being processed.",
        "pending": "Your authenticated Meta deletion request is being processed.",
        "completed": "Your authenticated Meta deletion request is complete.",
        "no_data": "Your authenticated Meta deletion request is complete. No matching social-bot records were found.",
        "failed": "We could not complete this deletion request automatically. Please contact support.",
    }
    message = status_messages.get(status_value, status_messages["pending"])
    timeline = ""
    if requested_at:
        timeline += f'<p class="meta">Request received: {html.escape(requested_at)}</p>'
    if completed_at:
        timeline += f'<p class="meta">Last updated: {html.escape(completed_at)}</p>'
    support = ""
    if status_value == "failed":
        support = f'<p>If this problem continues, email <a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a>.</p>'
    body = f"""
<h1>Deletion Request Status</h1>
<p class="meta">Confirmation code: <code>{safe_code}</code></p>
<p><span class="status-pill">{html.escape(status_value)}</span></p>
<p>{message}</p>
{timeline}
{support}
<p><a href="/data-deletion">Back to Data Deletion instructions</a></p>
"""
    return _page("Deletion Request Status", body, noindex=True)


@app.post("/oauth/meta/data-deletion", response_class=JSONResponse)
async def meta_oauth_data_deletion_callback(request: Request) -> JSONResponse:
    return await _handle_meta_data_deletion(
        request,
        context=_load_callback_context(instagram_login=False),
    )


@app.get("/oauth/meta/data-deletion", response_class=JSONResponse)
@app.head("/oauth/meta/data-deletion", response_class=JSONResponse)
async def meta_oauth_data_deletion_health() -> JSONResponse:
    return _callback_health_response()


@app.post("/data-deletion", response_class=JSONResponse)
async def meta_data_deletion_callback_legacy(request: Request) -> JSONResponse:
    return await _handle_meta_data_deletion(
        request,
        context=_load_callback_context(instagram_login=False),
    )


@app.post("/oauth/instagram/data-deletion", response_class=JSONResponse)
async def instagram_oauth_data_deletion_callback(request: Request) -> JSONResponse:
    return await _handle_meta_data_deletion(
        request,
        context=_load_callback_context(instagram_login=True),
    )


@app.get("/oauth/instagram/data-deletion", response_class=JSONResponse)
@app.head("/oauth/instagram/data-deletion", response_class=JSONResponse)
async def instagram_oauth_data_deletion_health() -> JSONResponse:
    return _callback_health_response()


@app.post("/oauth/meta/deauthorize", response_class=JSONResponse)
async def meta_oauth_deauthorization_callback(request: Request) -> JSONResponse:
    return await _handle_meta_deauthorization(
        request,
        context=_load_callback_context(instagram_login=False),
    )


@app.get("/oauth/meta/deauthorize", response_class=JSONResponse)
@app.head("/oauth/meta/deauthorize", response_class=JSONResponse)
async def meta_oauth_deauthorization_health() -> JSONResponse:
    return _callback_health_response()


@app.post("/meta/deauthorize", response_class=JSONResponse)
async def meta_deauthorization_callback_legacy(request: Request) -> JSONResponse:
    return await _handle_meta_deauthorization(
        request,
        context=_load_callback_context(instagram_login=False),
    )


@app.post("/oauth/instagram/deauthorize", response_class=JSONResponse)
async def instagram_oauth_deauthorization_callback(request: Request) -> JSONResponse:
    return await _handle_meta_deauthorization(
        request,
        context=_load_callback_context(instagram_login=True),
    )


@app.get("/oauth/instagram/deauthorize", response_class=JSONResponse)
@app.head("/oauth/instagram/deauthorize", response_class=JSONResponse)
async def instagram_oauth_deauthorization_health() -> JSONResponse:
    return _callback_health_response()
