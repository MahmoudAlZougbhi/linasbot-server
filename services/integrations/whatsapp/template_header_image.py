"""Public HTTPS image URL for WhatsApp Cloud template IMAGE headers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from storage.persistent_storage import APP_SETTINGS_FILE


def _sidecar_path() -> Path:
    return Path(APP_SETTINGS_FILE).parent / "template_header_image_url.txt"


def _cloud_templates_config_path() -> Path:
    envp = os.getenv("WHATSAPP_CLOUD_TEMPLATES_CONFIG_PATH", "").strip()
    if envp:
        return Path(envp)
    return Path(__file__).resolve().parents[3] / "config" / "whatsapp_cloud_templates.json"


def _read_sidecar() -> str:
    path = _sidecar_path()
    if not path.is_file():
        return ""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = (line or "").strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        return ""
    return ""


def _default_header_url_from_cloud_templates() -> str:
    path = _cloud_templates_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return ""
    dc = (data.get("api_config") or {}).get("default_header_component") or {}
    if isinstance(dc, dict):
        return str(dc.get("image_link") or dc.get("link") or "").strip()
    return ""


def _url_from_app_settings() -> str:
    path = Path(APP_SETTINGS_FILE)
    if not path.is_file():
        return ""
    try:
        root = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(root, dict):
        return ""
    for key in ("templateHeaderImageUrl", "template_header_image_url", "header_image_url"):
        raw = root.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return ""


def get_template_header_image_url() -> str:
    """Order: env → sidecar → app_settings → Cloud templates JSON."""
    env = os.getenv("WHATSAPP_TEMPLATE_HEADER_IMAGE_URL", "").strip()
    if env:
        return env
    sidecar = _read_sidecar()
    if sidecar:
        return sidecar
    from_settings = _url_from_app_settings()
    if from_settings:
        return from_settings
    return _default_header_url_from_cloud_templates()
