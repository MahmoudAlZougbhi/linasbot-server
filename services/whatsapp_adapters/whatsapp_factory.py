"""
WhatsApp Adapter Factory
Creates and manages WhatsApp adapters.

Runtime transport is Meta Cloud only. Legacy MontyMobile / Qiscus / 360dialog
adapter modules may remain on disk for archive, but must not be selected as
default or fallback transport.
"""

from __future__ import annotations

import os
from typing import Any

from .base_adapter import WhatsAppAdapter
from .meta_adapter import MetaAdapter
from .outbound_dedupe_text_adapter import DedupeOutboundTextAdapter
from .safe_send_adapter import SafeSendAdapter

_config_module: Any
try:
    import config as _config_module
except ImportError:
    _config_module = None

config: Any = _config_module

# Supported runtime transport. Legacy names are refused (no silent Monty fallback).
_SUPPORTED_PROVIDERS = frozenset({"meta", "cloud"})
_UNSUPPORTED_LEGACY_PROVIDERS = frozenset({"montymobile", "qiscus", "360dialog", "dialog360"})


def _wrap_if_safe_send(adapter: WhatsAppAdapter) -> WhatsAppAdapter:
    """Wrap adapter with SafeSendAdapter when local env or sending disabled."""
    if config is None:
        return adapter
    if getattr(config, "is_local_env", lambda: False)() or not getattr(config, "ENABLE_SENDING", True):
        print("📋 Outbound WhatsApp: dry-run or sandbox-only (APP_MODE=local / ENABLE_SENDING=false)")
        return SafeSendAdapter(adapter)
    return adapter


def _normalize_provider(provider: str | None) -> str:
    raw = (provider or "").strip().lower()
    if not raw:
        raw = (os.getenv("WHATSAPP_PROVIDER") or "meta").strip().lower() or "meta"
    # "cloud" is an alias for Meta Cloud API
    if raw == "cloud":
        return "meta"
    return raw


def _refuse_unsupported_provider(provider: str) -> None:
    if provider in _SUPPORTED_PROVIDERS or provider == "meta":
        return
    if provider in _UNSUPPORTED_LEGACY_PROVIDERS:
        raise ValueError(
            f"WhatsApp provider {provider!r} is unsupported. "
            "Runtime transport is Meta Cloud only (WHATSAPP_PROVIDER=meta). "
            "MontyMobile / Qiscus / 360dialog are not available as runtime fallback."
        )
    raise ValueError(
        f"Unknown WhatsApp provider: {provider!r}. "
        "Supported: meta (Cloud). Legacy montymobile/qiscus/360dialog are disabled."
    )


class WhatsAppFactory:
    """Factory for creating WhatsApp adapters (Meta Cloud only at runtime)."""

    _current_adapter: WhatsAppAdapter | None = None
    _current_provider: str = "meta"

    @classmethod
    def get_adapter(cls, provider: str | None = None) -> WhatsAppAdapter:
        """Get WhatsApp adapter instance (Meta Cloud only)."""
        resolved = _normalize_provider(provider if provider is not None else cls._current_provider)
        _refuse_unsupported_provider(resolved)
        cls._current_provider = "meta"

        if cls._current_adapter and hasattr(cls._current_adapter, "provider_name"):
            if cls._current_adapter.provider_name == "meta":
                return cls._current_adapter

        cls._current_adapter = cls._create_meta_adapter()
        cls._current_adapter.provider_name = "meta"
        cls._current_adapter = _wrap_if_safe_send(cls._current_adapter)
        cls._current_adapter = DedupeOutboundTextAdapter(cls._current_adapter)
        return cls._current_adapter

    @classmethod
    def _create_meta_adapter(cls) -> MetaAdapter:
        """Create Meta WhatsApp adapter"""
        api_token = os.getenv("WHATSAPP_API_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

        if not api_token or not phone_number_id:
            raise ValueError("Meta WhatsApp credentials not found in environment variables")

        return MetaAdapter(api_token, phone_number_id)

    @classmethod
    def _create_360dialog_adapter(cls) -> WhatsAppAdapter:
        """Archived: 360dialog is not a runtime transport."""
        raise ValueError("360dialog WhatsApp provider is unsupported. Runtime transport is Meta Cloud only.")

    @classmethod
    def _create_qiscus_adapter(cls) -> WhatsAppAdapter:
        """Archived: Qiscus is not a runtime transport."""
        raise ValueError("Qiscus WhatsApp provider is unsupported. Runtime transport is Meta Cloud only.")

    @classmethod
    def _create_montymobile_adapter(cls) -> WhatsAppAdapter:
        """Archived: MontyMobile is not a runtime transport."""
        raise ValueError("MontyMobile WhatsApp provider is unsupported. Runtime transport is Meta Cloud only.")

    @classmethod
    def switch_provider(cls, provider: str) -> WhatsAppAdapter:
        """Switch WhatsApp provider (Meta Cloud only; legacy names refused)."""
        resolved = _normalize_provider(provider)
        _refuse_unsupported_provider(resolved)
        print(f"Switching WhatsApp provider from {cls._current_provider} to meta")

        if cls._current_adapter:
            pass

        cls._current_provider = "meta"
        cls._current_adapter = None
        return cls.get_adapter()

    @classmethod
    def get_current_provider(cls) -> str:
        """Get current WhatsApp provider name"""
        return cls._current_provider

    @classmethod
    async def close_current_adapter(cls) -> None:
        """Close current adapter connection"""
        if cls._current_adapter:
            await cls._current_adapter.close()
            cls._current_adapter = None
