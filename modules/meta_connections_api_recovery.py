"""Meta connection recovery routes: webhook retry and honest reconnect refusal."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from modules.meta_connections_api_helpers import _tenant_binding
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_webhook_subscription
from services.meta_oauth import MetaOAuthError


@app.post("/api/meta/connections/{binding_id}/instagram-login/retry-webhook")
async def retry_instagram_login_webhook_setup(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.auth_flow != "instagram_login":
        raise HTTPException(status_code=409, detail="Webhook retry applies only to Instagram Login connections")
    from services.membership.edit_http import guarded_edit

    try:
        with guarded_edit(
            tenant_id=session.tenant_id,
            kind="safety:webhook",
            payload={"binding_id": binding_id, "action": "retry_instagram_login_webhook"},
            safety=True,
        ):
            state = await retry_instagram_login_webhook_subscription(
                binding.binding_id,
                actor_id=session.user_id or session.email,
            )
    except MetaOAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    refreshed = _tenant_binding(binding_id, session.tenant_id)
    public = refreshed.public_dict()
    public["webhook_subscription"] = state.public_dict()
    return {
        "success": state.ready_for_dm,
        "connection": public,
        "webhook_subscription": state.public_dict(),
    }


@app.post("/api/meta/connections/{binding_id}/reconnect")
async def reconnect_meta_connection(binding_id: str, request: Request) -> Any:
    """Reconnect requires a fresh OAuth authorization — token reuse is not supported."""

    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.status not in {"disconnected", "inactive"}:
        raise HTTPException(status_code=409, detail="Connection is already active or cannot be reconnected here")
    channel = str(binding.channel or "").strip().lower()
    if binding.auth_flow == "instagram_login" or channel == "instagram":
        raise HTTPException(
            status_code=409,
            detail="Disconnect Instagram, then use Connect Instagram to authorize again.",
        )
    raise HTTPException(
        status_code=409,
        detail="Disconnect this channel, then use Connect to run a fresh Meta authorization.",
    )
