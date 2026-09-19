"""escalate_to_human via existing Live Chat takeover persistence."""

from __future__ import annotations

from services.brain.contracts.actions import ActionProposal, ActionReceipt


async def escalate_to_human(
    *,
    proposal: ActionProposal,
    user_id: str,
    conversation_id: str,
) -> ActionReceipt:
    if not user_id or not conversation_id:
        return ActionReceipt(
            action_id=f"handoff:{proposal.task_id}",
            action_type="escalate_to_human",
            state="failure",
            reason="missing_conversation",
        )
    try:
        from utils.utils_takeover import set_human_takeover_status

        result = await set_human_takeover_status(
            user_id,
            conversation_id,
            True,
            force_waiting_queue=True,
        )
    except Exception:
        return ActionReceipt(
            action_id=f"handoff:{proposal.task_id}",
            action_type="escalate_to_human",
            state="failure",
            reason="handoff_persist_failed",
        )
    if result is None:
        return ActionReceipt(
            action_id=f"handoff:{proposal.task_id}",
            action_type="escalate_to_human",
            state="unknown",
            reason="handoff_unconfirmed",
        )
    try:
        from utils.utils_livechat_hooks import _refresh_live_chat_index_async

        _refresh_live_chat_index_async(user_id, conversation_id)
    except Exception:
        pass
    return ActionReceipt(
        action_id=f"handoff:{proposal.task_id}",
        action_type="escalate_to_human",
        state="success",
        backend_id=conversation_id,
        revision=str(proposal.expected_revision or ""),
    )
