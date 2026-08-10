"""CM Setup Chat API — same draft SoT as manual Content Managers forms."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_permission
from modules.core import app
from services.cm.progress import progress_summary
from services.cm.setup_chat import INTRO_MESSAGE, interpret_and_patch, start_setup
from services.dashboard_session_service import SessionRecord
from services.token_wallet_service import InsufficientTokenBalance


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


class SetupChatMessageBody(BaseModel):
    message: str = Field(default="", max_length=8000)
    section: str | None = None
    use_llm: bool = True


@app.get("/api/cm/setup-chat/start")
async def cm_setup_chat_start(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    data = start_setup(tenant_id, session.user_id or session.email)
    return {"success": True, "tenant_id": tenant_id, **data}


@app.get("/api/cm/setup-chat/progress")
async def cm_setup_chat_progress(request: Request) -> Any:
    """Read-only CM fill progress for mobile readiness + Owner Copilot handoff."""
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    # Do not materialize empty drafts on a progress read.
    summary = progress_summary(tenant_id, create_missing=False)
    return {
        "success": True,
        "tenant_id": tenant_id,
        "intro": INTRO_MESSAGE,
        "progress": summary["sections"],
        "summary": {
            "complete": summary["complete"],
            "incomplete": summary["incomplete"],
            "total": summary["total"],
            "percent": summary["percent"],
            "published": summary["published"],
            "missing_sections": summary["missing_sections"],
        },
    }


@app.post("/api/cm/setup-chat/message")
async def cm_setup_chat_message(request: Request, body: SetupChatMessageBody = Body(...)) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    try:
        result = await interpret_and_patch(
            tenant_id=tenant_id,
            user_id=session.user_id or session.email,
            message=body.message,
            actor_id=session.user_id or session.email,
            section=body.section,
            use_llm=bool(body.use_llm),
        )
    except InsufficientTokenBalance as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "tenant_id": tenant_id, **result}
