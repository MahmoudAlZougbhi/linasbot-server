"""Content Management FAQ bridge API (plan Phase 3 — CM is canonical FAQ writer)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from services.cm.faq_integration import FaqIntegrationError, create_faq_pair, list_cm_faq


@app.get("/api/cm/faq")
async def cm_list_faq(request: Request) -> Any:
    require_permission(request, "contentManagers")
    items = list_cm_faq()
    return {"success": True, "data": items, "count": len(items)}


@app.post("/api/cm/faq")
async def cm_create_faq(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    question = str(body.get("question") or "").strip()
    answer = str(body.get("answer") or "").strip()
    language = str(body.get("language") or "ar")
    raw_tags = body.get("tags")
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []

    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")

    try:
        result = await create_faq_pair(
            question=question,
            answer=answer,
            language=language,
            tags=tags,
            updated_by=session.user_id or session.email,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"success": True, **result}
