"""Render branded HTML + plain-text transactional emails."""

from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import urlparse

from services.email_templates_catalog import get_template_copy, normalize_locale

BRAND_NAME = "Linas AI"
BRAND_PRIMARY = "#0F766E"
BRAND_BG = "#F8FAFC"
BRAND_CARD = "#FFFFFF"
BRAND_TEXT = "#0F172A"
BRAND_MUTED = "#64748B"
SUPPORT_EMAIL = "support@linasaibot.com"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str
    locale: str
    template_id: str


def _safe_https_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        return None
    host = (parsed.hostname or "").lower()
    if host not in {"linasaibot.com", "www.linasaibot.com"}:
        return None
    return raw


def render_transactional_email(
    *,
    template_id: str,
    action_url: str | None = None,
    locale: str | None = None,
    extra_lines: list[str] | None = None,
) -> RenderedEmail:
    loc = normalize_locale(locale)
    copy = get_template_copy(template_id, loc)
    subject = str(copy["subject"])
    heading = str(copy["heading"])
    preview = str(copy.get("preview") or "")
    body_lines = [str(x) for x in (copy.get("body_lines") or [])]
    if extra_lines:
        body_lines.extend(str(x) for x in extra_lines if str(x).strip())
    cta_label = str(copy.get("cta_label") or "Continue")
    footer_note = str(copy.get("footer_note") or "")
    safe_url = _safe_https_url(action_url or "")

    # Plain text
    text_parts = [heading, ""]
    text_parts.extend(body_lines)
    if safe_url:
        text_parts.extend(["", f"{cta_label}: {safe_url}"])
    if footer_note:
        text_parts.extend(["", footer_note])
    text_parts.extend(["", f"— {BRAND_NAME}", f"Support: {SUPPORT_EMAIL}"])
    text_body = "\n".join(text_parts)

    # HTML
    dir_attr = 'dir="rtl"' if loc == "ar" else 'dir="ltr"'
    lines_html = "".join(
        f'<p style="margin:0 0 12px;color:{BRAND_TEXT};font-size:15px;line-height:1.55;">{html.escape(line)}</p>'
        for line in body_lines
    )
    cta_html = ""
    if safe_url:
        cta_html = (
            f'<p style="margin:24px 0 8px;">'
            f'<a href="{html.escape(safe_url, quote=True)}" '
            f'style="display:inline-block;background:{BRAND_PRIMARY};color:#fff;'
            f'text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:600;">'
            f"{html.escape(cta_label)}</a></p>"
            f'<p style="margin:0;color:{BRAND_MUTED};font-size:12px;word-break:break-all;">'
            f"{html.escape(safe_url)}</p>"
        )
    html_body = f"""<!DOCTYPE html>
<html {dir_attr} lang="{html.escape(loc)}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)}</title>
<!--[if !mso]><!--><meta name="color-scheme" content="light dark"><!--<![endif]-->
</head>
<body style="margin:0;padding:0;background:{BRAND_BG};">
<span style="display:none!important;visibility:hidden;opacity:0;color:transparent;height:0;width:0;overflow:hidden;">{html.escape(preview)}</span>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{BRAND_BG};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" style="max-width:560px;background:{BRAND_CARD};border-radius:12px;padding:28px 24px;border:1px solid #E2E8F0;">
<tr><td style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<p style="margin:0 0 4px;color:{BRAND_PRIMARY};font-size:13px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">{html.escape(BRAND_NAME)}</p>
<h1 style="margin:0 0 16px;color:{BRAND_TEXT};font-size:22px;line-height:1.3;">{html.escape(heading)}</h1>
{lines_html}
{cta_html}
<hr style="border:none;border-top:1px solid #E2E8F0;margin:24px 0;">
<p style="margin:0;color:{BRAND_MUTED};font-size:12px;line-height:1.5;">{html.escape(footer_note)}</p>
<p style="margin:12px 0 0;color:{BRAND_MUTED};font-size:12px;">Support: <a href="mailto:{SUPPORT_EMAIL}" style="color:{BRAND_PRIMARY};">{SUPPORT_EMAIL}</a></p>
</td></tr></table>
</td></tr></table>
</body></html>"""

    return RenderedEmail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        locale=loc,
        template_id=template_id,
    )
