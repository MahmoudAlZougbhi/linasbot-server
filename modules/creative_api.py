"""Creative Studio asset serving. Generation runs through Owner Copilot tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, Response

from modules.core import app
from storage.persistent_storage import _DATA_ROOT


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
