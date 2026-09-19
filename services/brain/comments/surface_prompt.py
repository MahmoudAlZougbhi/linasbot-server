"""Terra-facing public-comment surface contract. Not customer copy. Not a gate."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.turn import CustomerTurn

COMMENT_SURFACE_BLOCK = """COMMENT_SURFACE
You are replying on a PUBLIC social comment thread (Instagram / Facebook / TikTok comment), NOT a private DM chat.
Write like a short public comment: concise, scannable, 1-3 short sentences unless Comment Rules / STYLE explicitly ask otherwise.
Do not write long multi-paragraph DM counseling, soft field collection, or private intake on the public thread.
Honor comment_mode in POLICY:
- ai_comment → public comment text only (destination will be comment).
- ai_dm → private DM continuation; do not claim a public filing.
- ai_both → optional short public ack + DM continuation; never claim a private message was sent unless that DM text is actually being sent.
Never invent "Sent you a DM." or any canned system copy.
Still obey EVIDENCE / RECEIPTS / RULES / IDENTITY / STYLE / Comment Rules.
Comment Rules + STYLE win on wording/tone; COMMENT_SURFACE wins on channel behavior (public vs private, length, no PII harvest)."""

_COMMENT_SYSTEM = "You are writing a PUBLIC social comment reply, not a private DM chat. Keep it short and scannable."

_MODE_NOTES = {
    "ai_comment": "AI comment mode=ai_comment. Public comment text only. Do not use canned system copy such as 'Sent you a DM.'",
    "ai_dm": "AI comment mode=ai_dm. Private DM continuation; do not claim a public filing. Do not use canned system copy such as 'Sent you a DM.'",
    "ai_both": (
        "AI comment mode=ai_both. Optional short public ack plus DM continuation. "
        "Never claim a private message was sent unless that DM text is actually being sent. "
        "Do not use canned system copy such as 'Sent you a DM.'"
    ),
}

_TIKTOK_NOTE = "This is TikTok: write a public comment only. Never claim a private message was sent."


def is_comment_generate_surface(turn: object | None = None, *, surface: str = "", invocation_kind: str = "") -> bool:
    surf = str(surface or getattr(turn, "surface", "") or "").strip().lower()
    kind = str(invocation_kind or getattr(turn, "invocation_kind", "") or "").strip().lower()
    return surf == "comment" or kind == "comment"


def comment_surface_block(
    turn: object | None = None,
    *,
    surface: str = "",
    invocation_kind: str = "",
) -> str:
    if not is_comment_generate_surface(turn, surface=surface, invocation_kind=invocation_kind):
        return ""
    return COMMENT_SURFACE_BLOCK


def comment_system_addon(
    turn: object | None = None,
    *,
    surface: str = "",
    invocation_kind: str = "",
) -> str:
    if not is_comment_generate_surface(turn, surface=surface, invocation_kind=invocation_kind):
        return ""
    return _COMMENT_SYSTEM


def comment_surface_policy_notes(turn: CustomerTurn) -> list[str]:
    if not is_comment_generate_surface(turn):
        return []
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    notes: list[str] = []
    mode = str(extra.get("comment_mode") or "").strip()
    mode_note = _MODE_NOTES.get(mode)
    if mode_note:
        notes.append(mode_note)
    elif mode.startswith("ai"):
        notes.append(
            f"AI comment mode={mode}. Write customer-facing wording from Comment Rules and Style. "
            "Do not use canned system copy such as 'Sent you a DM.'"
        )
    channel = str(getattr(turn, "channel", "") or extra.get("comment_channel") or "").lower()
    if "tiktok" in channel:
        notes.append(_TIKTOK_NOTE)
    if extra.get("parent_is_page"):
        from services.brain.comments.thread_parent import JOINER_POLICY_NOTE

        notes.append(JOINER_POLICY_NOTE)
    return notes


def merge_policy_notes(*groups: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            text = str(raw or "").strip()
            if not text:
                continue
            key = " ".join(text.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text[:1200])
    return out


def history_lines_for_prompt(turn: CustomerTurn) -> list[str]:
    """Comment HISTORY is the public thread stored on this conversation id."""
    return [f"{item.role}: {item.text}" for item in turn.history.messages]


def extra_policy_notes(turn: CustomerTurn) -> list[str]:
    extra: dict[str, Any] = turn.extra if isinstance(turn.extra, dict) else {}
    return [str(item).strip() for item in (extra.get("policy_notes") or []) if str(item).strip()]
