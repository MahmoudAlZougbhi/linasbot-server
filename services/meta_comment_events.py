"""Parse Meta webhook comment events (Facebook Page feed + Instagram comments)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Literal

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppConfig,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_registry,
)
from services.meta_messaging import MetaMessagingSettings

MetaCommentChannel = Literal["facebook", "instagram"]


@dataclass(frozen=True)
class ResolvedMetaCommentEvent:
    event: dict[str, Any]
    settings: MetaMessagingSettings
    binding: MetaAssetBinding


def _stable_comment_id(*parts: str) -> str:
    joined = "|".join(part for part in parts if part)
    return "meta_comment_" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:48]


def _parse_facebook_comment_changes(
    payload: dict[str, Any],
    *,
    page_id: str,
) -> list[dict[str, Any]]:
    if str(payload.get("object") or "").strip().lower() != "page":
        return []
    events: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if page_id and entry_id and entry_id != page_id:
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if str(change.get("field") or "").strip().lower() != "feed":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            if str(value.get("item") or "").strip().lower() != "comment":
                continue
            verb = str(value.get("verb") or "add").strip().lower()
            if verb not in {"add", "edited"}:
                continue
            comment_id = str(value.get("comment_id") or value.get("id") or "").strip()
            post_id = str(value.get("post_id") or value.get("parent_id") or "").strip()
            parent_id = str(value.get("parent_id") or "").strip()
            if parent_id and parent_id != post_id and parent_id != comment_id:
                # Nested reply to another comment — still a new comment event.
                pass
            from_raw = value.get("from")
            from_dict = from_raw if isinstance(from_raw, dict) else {}
            author_id = str(from_dict.get("id") or "").strip()
            text = str(value.get("message") or value.get("text") or "").strip()
            if not comment_id or not author_id:
                continue
            if not text:
                continue
            events.append(
                {
                    "channel": "facebook",
                    "comment_id": comment_id,
                    "media_id": post_id,
                    "post_id": post_id,
                    "parent_id": parent_id,
                    "author_id": author_id,
                    "author_name": str(from_dict.get("name") or "").strip(),
                    "text": text,
                    "timestamp": value.get("created_time") or entry.get("time"),
                    "message_id": comment_id or _stable_comment_id("facebook", entry_id, comment_id, text),
                    "account_id": entry_id or page_id,
                }
            )
    return events


def _parse_instagram_comment_changes(
    payload: dict[str, Any],
    *,
    instagram_account_id: str,
) -> list[dict[str, Any]]:
    if str(payload.get("object") or "").strip().lower() != "instagram":
        return []
    events: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if instagram_account_id and entry_id and entry_id != instagram_account_id:
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if str(change.get("field") or "").strip().lower() != "comments":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            comment_id = str(value.get("id") or "").strip()
            text = str(value.get("text") or "").strip()
            from_raw = value.get("from")
            from_dict = from_raw if isinstance(from_raw, dict) else {}
            author_id = str(from_dict.get("id") or "").strip()
            media_raw = value.get("media")
            media = media_raw if isinstance(media_raw, dict) else {}
            media_id = str(media.get("id") or value.get("media_id") or "").strip()
            if not comment_id or not author_id or not text:
                continue
            events.append(
                {
                    "channel": "instagram",
                    "comment_id": comment_id,
                    "media_id": media_id,
                    "post_id": media_id,
                    "parent_id": str(value.get("parent_id") or "").strip(),
                    "author_id": author_id,
                    "author_username": str(from_dict.get("username") or "").strip(),
                    "text": text,
                    "timestamp": value.get("created_time") or entry.get("time"),
                    "message_id": comment_id,
                    "account_id": entry_id or instagram_account_id,
                }
            )
    return events


def parse_meta_comment_events(
    payload: dict[str, Any],
    *,
    channel: MetaCommentChannel,
    page_id: str = "",
    instagram_account_id: str = "",
) -> list[dict[str, Any]]:
    if channel == "facebook":
        return _parse_facebook_comment_changes(payload, page_id=page_id)
    return _parse_instagram_comment_changes(payload, instagram_account_id=instagram_account_id)


def resolve_registry_comment_events(
    payload: dict[str, Any],
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry | None = None,
) -> list[ResolvedMetaCommentEvent]:
    """Resolve comment webhook payloads to active App A bindings only."""

    if app_config.key != APP_A_KEY:
        return []
    current_registry = registry or get_meta_app_registry()
    resolved: list[ResolvedMetaCommentEvent] = []
    claimed: set[tuple[str, str]] = set()
    for binding in current_registry.get_active_bindings_for_app(app_config.key):
        if binding.status != "active":
            continue
        credential = current_registry.get_credential(binding)
        if credential.token_app_id != app_config.app_id:
            continue
        if credential.expires_at and credential.expires_at <= int(time.time()):
            continue
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret=app_config.app_secret,
            page_id=binding.page_id,
            page_access_token=credential.access_token,
            instagram_account_id=binding.instagram_account_id,
            verify_token=app_config.verify_token,
            graph_api_version=app_config.graph_api_version,
            app_id=app_config.app_id,
            app_key=app_config.key,
            tenant_id=binding.tenant_id,
            binding_id=binding.binding_id,
        )
        events = parse_meta_comment_events(
            payload,
            channel=binding.channel,
            page_id=binding.page_id,
            instagram_account_id=binding.instagram_account_id,
        )
        for event in events:
            if str(event.get("channel") or "") != binding.channel:
                continue
            event_asset = binding.instagram_account_id if binding.channel == "instagram" else binding.page_id
            if event_asset != binding.asset_id:
                continue
            comment_id = str(event.get("comment_id") or "")
            key = (binding.binding_id, comment_id)
            if not comment_id or key in claimed:
                continue
            claimed.add(key)
            tagged = dict(event)
            tagged.update(
                {
                    "tenant_id": binding.tenant_id,
                    "meta_app_key": app_config.key,
                    "meta_binding_id": binding.binding_id,
                }
            )
            resolved.append(ResolvedMetaCommentEvent(event=tagged, settings=settings, binding=binding))
    return resolved
