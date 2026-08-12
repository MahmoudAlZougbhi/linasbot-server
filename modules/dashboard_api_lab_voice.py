"""Dashboard Testing Lab voice leftovers — product-disabled stubs (LOC split).

Unreachable lab bodies removed (W12-A4). Routes refuse immediately.
"""

from __future__ import annotations

from typing import Any

from fastapi import File, Form, UploadFile

from modules.core import app
from modules.dashboard_api_helpers import _refuse_disabled_lab_endpoint
from modules.models import TestVoiceRequest


@app.post("/api/test-voice")
async def test_voice(
    audio: UploadFile = File(None),
    phone: str = Form(None),
    provider: str = Form(None),
    voice_text: str = Form(None),
) -> Any:
    """Testing Lab voice endpoint — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/test-voice-text")
async def test_voice_text(request: TestVoiceRequest) -> Any:
    """Testing Lab voice-text endpoint — product-disabled."""
    _refuse_disabled_lab_endpoint()
