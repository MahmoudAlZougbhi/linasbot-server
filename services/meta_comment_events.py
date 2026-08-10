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
    MetaBindingCredential,
    get_meta_app_registry,
)
from services.meta_graph_routing import build_messaging_settings_for_binding
from services.meta_instagram_login_capabilities import (
    binding_ready_for_comments,
    facebook_login_binding_superseded_for_capability,
    select_instagram_binding_for_capability,
)
from services.meta_instagram_login_config import AuthFlow, instagram_login_app_id
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
            from_raw = value.get("from")
            from_dict = from_raw if isinstance(from_raw, dict) else {}
            author_id = str(from_dict.get("id") or "").strip()
            text = str(value.get("message") or value.get("text") or "").strip()
            if not comment_id or not author_id or not text:
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


def count_raw_comment_changes(payload: dict[str, Any]) -> int:
    """Count comment-shaped webhook changes without binding resolution (observability)."""

    object_name = str(payload.get("object") or "").strip().lower()
    count = 0
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            field = str(change.get("field") or "").strip().lower()
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            if object_name == "page" and field == "feed":
                if str(value.get("item") or "").strip().lower() != "comment":
                    continue
                verb = str(value.get("verb") or "add").strip().lower()
                if verb not in {"add", "edited"}:
                    continue
                count += 1
            elif object_name == "instagram" and field == "comments":
                count += 1
    return count


def comment_binding_skip_reason(
    binding: MetaAssetBinding,
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry,
) -> str | None:
    """Return why a binding cannot handle comments, or None when ready."""

    try:
        credential = registry.get_credential(binding)
    except Exception:
        return "credential_unavailable"
    if binding.auth_flow == "facebook_login" and credential.token_app_id != app_config.app_id:
        return "token_app_mismatch"
    if binding.auth_flow == "instagram_login" and credential.token_app_id != instagram_login_app_id():
        return "token_app_mismatch"
    if credential.expires_at and credential.expires_at <= int(time.time()):
        return "token_expired"
    if facebook_login_binding_superseded_for_capability(binding, "comments", registry=registry):
        return "superseded_by_instagram_login"
    if not binding_ready_for_comments(binding, credential):
        return "comment_scopes_or_subscription_missing"
    return None


def _prepare_comment_binding(
    binding: MetaAssetBinding,
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry,
) -> tuple[MetaAssetBinding, MetaBindingCredential] | None:
    if comment_binding_skip_reason(binding, app_config=app_config, registry=registry) is not None:
        return None
    return binding, registry.get_credential(binding)


def resolve_registry_comment_events(
    payload: dict[str, Any],
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry | None = None,
    auth_flow: AuthFlow | None = None,
) -> list[ResolvedMetaCommentEvent]:
    """Resolve comment webhook payloads to active App A bindings."""

    if app_config.key != APP_A_KEY:
        return []
    current_registry = registry or get_meta_app_registry()
    bindings = [
        binding
        for binding in current_registry.get_active_bindings_for_app(app_config.key)
        if binding.status == "active" and (auth_flow is None or binding.auth_flow == auth_flow)
    ]
    by_comment_id: dict[str, list[tuple[MetaAssetBinding, MetaBindingCredential, dict[str, Any]]]] = {}
    for binding in bindings:
        prepared = _prepare_comment_binding(binding, app_config=app_config, registry=current_registry)
        if prepared is None:
            continue
        active_binding, credential = prepared
        events = parse_meta_comment_events(
            payload,
            channel=active_binding.channel,
            page_id=active_binding.page_id,
            instagram_account_id=active_binding.instagram_account_id or active_binding.asset_id,
        )
        for event in events:
            if str(event.get("channel") or "") != active_binding.channel:
                continue
            event_asset = (
                active_binding.instagram_account_id if active_binding.channel == "instagram" else active_binding.page_id
            )
            if event_asset != active_binding.asset_id:
                continue
            comment_id = str(event.get("comment_id") or "")
            if not comment_id:
                continue
            by_comment_id.setdefault(comment_id, []).append((active_binding, credential, event))

    resolved: list[ResolvedMetaCommentEvent] = []
    for _comment_id, options in by_comment_id.items():
        instagram_options = [item for item in options if item[0].channel == "instagram"]
        facebook_options = [item for item in options if item[0].channel == "facebook"]
        chosen: tuple[MetaAssetBinding, MetaBindingCredential, dict[str, Any]] | None = None
        if instagram_options:
            selected = select_instagram_binding_for_capability(
                [binding for binding, _, _ in instagram_options],
                "comments",
                registry=current_registry,
            )
            if selected is not None:
                for binding, credential, event in instagram_options:
                    if binding.binding_id == selected.binding_id:
                        chosen = (binding, credential, event)
                        break
        elif facebook_options:
            chosen = facebook_options[0]
        if chosen is None:
            continue
        binding, credential, event = chosen
        settings = build_messaging_settings_for_binding(
            binding,
            credential=credential,
            app_config=app_config,
        )
        tagged = dict(event)
        tagged.update(
            {
                "tenant_id": binding.tenant_id,
                "meta_app_key": app_config.key,
                "meta_binding_id": binding.binding_id,
                "meta_auth_flow": binding.auth_flow,
            }
        )
        resolved.append(ResolvedMetaCommentEvent(event=tagged, settings=settings, binding=binding))
    return resolved


def summarize_comment_resolve_drops(
    payload: dict[str, Any],
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry | None = None,
    auth_flow: AuthFlow | None = None,
) -> dict[str, Any]:
    """Redacted summary when comment-shaped webhooks do not resolve to a binding."""

    current_registry = registry or get_meta_app_registry()
    bindings = [
        binding
        for binding in current_registry.get_active_bindings_for_app(app_config.key)
        if binding.status == "active" and (auth_flow is None or binding.auth_flow == auth_flow)
    ]
    reasons: dict[str, int] = {}
    for binding in bindings:
        reason = comment_binding_skip_reason(binding, app_config=app_config, registry=current_registry) or "ready"
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "raw_comment_changes": count_raw_comment_changes(payload),
        "active_bindings": len(bindings),
        "skip_reasons": reasons,
    }
