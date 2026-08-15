"""First-run setup inside the same owner chat → same CM draft."""

from __future__ import annotations

from services.owner_ai_tools_base import ToolResult

SETUP_SECTIONS: tuple[str, ...] = (
    "basics",
    "languages",
    "tone",
    "greetings",
    "services",
    "branches",
    "prices",
    "knowledge",
    "faq",
    "handoff",
    "restricted",
    "sources",
    "allowed_actions",
    "ai_limits",
    "off_days",
    "integrations",
    "review_publish",
)


def _section_prompt(section: str, *, language: str = "en") -> str:
    prompts = {
        "basics": "Let's set business basics (name, category). What is your business name and category?",
        "languages": "Which languages should the customer AI use? (Arabic, English, French, …)",
        "tone": "Which reply tone should customers hear?",
        "greetings": "What greeting should customers get on first contact?",
        "services": "List your main services or products.",
        "branches": "Do you have branches/locations to configure?",
        "prices": "Share prices/offers, or upload a price-list photo.",
        "knowledge": "Any core business knowledge the AI must know?",
        "faq": "Common questions and answers to save as Smart Q&A?",
        "handoff": "When should the AI hand off to a human?",
        "restricted": "Any topics the AI must refuse?",
        "sources": "Files/links to use as sources?",
        "allowed_actions": "Which AI actions are allowed for customers?",
        "ai_limits": "Any AI usage limits to enforce?",
        "off_days": "Off days or holidays?",
        "integrations": "Connect Instagram/Facebook when ready (Integrations screen).",
        "review_publish": "Review, validate, then publish when ready (separate confirmation).",
    }
    text = prompts.get(section, f"Continue setup: {section}")
    if language == "ar":
        return f"إعداد — {section}: أكمل هذه الخطوة في نفس المحادثة (نفس مسودة إعداد الذكاء الاصطناعي)."
    return text


async def tool_setup_next_step(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    action: str = "status",
    section: str | None = None,
) -> ToolResult:
    del role
    from services.owner_ai_account_state import build_account_summary

    summary = build_account_summary(tenant_id=tenant_id, user_id=user_id)
    stage = str(summary.get("setup_stage") or "new")
    cm = summary.get("cm") or {}
    present = int(cm.get("sections_present") or 0)
    total = int(cm.get("sections_total") or len(SETUP_SECTIONS))

    idx = 0
    if section and section in SETUP_SECTIONS:
        idx = SETUP_SECTIONS.index(section)
    else:
        # Heuristic progress: map filled sections to next unfinished
        idx = min(present, len(SETUP_SECTIONS) - 1)

    if action == "skip_section":
        idx = min(idx + 1, len(SETUP_SECTIONS) - 1)
    elif action == "continue":
        idx = min(idx + (1 if section else 0), len(SETUP_SECTIONS) - 1)

    current = SETUP_SECTIONS[idx]
    ask_tone = current == "tone"
    data = {
        "setup_stage": stage,
        "section": current,
        "sections": list(SETUP_SECTIONS),
        "index": idx,
        "cm_sections_present": present,
        "cm_sections_total": total,
        "prompt": _section_prompt(current),
        "ask_tone": ask_tone,
        "same_cm_draft": True,
        "action": action,
    }
    return ToolResult(ok=True, name="setup_next_step", data=data)
