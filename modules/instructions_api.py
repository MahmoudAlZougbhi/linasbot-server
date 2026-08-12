"""Legacy global instructions/style-guide API — disabled (410 Gone).

Product path is tenant CM: ``/api/cm/...`` (style / AI basics drafts + publish).
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from modules.core import app

_GONE = {
    "success": False,
    "error": "Legacy /api/instructions is disabled. Use tenant Content Management (/api/cm/...).",
    "code": "INSTRUCTIONS_API_GONE",
}


def _gone() -> JSONResponse:
    return JSONResponse(status_code=410, content=_GONE)


@app.get("/api/instructions/get")
async def get_instructions() -> Any:
    return _gone()


@app.post("/api/instructions/update")
async def update_instructions() -> Any:
    return _gone()


@app.get("/api/instructions/backups")
async def list_backups() -> Any:
    return _gone()


@app.post("/api/instructions/restore")
async def restore_backup() -> Any:
    return _gone()


@app.get("/api/instructions/stats")
async def get_instructions_stats() -> Any:
    return _gone()
