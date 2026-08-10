"""Real account readiness signals for System Copilot greetings and context."""

from __future__ import annotations

from typing import Any, Literal

SetupStage = Literal[
    "new",
    "cm_partial",
    "cm_ready_no_integration",
    "fully_configured",
]


def compute_cm_progress(tenant_id: str) -> dict[str, Any]:
    """CM readiness from real draft fill quality (shared SoT with progress UI)."""
    from services.cm.progress import progress_summary

    summary = progress_summary(tenant_id, create_missing=False)
    present = int(summary.get("complete") or 0)
    total = int(summary.get("total") or 0)
    remaining = list(summary.get("remaining_sections") or [])
    published = bool(summary.get("published"))
    return {
        "sections_total": total,
        "sections_present": present,
        "sections_missing": remaining,
        "sections_filled": list(summary.get("filled_sections") or []),
        "sections_weak": list(summary.get("weak_sections") or []),
        "sections_truly_missing": list(summary.get("missing_sections") or []),
        "published": published,
        "draft_ratio": (present / total) if total else 0.0,
        "percent": int(summary.get("percent") or 0),
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

    fill_plan_brief: dict[str, Any] | None = None
    try:
        from services.cm.fill_plan import load_fill_plan, refresh_plan_from_progress

        raw = load_fill_plan(tenant_id, user_id)
        if raw:
            refreshed = refresh_plan_from_progress(raw, tenant_id)
            fill_plan_brief = {
                "active": refreshed.get("status") == "active",
                "current_section": refreshed.get("current_section"),
                "remaining_count": len(refreshed.get("remaining") or []),
                "done_count": len(refreshed.get("done") or []),
            }
    except Exception:
        fill_plan_brief = None

    return {
        "setup_stage": stage,
        "cm": {
            "sections_present": cm.get("sections_present"),
            "sections_total": cm.get("sections_total"),
            "percent": cm.get("percent"),
            "published": cm.get("published"),
            # Do not dump full CM payloads.
            "done_sample": (cm.get("sections_filled") or [])[:6],
            "missing_sample": (cm.get("sections_missing") or [])[:6],
            "weak_sample": (cm.get("sections_weak") or [])[:4],
            "done_rule": "Never re-ask or re-propose edits for done/filled sections unless the owner explicitly requests a change.",
        },
        "cm_fill_plan": fill_plan_brief,
        "integrations": {
            "any_connected": integ.get("any_connected"),
            "meta_dm_live_verified": integ.get("meta_dm_live_verified"),
        },
        "plan": plan,
        "wallet": wallet,
        "profile": profile,
    }
