"""Public TikTok OAuth callback — tenant comes only from signed one-time state."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from modules.core import app
from services.tiktok_business.errors import TikTokBusinessError
from services.tiktok_business.oauth import complete_tiktok_oauth


@app.get("/oauth/tiktok/callback")
async def tiktok_oauth_callback(request: Request) -> Any:
    params = request.query_params
    # Never read tenant_id from the query string.
    state = params.get("state") or ""
    code = params.get("code") or params.get("auth_code")
    error = params.get("error")
    error_description = params.get("error_description")
    try:
        result = await complete_tiktok_oauth(
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )
        return RedirectResponse(url=str(result["redirect_url"]), status_code=303)
    except TikTokBusinessError as exc:
        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='robots' content='noindex,nofollow'>"
            "<title>Return to Linas AI</title></head><body>"
            "<h1>You can return to Linas AI</h1>"
            "<p>TikTok connection did not complete. Open the Linas AI app and try again from Integrations.</p>"
            f"<p>Reference: {exc.code}</p>"
            "</body></html>"
        )
        return HTMLResponse(content=html, status_code=400, headers={"X-Robots-Tag": "noindex, nofollow"})
