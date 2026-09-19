"""Comment/DM rule proposals from Sol chat. Ask when required fields are missing."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from modules.api_security import resolve_permissions
from services.owner_copilot.tools_base import ToolResult

_ACTIONS = {
    "COMMENT_ONLY": "reply_comment",
    "DM_ONLY": "reply_dm",
    "BOTH": "reply_comment_and_dm",
    "reply_comment": "reply_comment",
    "reply_dm": "reply_dm",
    "reply_comment_and_dm": "reply_comment_and_dm",
    "reply_comment_static": "reply_comment_static",
    "send_dm_static": "send_dm_static",
    "reply_comment_and_dm_static": "reply_comment_and_dm_static",
}


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def _missing_comment_fields(args: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    action = str(args.get("action") or args.get("mode") or "").strip()
    if not action or action not in _ACTIONS:
        missing.append("action (COMMENT_ONLY / DM_ONLY / BOTH, or static variants)")
    wording = str(args.get("reply_template") or args.get("dm_template") or args.get("ai_instructions") or "").strip()
    rule_mode = str(args.get("rule_mode") or "deterministic").strip()
    if rule_mode == "ai_guidance":
        if not str(args.get("ai_instructions") or "").strip():
            missing.append("ai_instructions")
    elif not wording:
        missing.append("reply_template or dm_template")
    scope = str(args.get("scope") or "").strip() or ("specific_post" if args.get("post_id") else "all_posts")
    if scope == "specific_post" and not str(args.get("post_id") or "").strip():
        missing.append("post_id (pick a connected post or paste an id)")
    return missing


async def tool_list_connected_posts(
    *,
    tenant_id: str,
    role: str,
    platform: str = "",
    after: str = "",
    limit: int = 20,
) -> ToolResult:
    _require(role, "contentManagers")
    from services.brain.reply.connected_posts import list_connected_posts, list_tenant_comment_accounts

    accounts = list_tenant_comment_accounts(tenant_id)
    if not accounts:
        return ToolResult(
            ok=True,
            name="list_connected_posts",
            data={"accounts": [], "posts": [], "note": "No connected comment accounts."},
        )
    plat = (platform or "").strip().lower()
    chosen = next((a for a in accounts if not plat or a.get("platform") == plat), accounts[0])
    posts = await list_connected_posts(
        tenant_id=tenant_id,
        platform=str(chosen.get("platform") or ""),
        connected_account_id=str(chosen.get("connected_account_id") or ""),
        after=after,
        limit=max(1, min(limit, 50)),
    )
    return ToolResult(
        ok=True,
        name="list_connected_posts",
        data={"accounts": accounts, "selected": chosen, "posts": posts},
    )


async def tool_propose_comment_rule(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    args: dict[str, Any],
) -> ToolResult:
    _require(role, "contentManagers")
    missing = _missing_comment_fields(args)
    if missing:
        return ToolResult(
            ok=True,
            name="propose_comment_rule",
            data={
                "needs_clarification": True,
                "missing_fields": missing,
                "ai_directive": (
                    "Ask the owner for the missing comment-rule fields before opening Approve cards. "
                    "Do not guess wording or COMMENT_ONLY/DM_ONLY/BOTH."
                ),
            },
        )
    from services.ai_setup.storage import get_draft
    from services.owner_copilot.tools_write import tool_propose_cm_patch

    env = get_draft("comments", tenant_id=tenant_id, create_default=True)
    payload = dict(env.payload) if isinstance(env.payload, dict) else {}
    rules = [dict(r) for r in (payload.get("rules") or []) if isinstance(r, dict)]
    action = _ACTIONS[str(args.get("action") or args.get("mode") or "").strip()]
    rule_mode = str(args.get("rule_mode") or "deterministic").strip() or "deterministic"
    if action.endswith("_static"):
        rule_mode = "deterministic"
    post_id = str(args.get("post_id") or "").strip()
    rule = {
        "id": str(args.get("id") or f"cr_{uuid4().hex[:12]}"),
        "enabled": True,
        "name": str(args.get("name") or args.get("title") or "Comment rule").strip(),
        "scope": "specific_post" if post_id else "all_posts",
        "rule_mode": rule_mode if rule_mode in {"deterministic", "ai_guidance"} else "deterministic",
        "trigger_type": str(args.get("trigger_type") or "all_comments"),
        "action": action,
        "reply_template": str(args.get("reply_template") or ""),
        "dm_template": str(args.get("dm_template") or ""),
        "ai_instructions": str(args.get("ai_instructions") or ""),
        "post_id": post_id,
        "post_ids": [post_id] if post_id else [],
        "platform": str(args.get("platform") or ""),
        "channel": str(args.get("channel") or "any") or "any",
        "keywords": list(args.get("keywords") or []) if isinstance(args.get("keywords"), list) else [],
    }
    existing = next((i for i, row in enumerate(rules) if str(row.get("id") or "") == rule["id"]), None)
    if existing is None:
        rules.append(rule)
    else:
        merged = {**rules[existing], **rule}
        rules[existing] = merged
        rule = merged
    return await tool_propose_cm_patch(
        tenant_id=tenant_id,
        role=role,
        user_id=user_id,
        section="comments",
        patch={"rules": rules},
        force_edit=True,
    )
