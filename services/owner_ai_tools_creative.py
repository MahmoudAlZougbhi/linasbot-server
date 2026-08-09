"""Creative draft tools for owner chat (Create Post in-chat)."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult

_TASK_OPTIONS: list[dict[str, str]] = [
    {"id": "auto", "label": "Auto"},
    {"id": "compress", "label": "Compress"},
    {"id": "caption", "label": "Caption"},
    {"id": "post", "label": "Post"},
    {"id": "rewrite", "label": "Rewrite"},
    {"id": "campaign_ideas", "label": "Campaign ideas"},
    {"id": "image", "label": "Image"},
    {"id": "video", "label": "Video"},
]

_VAGUE_CREATE = re.compile(
    r"^\s*("
    r"create(\s+a)?\s+post|"
    r"make(\s+a)?\s+post|"
    r"i\s+want\s+to\s+(make|create)(\s+a)?\s+post|"
    r"let'?s\s+(make|create)(\s+a)?\s+post|"
    r"بدي\s*(نعمل|اعمل|أعمل)\s*(بوست|منشور)|"
    r"بدنا\s*(نعمل|ننشئ)\s*(بوست|منشور)|"
    r"أريد\s*(أن\s*)?(أعمل|انشئ|أنشئ)\s*(بوست|منشور)|"
    r"انشاء\s*منشور|"
    r"créer(\s+une)?\s+(publication|post)"
    r")\s*[.!?؟]*\s*$",
    re.I,
)


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def infer_creative_kind(text: str, requested: str | None = None) -> str:
    kind = (requested or "").strip().lower()
    if kind and kind not in {"auto", ""}:
        if kind == "compress":
            return "rewrite"
        return kind
    t = f" {(text or '').lower()} "
    if any(x in t for x in (" compress ", " shorten ", " اختصر ", " لخص ", " لخّص ", " compresser ")):
        return "rewrite"
    if any(x in t for x in (" image ", " صورة ", " صور ", " photo ")):
        return "image"
    if any(x in t for x in (" video ", " فيديو ", " reel ", " ريل ")):
        return "video"
    if any(x in t for x in (" caption ", " كابشن ", " légende ")):
        return "caption"
    if any(x in t for x in (" campaign ", " حملة ", " campagne ")):
        return "campaign_ideas"
    if any(x in t for x in (" rewrite ", " أعد كتابة ", " réécrire ")):
        return "rewrite"
    return "post"


def _publish_gate() -> dict[str, Any]:
    return {
        "publish": False,
        "publish_reason": "Meta content_publish is not live_verified — publish stays gated.",
        "edit": True,
        "regenerate": True,
        "schedule": True,
    }


async def tool_create_creative_draft(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    prompt: str,
    kind: str | None = None,
    compress: bool = False,
) -> ToolResult:
    _require(role, "contentManagers")
    text = (prompt or "").strip()
    if not text:
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "needs_brief",
                "kind": "auto",
                "task_options": _TASK_OPTIONS,
                "actions": _publish_gate(),
            },
        )

    requested = (kind or "").strip().lower()
    if requested == "compress":
        compress = True
    resolved = infer_creative_kind(text, requested if requested not in {"", "auto"} else None)

    if _VAGUE_CREATE.match(text) and requested in {"", "auto", None}:
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "needs_brief",
                "kind": "auto",
                "task_options": _TASK_OPTIONS,
                "prompt": text,
                "actions": _publish_gate(),
            },
        )

    if resolved == "video":
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "unavailable",
                "kind": "video",
                "reason": "Video generation has no production provider yet.",
                "task_options": _TASK_OPTIONS,
                "actions": {**_publish_gate(), "regenerate": False, "schedule": False},
            },
        )

    from services.creative_studio_service import create_creative_draft

    studio_prompt = text
    if compress or requested == "compress":
        studio_prompt = f"Compress and tighten this social content. Keep the brand voice. Source:\n{text}"
        resolved = "rewrite"

    try:
        result = await create_creative_draft(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=resolved,  # type: ignore[arg-type]
            prompt=studio_prompt,
        )
    except PermissionError as exc:
        return ToolResult(
            ok=False,
            name="create_creative_draft",
            data={"status": "entitlement_blocked", "kind": resolved},
            error=str(exc),
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="create_creative_draft",
            data={"status": "failed", "kind": resolved},
            error=f"{type(exc).__name__}: {exc}",
        )

    payload = {
        **result,
        "prompt": text,
        "requested_kind": requested or "auto",
        "task_options": _TASK_OPTIONS,
        "actions": _publish_gate(),
    }
    return ToolResult(ok=True, name="create_creative_draft", data=payload)


async def tool_schedule_creative_draft(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    text: str,
    kind: str = "post",
    platform: str | None = None,
    scheduled_at: float | None = None,
) -> ToolResult:
    del user_id
    _require(role, "contentManagers")
    body = (text or "").strip()
    if not body:
        return ToolResult(
            ok=False,
            name="schedule_creative_draft",
            data={},
            error="Nothing to schedule — generate a draft first.",
        )

    from services.integration_capabilities import list_tenant_integration_status
    from services.schedule_service import schedule_service

    rows = list_tenant_integration_status(tenant_id)
    connected = [
        r
        for r in rows
        if isinstance(r, dict) and r.get("connected") and str(r.get("platform") or "") in {"instagram", "facebook"}
    ]
    if platform:
        connected = [r for r in connected if str(r.get("platform")) == platform]
    if not connected:
        return ToolResult(
            ok=False,
            name="schedule_creative_draft",
            data={"needs_integration": True},
            error="Connect Instagram or Facebook in Integrations before scheduling.",
        )

    row = connected[0]
    binding_ids = row.get("binding_ids") if isinstance(row.get("binding_ids"), list) else []
    account = str(
        (binding_ids[0] if binding_ids else None)
        or row.get("account_id")
        or row.get("connected_account")
        or row.get("id")
        or ""
    ).strip()
    plat = str(row.get("platform") or "instagram")
    if not account:
        return ToolResult(
            ok=False,
            name="schedule_creative_draft",
            data={"needs_integration": True},
            error="Connected account id missing — reconnect Meta in Integrations.",
        )

    when = float(scheduled_at) if scheduled_at else time.time() + 3600
    try:
        post = schedule_service.create(
            tenant_id=tenant_id,
            connected_account=account,
            platform=plat,
            content_asset={"kind": kind or "post", "text": body, "source": "owner_chat"},
            scheduled_at=when,
            timezone="UTC",
            idempotency_key=f"owner-chat:{uuid.uuid4().hex}",
        )
    except PermissionError as exc:
        return ToolResult(
            ok=False,
            name="schedule_creative_draft",
            data={"status": "entitlement_blocked"},
            error=str(exc),
        )

    return ToolResult(
        ok=True,
        name="schedule_creative_draft",
        data={
            "status": "scheduled",
            "post_id": post.id,
            "platform": plat,
            "scheduled_at": post.scheduled_at,
            "note": "Queued for schedule. Meta publish still requires content_publish live_verified.",
        },
    )
