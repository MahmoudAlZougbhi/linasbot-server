"""Web Chat widget configuration models."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from services.web_chat.appearance import IntegrationMode, normalize_appearance, normalize_integration_mode


@dataclass
class WebChatInstallation:
    last_seen_at: float | None = None
    last_origin: str = ""

    @property
    def installed(self) -> bool:
        return self.last_seen_at is not None and self.last_seen_at > 0


@dataclass
class WebChatWidgetConfig:
    tenant_id: str
    widget_key: str
    site_url: str
    enabled: bool
    created_at: float
    updated_at: float
    integration_mode: IntegrationMode = "linas_widget"
    appearance: dict[str, Any] = field(default_factory=dict)
    installation: WebChatInstallation = field(default_factory=WebChatInstallation)

    @property
    def connected(self) -> bool:
        return bool(self.site_url.strip()) and self.enabled

    @property
    def integration_public_id(self) -> str:
        return self.widget_key


def installation_from_raw(raw: dict[str, Any] | None) -> WebChatInstallation:
    if not isinstance(raw, dict):
        return WebChatInstallation()
    seen = raw.get("last_seen_at")
    return WebChatInstallation(
        last_seen_at=float(seen) if seen is not None else None,
        last_origin=str(raw.get("last_origin") or ""),
    )


def config_from_raw(tenant_id: str, raw: dict[str, Any]) -> WebChatWidgetConfig:
    return WebChatWidgetConfig(
        tenant_id=str(raw.get("tenant_id") or tenant_id),
        widget_key=str(raw.get("widget_key") or ""),
        site_url=str(raw.get("site_url") or ""),
        enabled=bool(raw.get("enabled")),
        created_at=float(raw.get("created_at") or time.time()),
        updated_at=float(raw.get("updated_at") or time.time()),
        integration_mode=normalize_integration_mode(raw.get("integration_mode")),
        appearance=normalize_appearance(raw.get("appearance") if isinstance(raw.get("appearance"), dict) else None),
        installation=installation_from_raw(
            raw.get("installation") if isinstance(raw.get("installation"), dict) else None
        ),
    )


def config_to_raw(config: WebChatWidgetConfig) -> dict[str, Any]:
    return {
        "tenant_id": config.tenant_id,
        "widget_key": config.widget_key,
        "site_url": config.site_url,
        "enabled": config.enabled,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
        "integration_mode": config.integration_mode,
        "appearance": config.appearance,
        "installation": {
            "last_seen_at": config.installation.last_seen_at,
            "last_origin": config.installation.last_origin,
        },
    }
