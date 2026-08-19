"""Make an AI Setup section Save immediately Live for customer replies.

Does not add a user-facing Draft→Publish step. After ``put_draft`` (which already
runs save-time Luna on changed items only), this flips the published pointer using
the existing publish machinery so Luna/Terra read the new revision on the next message.
"""

from __future__ import annotations

from typing import Any

from services.cm.constants import cm_emergency_disable_publish
from services.cm.schemas import SectionDraftEnvelope
from services.cm.storage import put_draft


async def go_live_saved_section(
    *,
    tenant_id: str,
    section: str,
    actor_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Activate the current draft of ``section`` as the customer-live published version."""
    from services.cm.constants import tenant_has_published_cm
    from services.cm.publish import PublishBlockedError, publish_draft, publish_draft_sections

    name = (section or "").strip().replace("-", "_")
    if cm_emergency_disable_publish():
        return {
            "activated": False,
            "live": False,
            "reason": "emergency_disable",
            "section": name,
            "message": "Publishing is temporarily disabled by an emergency ops switch.",
        }
    has_published = tenant_has_published_cm(tenant_id)
    try:
        if has_published:
            result = await publish_draft_sections(
                tenant_id=tenant_id,
                published_by=actor_id or "save",
                notes=notes or f"save_live:{name}",
                section_names=[name],
            )
            mode = "section_overlay"
        else:
            result = await publish_draft(
                tenant_id=tenant_id,
                published_by=actor_id or "save",
                notes=notes or f"save_live_first:{name}",
            )
            mode = "first_live_full_publish"
        return {
            "activated": True,
            "live": True,
            "mode": mode,
            "section": name,
            "content_version_id": getattr(result, "content_version_id", None),
            "index_version_id": getattr(result, "index_version_id", None),
        }
    except PublishBlockedError as exc:
        return {
            "activated": False,
            "live": False,
            "reason": "publish_blocked",
            "section": name,
            "errors": list(getattr(exc, "errors", []) or [])[:20],
            "message": str(exc),
        }
    except Exception as exc:
        return {
            "activated": False,
            "live": False,
            "reason": type(exc).__name__,
            "section": name,
            "message": str(exc)[:200],
        }


async def put_draft_and_go_live(
    *,
    section: str,
    payload: dict[str, Any],
    if_match: str | None,
    tenant_id: str,
    updated_by: str = "unknown",
    allow_create: bool = False,
) -> tuple[SectionDraftEnvelope, dict[str, Any]]:
    """Save one section (metadata first) then make that same payload customer-live."""
    envelope = put_draft(
        section,
        payload=payload,
        if_match=if_match,
        tenant_id=tenant_id,
        updated_by=updated_by,
        allow_create=allow_create,
    )
    activation = await go_live_saved_section(
        tenant_id=tenant_id,
        section=section,
        actor_id=updated_by,
    )
    return envelope, activation
