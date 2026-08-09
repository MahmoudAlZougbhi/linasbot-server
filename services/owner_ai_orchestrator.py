"""Owner Linas AI turn orchestration with safe tool routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.owner_ai_tools import TOOL_HANDLERS, ToolResult, list_tool_names


@dataclass
class OwnerTurnResult:
    reply_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmation: str | None = None


_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(what can you do|capabilities|help)\b", re.I), "help"),
    (re.compile(r"\b(usage|credits|wallet|how much)\b", re.I), "read_usage"),
    (re.compile(r"\b(subscription|plan|billing)\b", re.I), "read_subscription"),
    (re.compile(r"\b(instagram|facebook|meta|integrat|connected)\b", re.I), "read_integrations"),
    (re.compile(r"\b(validate|missing|setup complete)\b", re.I), "validate_cm"),
    (re.compile(r"\b(publish)\b", re.I), "publish_cm"),
    (re.compile(r"\b(what does my ai know|content management|cm|draft)\b", re.I), "read_cm"),
]


def _help_text() -> str:
    tools = ", ".join(list_tool_names())
    return (
        "I can help you configure Linas AI, inspect Content Management, check usage and "
        "subscription, review integrations, validate drafts, and publish when you confirm. "
        f"Available tools: {tools}. High-impact actions always ask for confirmation."
    )


async def run_owner_turn(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    conversation_id: str,
    user_text: str,
    confirm_tool: str | None = None,
) -> OwnerTurnResult:
    """Route owner chat to typed tools. Does not write CM except via publish tool."""
    del user_id, conversation_id  # reserved for future context packing / audit
    text = (user_text or "").strip()
    if not text and not confirm_tool:
        return OwnerTurnResult(reply_text="Tell me what you’d like to configure or inspect.")

    intent = confirm_tool
    if not intent:
        for pattern, name in _INTENT_PATTERNS:
            if pattern.search(text):
                intent = name
                break

    if intent == "help" or intent is None:
        # Prefer help when unmatched; still answer generally.
        if intent is None:
            return OwnerTurnResult(
                reply_text=(
                    _help_text()
                    + " For configuration changes, ask me specifically "
                    + "(for example: validate my setup, check Instagram, show usage)."
                )
            )
        return OwnerTurnResult(reply_text=_help_text())

    handler = TOOL_HANDLERS.get(intent)
    if handler is None:
        return OwnerTurnResult(reply_text=_help_text())

    try:
        if intent == "publish_cm":
            result: ToolResult = await handler(
                tenant_id=tenant_id,
                role=role,
                confirmed=confirm_tool == "publish_cm",
            )
        elif intent == "read_cm":
            result = await handler(tenant_id=tenant_id, role=role, section=None)
        else:
            result = await handler(tenant_id=tenant_id, role=role)
    except PermissionError as exc:
        return OwnerTurnResult(reply_text=f"I can’t do that with your role: {exc}")
    except Exception as exc:
        return OwnerTurnResult(reply_text=f"That tool failed safely without applying changes: {type(exc).__name__}")

    tool_payload = result.to_dict()
    if result.requires_confirmation:
        return OwnerTurnResult(
            reply_text=(
                "Publishing will update your live customer AI from the current draft. "
                "Reply with confirmation or send confirm_tool=publish_cm from the app."
            ),
            tool_calls=[tool_payload],
            pending_confirmation=result.confirmation_token,
        )

    summary = _summarize(result)
    return OwnerTurnResult(reply_text=summary, tool_calls=[tool_payload])


def _summarize(result: ToolResult) -> str:
    if not result.ok:
        return result.error or "Tool failed."
    if result.name == "read_usage":
        wallet = result.data.get("wallet") or {}
        return f"Usage snapshot: {wallet}"
    if result.name == "read_subscription":
        return f"Subscription: {result.data}"
    if result.name == "read_integrations":
        return f"Integrations: {result.data.get('integrations')}"
    if result.name == "validate_cm":
        report = result.data.get("report") or {}
        errors = report.get("errors") if isinstance(report, dict) else None
        return f"Validation complete. Errors: {len(errors) if isinstance(errors, list) else 'see report'}."
    if result.name == "publish_cm":
        return "Publish completed successfully."
    if result.name == "read_cm":
        sections = (result.data.get("sections") or {}) if isinstance(result.data, dict) else {}
        present = sum(1 for v in sections.values() if isinstance(v, dict) and v.get("present"))
        return f"Content Management draft has {present} section(s) present. Ask about a specific section to dive in."
    return "Done."
