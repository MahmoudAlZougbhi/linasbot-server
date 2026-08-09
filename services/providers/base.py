"""Provider interfaces — replaceable without rewriting product flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TextGenerationResult:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    provider_cost_usd: float


@dataclass(frozen=True)
class ImageGenerationResult:
    asset_url: str
    model: str
    provider: str
    provider_cost_usd: float


@dataclass(frozen=True)
class VideoGenerationResult:
    job_id: str
    status: str
    model: str
    provider: str
    provider_cost_usd: float


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    model: str
    provider: str
    provider_cost_usd: float


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    categories: dict[str, bool]
    provider: str


class TextModelProvider(Protocol):
    async def generate(
        self, *, messages: list[dict[str, str]], model: str, max_tokens: int
    ) -> TextGenerationResult: ...


class ImageProvider(Protocol):
    async def generate(self, *, prompt: str, model: str) -> ImageGenerationResult: ...


class VideoProvider(Protocol):
    async def start(self, *, prompt: str, model: str) -> VideoGenerationResult: ...


class SpeechToTextProvider(Protocol):
    async def transcribe(self, *, audio_path: str, model: str) -> TranscriptionResult: ...


class ModerationProvider(Protocol):
    async def moderate(self, *, text: str) -> ModerationResult: ...


def provider_config() -> dict[str, Any]:
    """Configuration-driven model/provider names.

    Text reply models come from the central Sol/Terra policy (env cannot silently override).
    Image/video/stt/moderation remain env-configurable.
    """
    import os

    from services.model_policy import MODEL_CUSTOMER_TERRA, MODEL_OWNER_SOL

    return {
        "text": {
            "customer_dm": MODEL_CUSTOMER_TERRA,
            "owner_chat": MODEL_OWNER_SOL,
            "setup_complex": MODEL_OWNER_SOL,
            "creative_text": MODEL_OWNER_SOL,
            "provider": os.getenv("LINAS_TEXT_PROVIDER", "openai"),
        },
        "image": {
            "model": os.getenv("LINAS_IMAGE_MODEL", "gpt-image-2"),
            "provider": os.getenv("LINAS_IMAGE_PROVIDER", "openai"),
        },
        "video": {
            "model": os.getenv("LINAS_VIDEO_MODEL", "sora-2-pro"),
            "provider": os.getenv("LINAS_VIDEO_PROVIDER", "openai"),
        },
        "stt": {
            "model": os.getenv("LINAS_STT_MODEL", "whisper-1"),
            "provider": os.getenv("LINAS_STT_PROVIDER", "openai"),
        },
        "moderation": {
            "provider": os.getenv("LINAS_MODERATION_PROVIDER", "openai"),
        },
    }
