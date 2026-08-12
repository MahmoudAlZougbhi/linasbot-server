"""Dashboard Testing Lab + debug leftovers — product-disabled stubs (LOC split).

Unreachable lab bodies removed (W12-A4). Routes remain registered and refuse
with 403 via ``_refuse_disabled_lab_endpoint`` (middleware also blocks these
prefixes via ``is_disabled_api_path``).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.core import app
from modules.dashboard_api_helpers import _refuse_disabled_lab_endpoint
from modules.models import ProviderSwitchRequest, TestImageRequest, TestMessageRequest


@app.get("/api/debug/webhook-status")
async def webhook_status() -> Any:
    """Debug webhook probe — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/debug/simulate-webhook")
async def simulate_webhook(_req: Request) -> Any:
    """Simulate webhook — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.get("/api/test")
async def test_api() -> Any:
    """Legacy Testing Lab health probe — disabled for all tenants."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/switch-provider")
async def switch_provider(request: ProviderSwitchRequest) -> Any:
    """HTTP provider switching is permanently refused."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/test-message")
async def test_message(request: TestMessageRequest) -> Any:
    """Testing Lab message endpoint — product-disabled."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/test-image")
async def test_image(request: TestImageRequest) -> Any:
    """Testing Lab image endpoint — product-disabled."""
    _refuse_disabled_lab_endpoint()
