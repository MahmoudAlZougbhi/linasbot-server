"""Mark Meta bindings disconnected after Graph invalidates the login session."""

from __future__ import annotations

import time
from typing import Any

from services.meta_app_registry_common import MetaBindingNotFoundError

PASSWORD_CHANGED_RECONNECT = "password_changed_reconnect"
SESSION_INVALIDATED_ACTOR = "meta-session-invalidated"


class MetaAppRegistrySessionMixin:
    """Persist a password/session-invalidated disconnect on one binding."""

    _append_audit: Any
    _binding_from_dict: Any
    _locked: Any
    _read_unlocked: Any
    _write_unlocked: Any

    def mark_binding_session_invalidated(
        self,
        binding_id: str,
        *,
        actor_id: str = SESSION_INVALIDATED_ACTOR,
    ) -> Any:
        bid = str(binding_id or "").strip()
        if not bid:
            raise MetaBindingNotFoundError("binding not found")
        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(bid)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            already = (
                current.status == "disconnected"
                and str(current.webhook_subscription_error or "") == PASSWORD_CHANGED_RECONNECT
            )
            if already:
                return current
            if current.status == "disconnected":
                return current
            raw = dict(raw)
            raw["status"] = "disconnected"
            raw["webhook_subscription_error"] = PASSWORD_CHANGED_RECONNECT
            raw["generation"] = current.generation + 1
            raw["updated_at"] = time.time()
            state["bindings"][bid] = raw
            self._write_unlocked(state)
            updated = self._binding_from_dict(raw)
            self._append_audit(
                {
                    "event": "binding_session_invalidated",
                    "actor_id": actor_id,
                    "tenant_id": current.tenant_id,
                    "channel": current.channel,
                    "asset_id": current.asset_id,
                    "app_key": current.app_key,
                    "binding_id": current.binding_id,
                    "reason": PASSWORD_CHANGED_RECONNECT,
                }
            )
            return updated
