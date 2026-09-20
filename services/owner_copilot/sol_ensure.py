"""Publish seed Sol identity when Live sol_basics is missing. Idempotent."""

from __future__ import annotations

import logging

from services.owner_copilot.sol_identity import load_sol_identity, sol_basics_configured
from services.owner_copilot.sol_seed import default_sol_app_knowledge_payload, default_sol_basics_payload

log = logging.getLogger("owner_copilot.sol_ensure")


def _payload_dict(envelope: object) -> dict:
    raw = getattr(envelope, "payload", None)
    return dict(raw) if isinstance(raw, dict) else {}


async def ensure_published_sol_basics(tenant_id: str) -> bool:
    """Make seed sol_basics Live when unpublished/empty. True when Sol can run."""
    tid = (tenant_id or "").strip()
    if not tid:
        return False
    if bool(load_sol_identity(tid).get("configured")):
        return True
    try:
        return await _publish_seed(tid)
    except Exception:
        log.exception("sol_ensure failed tenant=%s", tid)
        return bool(load_sol_identity(tid).get("configured"))


async def _publish_seed(tenant_id: str) -> bool:
    from services.ai_setup.constants import cm_emergency_disable_publish, cm_publish_enabled
    from services.ai_setup.save_live import go_live_saved_section
    from services.ai_setup.storage import get_draft, put_draft

    if cm_emergency_disable_publish() or not cm_publish_enabled():
        log.warning("sol_ensure skipped: publish disabled tenant=%s", tenant_id)
        return False

    basics = get_draft("sol_basics", tenant_id=tenant_id, create_default=True)
    if not sol_basics_configured(_payload_dict(basics)):
        put_draft(
            "sol_basics",
            payload=default_sol_basics_payload(),
            if_match=str(getattr(basics, "etag", "") or "*"),
            tenant_id=tenant_id,
            updated_by="sol_ensure",
            allow_create=True,
        )
    knowledge = get_draft("sol_app_knowledge", tenant_id=tenant_id, create_default=True)
    items = _payload_dict(knowledge).get("items")
    if not (isinstance(items, list) and items):
        put_draft(
            "sol_app_knowledge",
            payload=default_sol_app_knowledge_payload(),
            if_match=str(getattr(knowledge, "etag", "") or "*"),
            tenant_id=tenant_id,
            updated_by="sol_ensure",
            allow_create=True,
        )

    activation = await go_live_saved_section(
        tenant_id=tenant_id,
        section="sol_basics",
        actor_id="sol_ensure",
        notes="auto_seed_sol_basics",
    )
    if not activation.get("live"):
        log.warning(
            "sol_ensure publish failed tenant=%s reason=%s",
            tenant_id,
            activation.get("reason") or activation.get("message") or "unknown",
        )
        return bool(load_sol_identity(tenant_id).get("configured"))

    await go_live_saved_section(
        tenant_id=tenant_id,
        section="sol_app_knowledge",
        actor_id="sol_ensure",
        notes="auto_seed_sol_app_knowledge",
    )
    return bool(load_sol_identity(tenant_id).get("configured"))
