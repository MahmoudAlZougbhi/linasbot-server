"""Live human-control checks. Firestore/DB misses do not invent a takeover."""

from __future__ import annotations

from services.customer_ai.contracts.turn import CustomerTurn


def _id_variants(user_id: str) -> list[str]:
    uid = (user_id or "").strip()
    if not uid:
        return []
    out = [uid]
    try:
        from utils.utils_takeover import iter_conversation_parent_user_ids_for_firestore

        out.extend(iter_conversation_parent_user_ids_for_firestore(uid))
    except Exception:
        pass
    seen: list[str] = []
    for item in out:
        key = str(item or "").strip()
        if key and key not in seen:
            seen.append(key)
    return seen


def _local_takeover(user_id: str) -> bool:
    try:
        import config

        table = getattr(config, "user_in_human_takeover_mode", None) or {}
        return any(bool(table.get(key)) for key in _id_variants(user_id))
    except Exception:
        return False


def _shared_takeover(user_id: str) -> bool:
    try:
        from services.scale.conversation_state_redis import get_takeover
    except Exception:
        return False
    for key in _id_variants(user_id):
        try:
            remote = get_takeover(key)
        except Exception:
            remote = None
        if remote is True:
            return True
    return False


def live_handoff_active(*, user_id: str, conversation_id: str = "") -> bool:
    uid = (user_id or "").strip()
    if not uid:
        return False
    if _local_takeover(uid) or _shared_takeover(uid):
        return True
    _ = conversation_id
    return False


def apply_live_control(turn: CustomerTurn) -> CustomerTurn:
    active = live_handoff_active(user_id=turn.customer_id, conversation_id=turn.conversation_id)
    if active == turn.state.handoff_active:
        return turn
    return turn.model_copy(update={"state": turn.state.model_copy(update={"handoff_active": active})})
