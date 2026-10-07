"""Platform-owner console: talk to one tenant's Customer Brain and Owner Copilot."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.owner_portal.platform_brain_lab import copilot_lab_turn, customer_lab_turn
from services.team.platform_owner_service import platform_owner_service


class LabHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(default="", max_length=4000)


class LabTurnBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    history: list[LabHistoryItem] = Field(default_factory=list, max_length=20)
    mode: Literal["live", "draft"] = "live"


def _history(body: LabTurnBody) -> list[dict[str, str]]:
    return [{"role": item.role, "text": item.text} for item in body.history]


async def _turn(request: Request, body: LabTurnBody, brain: Literal["customer", "copilot"]) -> dict[str, Any]:
    session = require_platform_owner(request)
    runner = customer_lab_turn if brain == "customer" else copilot_lab_turn
    try:
        kwargs: dict[str, Any] = {
            "actor_user_id": session.user_id,
            "tenant_id": body.tenant_id,
            "message": body.message,
            "history": _history(body),
        }
        if brain == "customer":
            kwargs["mode"] = body.mode
        result = await runner(**kwargs)
    except ValueError as exc:
        code = str(exc)
        status = 400 if code == "empty_message" else 404
        raise HTTPException(status_code=status, detail=code) from exc
    platform_owner_service.log_action(
        actor_user_id=session.user_id,
        action=f"brain_lab_{brain}",
        tenant_id=str(result.get("tenant_id") or ""),
        details={"brain": brain},
    )
    return {"success": True, **result}


@app.post("/api/platform/brains/customer")
async def platform_customer_brain(body: LabTurnBody, request: Request) -> Any:
    return await _turn(request, body, "customer")


@app.post("/api/platform/brains/copilot")
async def platform_copilot_brain(body: LabTurnBody, request: Request) -> Any:
    return await _turn(request, body, "copilot")
