"""App-owned Meta DM/Comments AI switches. Independent of Meta subscriptions."""

from __future__ import annotations

from services.ai_setup.actions import load_actions_section
from services.integrations.channel_capability_state import action_id_for


def meta_dm_replies_enabled(*, tenant_id: str, platform: str) -> bool:
    """True when the owner left Messages ON for this connected channel.

    Unpublished tenants keep current live DM behavior. A published Actions
    section is the switch: off means the AI must not reply. A published
    section that never stored this DM action keeps DMs on — only an explicit
    enabled=False is off.
    """

    action_id = action_id_for(platform, "dm")
    if not action_id:
        return False
    actions = load_actions_section(tenant_id)
    if actions is None:
        return True
    for item in actions.items:
        if item.id == action_id:
            return bool(item.enabled)
    return True
