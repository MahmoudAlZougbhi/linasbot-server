"""Live human-control checks. Firestore/DB misses do not invent a takeover."""

from __future__ import annotations

from services.customer_ai.contracts.turn import CustomerTurn


def live_handoff_active(*, user_id: str, conversation_id: str = "") -> bool:
    uid = (user_id or "").strip()
    if not uid:
        return False
    try:
        import config

        table = getattr(config, "user_in_human_takeover_mode", None) or {}
        if bool(table.get(uid)):
            return True
        from utils.utils_takeover import iter_conversation_parent_user_ids_for_firestore

        for variant in iter_conversation_parent_user_ids_for_firestore(uid):
            if bool(table.get(variant)):
                return True
    except Exception:
        pass
    _ = conversation_id
    return False


def apply_live_control(turn: CustomerTurn) -> CustomerTurn:
    if turn.state.handoff_active:
        return turn
    if live_handoff_active(user_id=turn.customer_id, conversation_id=turn.conversation_id):
        state = turn.state.model_copy(update={"handoff_active": True})
        return turn.model_copy(update={"state": state})
    return turn
