"""Dashboard Testing Lab upload/stats leftovers — product-disabled stubs (LOC split).

Unreachable lab bodies removed (W12-A4). ``/api/stats`` refuses like other lab
surfaces (also matched by ``is_disabled_api_path``).
"""

from __future__ import annotations

from typing import Any

from fastapi import File, Form, UploadFile

from modules.core import app
from modules.dashboard_api_helpers import _refuse_disabled_lab_endpoint


@app.post("/api/test-voice-upload")
async def test_voice_upload(
    audio: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("meta")
) -> Any:
    """Testing Lab voice upload — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/test-image-upload")
async def test_image_upload(
    image: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("meta")
) -> Any:
    """Testing Lab image upload — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.get("/api/stats")
async def get_stats() -> Any:
    """Legacy in-memory lab stats — product-disabled (no conversation leak)."""
    _refuse_disabled_lab_endpoint()
