"""Creative Studio API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.creative_studio_service import create_creative_draft
from services.safety_gateway import safety_gateway
from storage.persistent_storage import _DATA_ROOT


class CreativeBody(BaseModel):
    kind: Literal["post", "caption", "image", "reel_concept", "video", "rewrite", "campaign_ideas"]
    prompt: str = Field(min_length=1, max_length=4000)


def _resolve_creative_asset(filename: str) -> Path | None:
    safe = Path(filename or "").name
    if not safe or safe in {".", ".."} or "/" in (filename or "") or "\\" in (filename or ""):
        return None
    root = (Path(_DATA_ROOT) / "creative_assets").resolve()
    candidate = (root / safe).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


@app.get("/api/creative-assets/{filename}")
async def serve_creative_asset(filename: str) -> Any:
    """Serve Creative Studio image outputs from durable storage."""
    path = _resolve_creative_asset(filename)
    if path is None or not path.is_file():
        return Response(content="File not found", status_code=404)
    return FileResponse(str(path), media_type="image/png")


@app.post("/api/creative/generate")
async def creative_generate(body: CreativeBody, request: Request) -> Any:
    session = require_session(request)
    decision = await safety_gateway.check_text(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        text=body.prompt,
        channel="creative",
    )
    if decision.decision == "block":
        raise HTTPException(status_code=400, detail={"error": "Blocked by safety gateway", "reasons": decision.reasons})
    try:
        result = await create_creative_draft(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            kind=body.kind,
            prompt=body.prompt,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return {"success": True, "result": result}
