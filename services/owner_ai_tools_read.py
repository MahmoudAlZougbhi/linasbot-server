"""Typed read tools for the owner System Copilot."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


async def tool_help(*, tenant_id: str, role: str, query: str = "") -> ToolResult:
    del tenant_id, role
    from services.system_knowledge_retrieval import help_payload_for_query

    return ToolResult(ok=True, name="help", data=help_payload_for_query(query))


async def tool_read_profile(*, tenant_id: str, role: str, user_id: str) -> ToolResult:
    del tenant_id, role
    from services.owner_ai_profile import read_owner_profile

    return ToolResult(ok=True, name="read_profile", data={"profile": read_owner_profile(user_id)})


async def tool_read_account_summary(*, tenant_id: str, role: str, user_id: str) -> ToolResult:
    del role
    from services.owner_ai_account_state import build_account_summary

    return ToolResult(
        ok=True,
        name="read_account_summary",
        data=build_account_summary(tenant_id=tenant_id, user_id=user_id),
    )


async def tool_read_cm(*, tenant_id: str, role: str, section: str | None = None) -> ToolResult:
    _require(role, "contentManagers")
    from services.cm.constants import CM_SECTIONS, tenant_has_published_cm
    from services.cm.storage import UnknownSectionError, get_draft, list_sections

    published = tenant_has_published_cm(tenant_id)
    if section:
        try:
            env = get_draft(section, tenant_id=tenant_id, create_default=False)
        except UnknownSectionError:
            return ToolResult(ok=False, name="read_cm", data={}, error=f"Unknown section: {section}")
        payload = env.model_dump(mode="json") if env is not None else None
        # Compact: section metadata + keys only when large
        draft_out: dict[str, Any] | None
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            keys = sorted(payload["payload"].keys())
            draft_out = {
                "section": section,
                "revision": payload.get("revision"),
                "etag": payload.get("etag"),
                "payload_keys": keys,
                "payload_preview": {k: payload["payload"].get(k) for k in keys[:8]},
            }
        else:
            draft_out = payload
        return ToolResult(
            ok=True,
            name="read_cm",
            data={"section": section, "draft": draft_out, "published": published},
        )

    listed = {str(item.get("section")): item for item in list_sections(tenant_id=tenant_id)}
    overview: dict[str, Any] = {}
    for sec in CM_SECTIONS:
        item = listed.get(sec)
        overview[sec] = {
            "present": bool(item and item.get("exists")),
            "revision": item.get("revision") if item else None,
        }
    present = sum(1 for v in overview.values() if v.get("present"))
    return ToolResult(
        ok=True,
        name="read_cm",
        data={
            "sections": overview,
            "sections_present": present,
            "sections_total": len(CM_SECTIONS),
            "published": published,
        },
    )


async def tool_validate_cm(*, tenant_id: str, role: str) -> ToolResult:
    _require(role, "contentManagers")
    from services.cm.validation import validate_cm

    report = validate_cm(tenant_id=tenant_id)
    return ToolResult(ok=True, name="validate_cm", data={"report": report})


async def tool_read_usage(*, tenant_id: str, role: str) -> ToolResult:
    del role
    from services.token_wallet_service import token_wallet_service

    wallet = token_wallet_service.get_wallet(tenant_id)
    return ToolResult(ok=True, name="read_usage", data={"wallet": wallet.to_public_dict()})


async def tool_read_subscription(*, tenant_id: str, role: str) -> ToolResult:
    del role
    from services.entitlements_service import get_tenant_entitlement_public

    return ToolResult(ok=True, name="read_subscription", data=get_tenant_entitlement_public(tenant_id))


async def tool_read_integrations(*, tenant_id: str, role: str) -> ToolResult:
    del role
    from services.integration_capabilities import list_tenant_integration_status

    # Comments are not a product surface — do not expose comment_* caps to System Copilot.
    rows: list[dict[str, Any]] = []
    for row in list_tenant_integration_status(tenant_id):
        caps = row.get("capabilities") or {}
        if isinstance(caps, dict):
            caps = {k: v for k, v in caps.items() if not str(k).lower().startswith("comment")}
        rows.append({**row, "capabilities": caps})
    return ToolResult(ok=True, name="read_integrations", data={"integrations": rows})


async def tool_read_dashboard_metrics(*, tenant_id: str, role: str, user_id: str = "") -> ToolResult:
    del role
    data: dict[str, Any] = {"tenant_id": tenant_id}
    try:
        from services.entitlements_service import get_tenant_entitlement_public
        from services.owner_ai_account_state import compute_cm_progress, compute_integration_summary
        from services.token_wallet_service import token_wallet_service

        cm = compute_cm_progress(tenant_id)
        integ = compute_integration_summary(tenant_id)
        data["setup_signals"] = {
            "cm_sections_present": cm.get("sections_present"),
            "cm_published": cm.get("published"),
            "integrations_connected": integ.get("any_connected"),
        }
        data["wallet"] = token_wallet_service.get_wallet(tenant_id).to_public_dict()
        data["plan"] = get_tenant_entitlement_public(tenant_id)
        if user_id:
            data["viewer_user_id"] = user_id
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="read_dashboard_metrics",
            data={},
            error=f"metrics_unavailable:{type(exc).__name__}",
        )
    return ToolResult(ok=True, name="read_dashboard_metrics", data=data)


async def tool_read_scheduled_posts(*, tenant_id: str, role: str) -> ToolResult:
    del role
    from services.schedule_service import schedule_service

    posts = schedule_service.list_for_tenant(tenant_id)
    compact = [
        {
            "id": getattr(p, "id", None),
            "platform": getattr(p, "platform", None),
            "scheduled_at": getattr(p, "scheduled_at", None),
            "status": getattr(p, "status", None),
        }
        for p in posts[:50]
    ]
    return ToolResult(ok=True, name="read_scheduled_posts", data={"posts": compact, "count": len(compact)})


async def tool_read_jobs_errors(*, tenant_id: str, role: str) -> ToolResult:
    del role, tenant_id
    import os

    require_redis = os.getenv("LINAS_REQUIRE_REDIS", "").strip().lower() in {"1", "true", "yes", "on"}
    if not require_redis:
        return ToolResult(
            ok=True,
            name="read_jobs_errors",
            data={
                "available": False,
                "reason": "Redis workers not required/active (LINAS_REQUIRE_REDIS unset).",
                "jobs": [],
            },
        )
    try:
        from services.job_queue import job_queue

        return ToolResult(ok=True, name="read_jobs_errors", data={"available": True, "health": job_queue.health()})
    except Exception as exc:
        return ToolResult(
            ok=True,
            name="read_jobs_errors",
            data={"available": False, "reason": f"{type(exc).__name__}: queue not reachable", "jobs": []},
        )
