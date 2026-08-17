"""TikTok CM action toggles. Does not touch Meta disconnect or Meta webhooks."""

from __future__ import annotations

from typing import Any, Literal

from services.cm.actions import ACTION_TIKTOK_COMMENTS, ACTION_TIKTOK_DM
from services.cm.publish import PublishBlockedError, publish_draft_sections
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.schemas import ActionCapability, ActionsSection, SectionDraftEnvelope
from services.cm.storage import ConflictError, draft_section_path, get_draft, put_draft
from services.cm.version_store import read_published_pointer
from services.tiktok_business.scopes import comments_read_ready, messaging_send_ready
from services.tiktok_business.status import tiktok_integration_row

ToggleKey = Literal["dm", "comments"]


class TikTokToggleError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "TOGGLE_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def attach_tiktok_row_toggles(row: dict[str, Any]) -> dict[str, Any]:
    comments = row.get("comments_state") if isinstance(row.get("comments_state"), dict) else {}
    dm = row.get("dm_state") if isinstance(row.get("dm_state"), dict) else {}
    enriched = {
        **row,
        "toggles": {
            "dm": bool(dm.get("requested_enabled")),
            "comments": bool(comments.get("requested_enabled")),
        },
        "comments_state": comments or row.get("comments_state"),
        "dm_state": dm or row.get("dm_state"),
    }
    blocker = (comments or {}).get("blocker_code") or (comments or {}).get("blocker")
    if blocker:
        enriched["comments_blocker"] = blocker
    return enriched


def _action_id(toggle: ToggleKey) -> str:
    return ACTION_TIKTOK_DM if toggle == "dm" else ACTION_TIKTOK_COMMENTS


def _draft_envelope(*, tenant_id: str, actor: str) -> SectionDraftEnvelope:
    from services.cm.actions import load_actions_section

    if draft_section_path(tenant_id, "actions").exists():
        return get_draft("actions", tenant_id=tenant_id, create_default=False)
    published = load_actions_section(tenant_id)
    if published is not None:
        return put_draft(
            "actions",
            payload=published.model_dump(),
            if_match="*",
            tenant_id=tenant_id,
            updated_by=actor,
            allow_create=True,
        )
    return get_draft("actions", tenant_id=tenant_id, create_default=True)


def _set_action(*, tenant_id: str, action_id: str, enabled: bool, actor: str) -> None:
    envelope = _draft_envelope(tenant_id=tenant_id, actor=actor)
    section = ActionsSection.model_validate(envelope.payload or {})
    found = False
    next_items: list[ActionCapability] = []
    for item in section.items:
        if item.id == action_id:
            next_items.append(item.model_copy(update={"enabled": bool(enabled)}))
            found = True
        else:
            next_items.append(item)
    if not found:
        next_items.append(ActionCapability(id=action_id, enabled=bool(enabled)))
    put_draft(
        "actions",
        payload=ActionsSection(items=next_items, notes=section.notes).model_dump(),
        if_match=envelope.etag,
        tenant_id=tenant_id,
        updated_by=actor,
    )


async def _publish(*, tenant_id: str, actor: str) -> None:
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        raise TikTokToggleError(exc.message, status_code=403, code="PUBLISH_DISABLED") from exc
    try:
        names = None if read_published_pointer(tenant_id) is None else ["actions"]
        await publish_draft_sections(
            tenant_id=tenant_id,
            published_by=actor,
            notes="tiktok_integrations_channel_toggle",
            section_names=names,
        )
    except PublishBlockedError as exc:
        raise TikTokToggleError(exc.message, status_code=422, code="PUBLISH_BLOCKED") from exc


async def set_tiktok_toggle(
    *,
    tenant_id: str,
    toggle: ToggleKey,
    enabled: bool,
    actor: str,
) -> dict[str, Any]:
    row = tiktok_integration_row(tenant_id)
    if enabled and not row.get("binding_ids"):
        raise TikTokToggleError("Connect TikTok before enabling this capability.", status_code=409, code="CONNECT_REQUIRED")
    scopes = row.get("granted_scopes") or []
    if toggle == "dm" and enabled and not messaging_send_ready(scopes):
        raise TikTokToggleError(
            "TikTok Business Messaging is pending TikTok approval.",
            status_code=409,
            code="TIKTOK_CAPABILITY_GATED",
        )
    if toggle == "comments" and enabled and not comments_read_ready(scopes):
        raise TikTokToggleError(
            "TikTok did not grant Get Account Comment. Reconnect and approve those scopes.",
            status_code=409,
            code="COMMENT_SCOPES_MISSING",
        )
    if toggle == "comments" and enabled:
        from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed

        try:
            assert_comment_automation_allowed(tenant_id)
        except CommentAutomationDenied as exc:
            raise TikTokToggleError(str(exc), status_code=403, code=exc.code) from exc
    try:
        _set_action(tenant_id=tenant_id, action_id=_action_id(toggle), enabled=enabled, actor=actor)
        await _publish(tenant_id=tenant_id, actor=actor)
    except ConflictError as exc:
        raise TikTokToggleError("Actions draft changed; reload and retry.", status_code=409, code="DRAFT_CONFLICT") from exc
    return {
        "toggles": {
            "dm": bool(tiktok_integration_row(tenant_id).get("dm_state", {}).get("requested_enabled")),
            "comments": bool(tiktok_integration_row(tenant_id).get("comments_state", {}).get("requested_enabled")),
        },
        "comments_state": tiktok_integration_row(tenant_id).get("comments_state"),
        "dm_state": tiktok_integration_row(tenant_id).get("dm_state"),
    }


async def enable_tiktok_comments_after_connect(*, tenant_id: str, actor: str) -> None:
    try:
        await set_tiktok_toggle(tenant_id=tenant_id, toggle="comments", enabled=True, actor=actor)
    except TikTokToggleError:
        return
