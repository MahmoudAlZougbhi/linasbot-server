"""Real account readiness signals for System Copilot greetings and context."""

from __future__ import annotations

from typing import Any, Literal

SetupStage = Literal[
    "new",
    "cm_partial",
    "cm_ready_no_integration",
    "fully_configured",
]


def _section_present(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    return bool(item.get("exists") or item.get("present"))


def compute_cm_progress(tenant_id: str) -> dict[str, Any]:
    from services.cm.constants import CM_SECTIONS, tenant_has_published_cm
    from services.cm.storage import list_sections

    listed = {str(item.get("section")): item for item in list_sections(tenant_id=tenant_id)}
    present = 0
    missing: list[str] = []
    for sec in CM_SECTIONS:
        item = listed.get(sec)
        if _section_present(item if isinstance(item, dict) else None):
            present += 1
        else:
            missing.append(sec)
    total = len(CM_SECTIONS)
    published = tenant_has_published_cm(tenant_id)
    return {
        "sections_total": total,
        "sections_present": present,
        "sections_missing": missing,
        "published": published,
        "draft_ratio": (present / total) if total else 0.0,
    }


def compute_integration_summary(tenant_id: str) -> dict[str, Any]:
    from services.integration_capabilities import list_tenant_integration_status

    rows = list_tenant_integration_status(tenant_id)
    connected = False
    meta_live_dm = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("connected") is True:
            connected = True
        caps = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
        dm = caps.get("dm_reply") if isinstance(caps, dict) else None
        if isinstance(dm, dict) and (dm.get("live_verified") is True or dm.get("level") == "connected"):
            meta_live_dm = True
    return {
        "any_connected": connected,
        "meta_dm_live_verified": meta_live_dm,
        "platforms": [
            {
                "platform": r.get("platform"),
                "connected": bool(r.get("connected")),
            }
            for r in rows
            if isinstance(r, dict)
        ],
    }


def resolve_setup_stage(tenant_id: str) -> SetupStage:
    cm = compute_cm_progress(tenant_id)
    integ = compute_integration_summary(tenant_id)
    present = int(cm.get("sections_present") or 0)
    published = bool(cm.get("published"))
    connected = bool(integ.get("any_connected"))

    if present <= 1 and not published:
        return "new"
    if not published and present < max(4, int(cm.get("sections_total") or 15) // 2):
        return "cm_partial"
    if published or present >= max(4, int(cm.get("sections_total") or 15) // 2):
        if not connected:
            return "cm_ready_no_integration"
        return "fully_configured"
    return "cm_partial"


def build_account_summary(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    from services.owner_ai_profile import read_owner_profile

    cm = compute_cm_progress(tenant_id)
    integ = compute_integration_summary(tenant_id)
    stage = resolve_setup_stage(tenant_id)
    profile = read_owner_profile(user_id)
    plan: dict[str, Any] = {}
    wallet: dict[str, Any] = {}
    try:
        from services.entitlements_service import get_tenant_entitlement_public

        plan = get_tenant_entitlement_public(tenant_id)
    except Exception:
        plan = {"available": False}
    try:
        from services.token_wallet_service import token_wallet_service

        wallet = token_wallet_service.get_wallet(tenant_id).to_public_dict()
    except Exception:
        wallet = {"available": False}
    return {
        "setup_stage": stage,
        "cm": {
            "sections_present": cm.get("sections_present"),
            "sections_total": cm.get("sections_total"),
            "published": cm.get("published"),
            # Do not dump full CM payloads.
            "missing_sample": (cm.get("sections_missing") or [])[:5],
        },
        "integrations": {
            "any_connected": integ.get("any_connected"),
            "meta_dm_live_verified": integ.get("meta_dm_live_verified"),
        },
        "plan": plan,
        "wallet": wallet,
        "profile": profile,
    }
