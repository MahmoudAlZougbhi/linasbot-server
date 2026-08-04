"""Public compliance pages and Meta's authenticated data-deletion callback."""

from __future__ import annotations

import asyncio
import html
import os
from urllib.parse import parse_qs

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from modules.core import app
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAppConfig,
    MetaRegistryError,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_data_deletion import (
    MetaSignedRequestError,
    VerifiedMetaDeletionRequest,
    delete_meta_social_user_data,
    read_deletion_status,
    verify_meta_deletion_signed_request,
)

_CONTACT_EMAIL = "Mahmoudalzougbhi@gmail.com"
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


def _page(title: str, body: str) -> HTMLResponse:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · Lina's Laser Clinics</title>
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
  </style>
</head>
<body><main>
  <nav aria-label="Compliance pages">
    <a href="/privacy-policy">Privacy Policy</a>
    <a href="/terms">Terms</a>
    <a href="/data-deletion">Data Deletion</a>
  </nav>
  {body}
</main></body></html>"""
    return HTMLResponse(document, headers=_SECURITY_HEADERS)


@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    return _page(
        "Privacy Policy",
        f"""
<h1>Privacy Policy</h1>
<p class="meta">Effective 2 August 2026</p>
<p>Lina's Laser Clinics uses Linas AI to answer Facebook Messenger and Instagram direct
messages that a person voluntarily sends to the official Lina's Laser Clinics Facebook Page
or linked Instagram professional account. Linas AI also provides an optional business-messaging
platform through which an independent business can explicitly connect its own Facebook Page and
linked professional Instagram account using Meta Business Login.</p>

<h2>Data we receive</h2>
<p>Meta may send us a platform-scoped sender identifier, the destination Page or Instagram
account identifier, message text, message and timestamp identifiers, postback selections, and
attachment notifications or metadata. The current social bot does not fetch attachment files;
it asks the sender to describe what help they need in text.</p>

<h2>How we use it</h2>
<p>We use this information only to authenticate and deduplicate the webhook, bind the message
to the business and assets that authorized the connection, preserve tenant-isolated conversation
context, answer that business's configured service questions, maintain service security, and
provide an explicit booking or human-support handoff when requested. We do not process public comments,
publish content, run ads, send unsolicited marketing DMs, or book an appointment inside
Facebook or Instagram.</p>

<h2>Service providers</h2>
<p>Meta delivers and sends the messages. OpenAI processes message text and relevant
conversation context to generate an answer. Google Cloud/Firebase stores operational
conversation records, and DigitalOcean hosts the application. These providers process data
under their applicable contracts, security controls, and privacy terms.</p>

<h2>Storage, retention, and security</h2>
<p>Conversation records can include tenant and asset bindings, platform-scoped identifiers,
message text, AI replies, timestamps, language, and routing state. OAuth credentials and Page
tokens are encrypted server-side and are never entered or displayed to normal dashboard users.
Operational logs may contain pseudonymous identifiers,
status codes, and errors. The service does not currently apply a fixed automatic deletion date
to conversation records; they remain while needed for continuity, security, troubleshooting,
and the clinic's legitimate service records, unless a valid deletion request is completed or
the records are no longer needed. Access is restricted; data is transmitted over HTTPS; Meta
webhook bodies require HMAC signature validation; and production credentials are kept outside
the source repository.</p>

<h2>WhatsApp handoff</h2>
<p>WhatsApp is only an outbound booking or human-agent destination. When a sender explicitly
asks to book or reach a person, the bot may ask for the minimum branch and gender information
needed to provide the correct public <code>https://wa.me/...</code> link. WhatsApp inbound
messages do not enter this AI from this integration, and no Facebook or Instagram appointment
is created in the clinic CRM.</p>

<h2>Sharing and choices</h2>
<p>We do not sell social-message data or use it for third-party advertising. A person can stop
messaging at any time and can request access, correction, or deletion by following our
<a href="/data-deletion">Data Deletion instructions</a> or emailing
<a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a>. We may ask for enough information to
verify the relevant Facebook or Instagram conversation before acting.</p>

<h2>Contact</h2>
<p>Questions about this policy can be sent to
<a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a>.</p>
""",
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service() -> HTMLResponse:
    return _page(
        "Terms of Service",
        f"""
<h1>Terms of Service</h1>
<p class="meta">Effective 2 August 2026</p>
<p>These terms cover Linas AI replies available through the official Lina's Laser Clinics
Facebook Messenger and Instagram direct-message accounts and, where enabled, through independent
business accounts that the business owner connects to Linas AI using Meta Business Login.</p>

<h2>Permitted use</h2>
<p>You may voluntarily message the clinic to ask about services, prices, preparation, branches,
and policies. Do not use the service unlawfully, attempt to bypass security, or send content
that infringes another person's rights.</p>

<h2>Automated information</h2>
<p>Replies are generated automatically and may be incomplete. They are general clinic
information, not medical diagnosis, emergency care, or a substitute for advice from a qualified
health professional. Confirm important treatment, eligibility, pricing, and preparation details
with clinic staff.</p>

<h2>Appointments and human contact</h2>
<p>The social bot does not create, edit, reschedule, cancel, or confirm appointments inside
Facebook, Instagram, or the clinic CRM. When you explicitly request booking or a person, it
provides the appropriate public WhatsApp contact and link after collecting only required routing
information. An appointment exists only after clinic staff confirm it through the applicable
booking process.</p>

