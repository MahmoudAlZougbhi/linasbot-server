"""Public mobile app version config + installed-version check."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException

from modules.core import app
from services.mobile_app_version import InvalidAppVersionError, app_version_config, evaluate_app_version


@app.get("/api/public/app-version")
async def public_app_version_config() -> Any:
    """Latest/min marketing versions and store URLs — unauthenticated."""
    try:
        cfg = app_version_config()
    except (InvalidAppVersionError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, **cfg}


@app.post("/api/public/app-version/check")
async def public_app_version_check(
    body: dict[str, Any] = Body(default={}),
) -> Any:
    """Compare installed marketing semver to server config."""
    installed = body.get("installed_version")
    if not isinstance(installed, str) or not installed.strip():
        raise HTTPException(status_code=400, detail="installed_version is required")
    try:
        return evaluate_app_version(installed)
    except InvalidAppVersionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
