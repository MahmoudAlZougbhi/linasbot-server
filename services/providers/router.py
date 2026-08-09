"""Config-driven model/provider router."""

from __future__ import annotations

from typing import Any, Literal

from services.model_pricing import compute_cost_from_usage
from services.providers.base import TextGenerationResult, provider_config

RouteKind = Literal["customer_dm", "owner_chat", "setup_complex", "creative_text"]


class ProviderRouter:
    def resolve_text_model(self, kind: RouteKind) -> dict[str, str]:
        cfg = provider_config()["text"]
        return {"provider": str(cfg["provider"]), "model": str(cfg[kind])}

    def resolve_image(self) -> dict[str, str]:
        cfg = provider_config()["image"]
        return {"provider": str(cfg["provider"]), "model": str(cfg["model"])}

    def resolve_video(self) -> dict[str, str]:
        cfg = provider_config()["video"]
        return {"provider": str(cfg["provider"]), "model": str(cfg["model"])}

    async def generate_text(
        self,
        *,
        kind: RouteKind,
        messages: list[dict[str, str]],
        max_tokens: int = 800,
    ) -> TextGenerationResult:
        route = self.resolve_text_model(kind)
        # Reuse existing OpenAI client path when provider is openai.
        if route["provider"] != "openai":
            raise RuntimeError(f"Text provider not configured: {route['provider']}")
        from services.llm_core_service import create_chat_completion

        resp = await create_chat_completion(
            model=route["model"],
            messages=messages,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cached = int(getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0)
        cost = compute_cost_from_usage(route["model"], prompt_tokens, completion_tokens)
        return TextGenerationResult(
            text=choice,
            model=route["model"],
            provider=route["provider"],
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cached_tokens=cached,
            provider_cost_usd=float(cost["cost_usd"]),
        )

    def public_routes(self) -> dict[str, Any]:
        return provider_config()


provider_router = ProviderRouter()
