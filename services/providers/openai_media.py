"""Real OpenAI image / video generation for Creative Studio (no stubs)."""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from services.providers.base import ImageGenerationResult, VideoGenerationResult

DEFAULT_IMAGE_COST_USD = float(os.getenv("LINAS_IMAGE_COST_USD") or "0.08")
DEFAULT_VIDEO_COST_USD = float(os.getenv("LINAS_VIDEO_COST_USD") or "0.50")


def _creative_assets_root() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    root = Path(_DATA_ROOT) / "creative_assets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _public_asset_url(relative_name: str) -> str:
    from services.media_service import get_public_base_url

    return f"{get_public_base_url()}/api/creative-assets/{relative_name}"


async def generate_openai_image(*, prompt: str, model: str, tenant_id: str) -> ImageGenerationResult:
    """Call Images API and persist PNG under LINASBOT_DATA_ROOT/creative_assets."""
    from services.llm_core_service import client

    text = (prompt or "").strip()
    if not text:
        raise ValueError("image prompt required")

    response = await client.images.generate(
        model=model,
        prompt=text,
        size="1024x1024",
        quality="high",
        n=1,
    )
    data = getattr(response, "data", None) or []
    if not data:
        raise RuntimeError("openai_image_empty_response")
    first = data[0]
    b64 = getattr(first, "b64_json", None) or (first.get("b64_json") if isinstance(first, dict) else None)
    if not b64:
        raise RuntimeError("openai_image_missing_b64")

    raw = base64.b64decode(b64)
    safe_tenant = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (tenant_id or "tenant"))[:64]
    name = f"{safe_tenant}_{uuid.uuid4().hex}.png"
    path = _creative_assets_root() / name
    path.write_bytes(raw)

    return ImageGenerationResult(
        asset_url=_public_asset_url(name),
        model=model,
        provider="openai",
        provider_cost_usd=DEFAULT_IMAGE_COST_USD,
    )


async def start_openai_video(*, prompt: str, model: str) -> VideoGenerationResult:
    """Start an OpenAI Videos API job (Sora). Uses HTTP — openai SDK 1.x has no videos client.

    Returns the provider job id with status queued/in_progress. Does not fake a finished MP4.
    """
    import config

    text = (prompt or "").strip()
    if not text:
        raise ValueError("video prompt required")
    api_key = (getattr(config, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing for video generation")

    # Multipart form matches OpenAI Videos API contract.
    timeout = float(os.getenv("LINAS_VIDEO_START_TIMEOUT_SECONDS") or "60")
    async with httpx.AsyncClient(timeout=timeout) as http:
        resp = await http.post(
            "https://api.openai.com/v1/videos",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": model,
                "prompt": text,
                "seconds": os.getenv("LINAS_VIDEO_SECONDS") or "8",
                "size": os.getenv("LINAS_VIDEO_SIZE") or "1280x720",
            },
        )
    if resp.status_code >= 400:
        detail = " ".join(resp.text.split())[:220]
        raise RuntimeError(f"openai_video_start_failed:{resp.status_code}:{detail}")

    payload: dict[str, Any]
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("openai_video_bad_json") from exc

    job_id = str(payload.get("id") or "").strip()
    status = str(payload.get("status") or "queued").strip() or "queued"
    if not job_id:
        raise RuntimeError("openai_video_missing_job_id")

    return VideoGenerationResult(
        job_id=job_id,
        status=status,
        model=str(payload.get("model") or model),
        provider="openai",
        provider_cost_usd=DEFAULT_VIDEO_COST_USD,
    )
