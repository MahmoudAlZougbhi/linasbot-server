"""CM Setup Chat progress — mobile readiness + Owner Copilot handoff."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from services.cm.progress import progress_summary
from services.cm.setup_chat import INTRO_MESSAGE
from services.dashboard_session_service import SessionRecord


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


@app.get("/api/cm/setup-chat/progress")
async def cm_setup_chat_progress(request: Request) -> Any:
    """Read-only CM fill progress for mobile readiness + Owner Copilot handoff."""
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
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
            "weak_sections": summary["weak_sections"],
            "filled_sections": summary["filled_sections"],
            "remaining_sections": summary["remaining_sections"],
            "done_sections": summary["done_sections"],
            "fill_missing_prompt": summary["fill_missing_prompt"],
        },
    }