<h2>Messaging limits</h2>
<p>The bot responds to customer-initiated direct messages within Meta's permitted messaging
window. It does not process comments or send unsolicited marketing messages. Availability may
be interrupted for maintenance, platform limits, or security reasons.</p>

<h2>Privacy and changes</h2>
<p>Use of the service is also governed by our <a href="/privacy-policy">Privacy Policy</a>.
We may update these terms when the service or legal requirements change. Questions may be sent
to <a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a>.</p>
""",
    )


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion_page(confirmation_code: str = "") -> HTMLResponse:
    status = read_deletion_status(confirmation_code)
    status_html = ""
    if confirmation_code:
        if status and status.get("status") == "completed":
            status_html = (
                "<h2>Automated request status</h2>"
                "<p>Your authenticated Meta deletion request is complete. The matching "
                "Facebook/Instagram social-bot records were removed.</p>"
            )
        else:
            status_html = (
                "<h2>Automated request status</h2>"
                "<p>No completed request was found for that confirmation code. Check the link "
                "returned by Meta or contact us.</p>"
            )
    return _page(
        "User Data Deletion",
        f"""
<h1>User Data Deletion</h1>
<p>You may request deletion of information associated with your Facebook Messenger or Instagram
DM interaction with the Linas AI social bot.</p>
{status_html}
<h2>Request through Meta</h2>
<p>Remove the app or request deletion through the applicable Facebook or Instagram app settings.
Meta sends our server an authenticated, signed deletion request. Valid requests remove the
namespaced Facebook/Instagram user record, its stored conversations, and matching social chat
index entries. Invalid signatures are rejected.</p>

<h2>Request by email</h2>
<p>Email <a href="mailto:{_CONTACT_EMAIL}?subject=Social%20message%20data%20deletion">
{_CONTACT_EMAIL}</a> with the subject “Social message data deletion”. State whether the request
concerns Facebook Messenger or Instagram and provide the public account handle used to contact
the clinic. Do not send a password, access token, 2FA code, government ID, or unrelated medical
information. We may reply with a minimal verification step so we delete the correct record.</p>

<h2>What deletion covers</h2>
<p>Deletion covers the social bot's platform-scoped identifier, stored DM text and AI replies,
conversation state, timestamps, and matching social-chat index entries under our control. It
does not delete records held independently by Meta, OpenAI, or another provider under its own
legal obligations, nor records the clinic must retain to meet a legal obligation. We will explain
any narrow exception that applies to a manual request.</p>
""",
    )


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


def _verify_deletion_app(
    signed_request: str,
) -> tuple[MetaAppConfig, VerifiedMetaDeletionRequest]:
    candidates = [config for config in get_meta_app_configs().values() if config.enabled]
    if not candidates:
        legacy_secret = (os.getenv("META_APP_SECRET") or "").strip()
        if legacy_secret:
            candidates = [
                MetaAppConfig(
                    key=APP_A_KEY,
                    app_id=(os.getenv("META_APP_ID") or "legacy-app-a").strip(),
                    app_secret=legacy_secret,
                    verify_token="",
                    graph_api_version=(os.getenv("META_GRAPH_API_VERSION") or "v24.0").strip(),
                    classification="own_business",
                    enabled=True,
                )
            ]
    matches: list[tuple[MetaAppConfig, VerifiedMetaDeletionRequest]] = []
    for config in candidates:
        try:
            matches.append((config, verify_meta_deletion_signed_request(signed_request, config.app_secret)))
        except MetaSignedRequestError:
            continue
    if len(matches) != 1:
        raise MetaSignedRequestError("Invalid signed deletion request")
    return matches[0]


@app.post("/data-deletion", response_class=JSONResponse)
async def meta_data_deletion_callback(request: Request) -> JSONResponse:
    try:
        signed_request = await _extract_signed_request(request)
        matched_app, verified = _verify_deletion_app(signed_request)
    except (MetaSignedRequestError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid signed deletion request") from None

    try:
        result = await asyncio.to_thread(
            delete_meta_social_user_data,
            verified.meta_user_id,
            matched_app.app_secret,
            app_key=matched_app.key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Data deletion could not be completed") from None

    status_url = f"{_PUBLIC_BASE_URL}/data-deletion?confirmation_code={result.confirmation_code}"
    return JSONResponse(
        {"url": status_url, "confirmation_code": result.confirmation_code},
        headers=_SECURITY_HEADERS,
    )


@app.post("/meta/deauthorize", response_class=JSONResponse)
async def meta_deauthorization_callback(request: Request) -> JSONResponse:
    """Authenticate Meta deauthorization and revoke only matching App B tokens."""

    try:
        signed_request = await _extract_signed_request(request)
        matched_app, verified = _verify_deletion_app(signed_request)
    except (MetaSignedRequestError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid signed deauthorization request") from None

    if matched_app.key == APP_B_KEY:
        try:
            get_meta_app_registry().revoke_authorization(
                app_key=matched_app.key,
                authorized_meta_user_id=verified.meta_user_id,
            )
        except MetaRegistryError:
            raise HTTPException(status_code=503, detail="Meta deauthorization could not be completed") from None
    return JSONResponse({"success": True}, headers=_SECURITY_HEADERS)
