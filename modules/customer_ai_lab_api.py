"""Platform-admin isolated Customer Brain lab. Disabled unless LINAS_CUSTOMER_AI_LAB=1."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.customer_ai.evals.runner import run_fixture_corpus
from services.customer_ai.test_lab import lab_enabled, run_lab_turn
from services.membership.message_policy import classify_turn, message_units_for


class LabTurnBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = "lab:conv"
    user_id: str = "lab:user"
    channel: str = "web_chat"
    message_id: str = ""
    history: list[dict[str, Any]] | None = None


@app.post("/api/platform/customer-ai-lab/turn")
async def platform_customer_ai_lab_turn(body: LabTurnBody, request: Request) -> Any:
    require_platform_owner(request)
    if not lab_enabled():
        raise HTTPException(status_code=404, detail="lab_disabled")
    if not str(body.tenant_id).startswith("lab_") and body.tenant_id != "lab":
        raise HTTPException(status_code=400, detail="lab_tenant_required")
    result = await run_lab_turn(
        tenant_id=body.tenant_id,
        message=body.message,
        conversation_id=body.conversation_id,
        user_id=body.user_id,
        channel=body.channel,
        message_id=body.message_id,
        history=body.history,
    )
    return {"success": True, **result}


class LabClassifyBody(BaseModel):
    generated: bool = False
    faq_used: bool = False
    followup_sent: bool = False


@app.post("/api/platform/customer-ai-lab/classify")
async def platform_customer_ai_lab_classify(body: LabClassifyBody, request: Request) -> Any:
    require_platform_owner(request)
    if not lab_enabled():
        raise HTTPException(status_code=404, detail="lab_disabled")
    response_class = classify_turn(
        generated=body.generated,
        faq_used=body.faq_used,
        followup_sent=body.followup_sent,
    )
    return {
        "success": True,
        "response_class": response_class,
        "message_units": message_units_for(response_class),
        "live_send": False,
    }


@app.get("/api/platform/customer-ai-lab/evals")
async def platform_customer_ai_lab_evals(request: Request) -> Any:
    require_platform_owner(request)
    if not lab_enabled():
        raise HTTPException(status_code=404, detail="lab_disabled")
    return {"success": True, **run_fixture_corpus()}
