"""App-owned Meta DM/Comments AI switches. Independent of Meta subscriptions."""

from __future__ import annotations

from services.channel_capability_state import action_id_for
from services.cm.actions import action_enabled, load_actions_section


def meta_dm_replies_enabled(*, tenant_id: str, platform: str) -> bool:
    """True when the owner left Messages ON for this connected channel.

    Unpublished tenants keep current live DM behavior. A published Actions
    section is the switch: off means the AI must not reply.
    """

    action_id = action_id_for(platform, "dm")
    if not action_id:
        return False
    actions = load_actions_section(tenant_id)
    if actions is None:
        return True
    return action_enabled(actions, action_id)
