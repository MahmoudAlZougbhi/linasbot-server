"""Per-asset Meta public comment reply settings (default off, tenant-isolated)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.meta_app_registry import APP_A_KEY, MetaChannel, binding_asset_key, normalize_meta_tenant_id
from storage.persistent_storage import _DATA_ROOT

_SETTINGS_ROOT = Path(_DATA_ROOT) / "meta_comment_settings"
_LOCK = threading.Lock()
_runtime_logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class MetaCommentReplySetting:
    tenant_id: str
    app_key: str
    channel: MetaChannel
    asset_id: str
    enabled: bool = False
    instructions: str = ""
    updated_at: float = 0.0

    @property
    def asset_key(self) -> str:
        return binding_asset_key(self.tenant_id, self.app_key, self.channel, self.asset_id)

    def public_dict(self) -> dict[str, Any]:
        return {
            "asset_key": self.asset_key,
            "tenant_id": self.tenant_id,
            "app_key": self.app_key,
            "channel": self.channel,
            "asset_id": self.asset_id,
            "enabled": self.enabled,
            "instructions": self.instructions,
            "updated_at": self.updated_at,
        }


def _tenant_path(tenant_id: str) -> Path:
    tenant = normalize_meta_tenant_id(tenant_id)
    return _SETTINGS_ROOT / f"{tenant}.json"


def _load_tenant_file(tenant_id: str) -> dict[str, Any]:
    path = _tenant_path(tenant_id)
    if not path.is_file():
        return {"settings": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"settings": {}}
    if not isinstance(payload, dict):
        return {"settings": {}}
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return {"settings": {}}
    return {"settings": settings}


def _save_tenant_file(tenant_id: str, settings: dict[str, Any]) -> None:
    path = _tenant_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"settings": settings}, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    try:
        from services.ha_tenant_config_peer_sync import replicate_comment_settings_to_peer

        replicate_comment_settings_to_peer(tenant_id)
    except Exception:
        _runtime_logger.error("[meta-comment-settings] ha_peer_replicate_failed tenant=%s", tenant_id)


def get_comment_reply_setting(
    *,
    tenant_id: str,
    app_key: str,
    channel: MetaChannel,
    asset_id: str,
) -> MetaCommentReplySetting:
    tenant = normalize_meta_tenant_id(tenant_id)
    key = binding_asset_key(tenant, app_key, channel, asset_id)
    with _LOCK:
        raw = _load_tenant_file(tenant).get("settings", {}).get(key, {})
    if not isinstance(raw, dict):
        raw = {}
    return MetaCommentReplySetting(
        tenant_id=tenant,
        app_key=app_key,
        channel=channel,
        asset_id=asset_id,
        enabled=bool(raw.get("enabled")),
        instructions=str(raw.get("instructions") or "").strip(),
        updated_at=float(raw.get("updated_at") or 0.0),
    )


def list_comment_reply_settings(tenant_id: str) -> list[MetaCommentReplySetting]:
    tenant = normalize_meta_tenant_id(tenant_id)
    with _LOCK:
        settings_raw = _load_tenant_file(tenant).get("settings", {})
    rows: list[MetaCommentReplySetting] = []
    if not isinstance(settings_raw, dict):
        return rows
    for key, raw in settings_raw.items():
        if not isinstance(raw, dict):
            continue
        parts = str(key).split(":", 3)
        if len(parts) != 4:
            continue
        channel = parts[2]
        if channel not in {"facebook", "instagram"}:
            continue
        rows.append(
            MetaCommentReplySetting(
                tenant_id=parts[0],
                app_key=parts[1],
                channel=channel,  # type: ignore[arg-type]
                asset_id=parts[3],
                enabled=bool(raw.get("enabled")),
                instructions=str(raw.get("instructions") or "").strip(),
                updated_at=float(raw.get("updated_at") or 0.0),
            )
        )
    return rows


def set_comment_reply_setting(
    *,
    tenant_id: str,
    app_key: str,
    channel: MetaChannel,
    asset_id: str,
    enabled: bool,
    instructions: str = "",
) -> MetaCommentReplySetting:
    if app_key != APP_A_KEY:
        raise ValueError("Comment replies are only supported for App A bindings")
    tenant = normalize_meta_tenant_id(tenant_id)
    key = binding_asset_key(tenant, app_key, channel, asset_id)
    record = MetaCommentReplySetting(
        tenant_id=tenant,
        app_key=app_key,
        channel=channel,
        asset_id=asset_id,
        enabled=bool(enabled),
        instructions=str(instructions or "").strip()[:2000],
        updated_at=time.time(),
    )
    with _LOCK:
        payload = _load_tenant_file(tenant)
        settings = payload.setdefault("settings", {})
        if not isinstance(settings, dict):
            settings = {}
            payload["settings"] = settings
        settings[key] = {
            "enabled": record.enabled,
            "instructions": record.instructions,
            "updated_at": record.updated_at,
        }
        _save_tenant_file(tenant, settings)
    return record


def comment_reply_settings_by_asset_key(tenant_id: str) -> dict[str, MetaCommentReplySetting]:
    return {row.asset_key: row for row in list_comment_reply_settings(tenant_id)}
