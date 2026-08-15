"""Compose the tenant-scoped mobile Dashboard payload from canonical services."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from services.billing_backend import billing_uses_postgres
from services.credit_ai_gate import remaining_credits, upgrade_plan_allowed
from services.credit_ledger_service import credit_ledger_service
from services.entitlements_service import (
    get_tenant_entitlement_public,
    is_subscription_exempt_tenant,
)
from services.membership.plan_catalog import PLAN_CATALOG
from services.owner_ai_account_state import compute_cm_progress
from services.plan_economics import PLAN_PRICES_USD, recommend_allowance
from services.platform_owner_service import PlatformOwnerService
from services.tenant_mobile_dashboard.activity import build_activity_summary
from services.tenant_mobile_dashboard.channels import build_channel_breakdown
from services.tenant_mobile_dashboard.periods import (
    PeriodValidationError,
    TimezoneValidationError,
    iso_z,
    parse_period,
    parse_timezone,
    resolve_period_window,
)
from services.tenant_mobile_dashboard.status import build_alerts, derive_workspace_status
from services.tenant_mobile_dashboard.usage import aggregate_tenant_usage

platform_owner_service = PlatformOwnerService()


def _section_ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"availability": "ok", **data}


def _section_error(code: str, message: str) -> dict[str, Any]:
    return {"availability": "error", "error_code": code, "message": message}


def _section_unavailable(code: str, message: str) -> dict[str, Any]:
    return {"availability": "unavailable", "error_code": code, "message": message}


def _workspace_identity(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    name: str | None = None
    try:
        from services.user_service import user_service

        user = user_service.get_user_by_id(user_id)
        if isinstance(user, dict):
            raw = user.get("businessName") or user.get("business_name") or user.get("name")
            if isinstance(raw, str) and raw.strip():
                name = raw.strip()[:120]
    except Exception:
        name = None
    return {
        "tenant_id": tenant_id,
        "workspace_name": name or tenant_id,
        "workspace_name_source": "user_profile" if name else "tenant_id",
    }


def _plan_and_credits(tenant_id: str) -> dict[str, Any]:
    try:
        public = get_tenant_entitlement_public(tenant_id)
        available = remaining_credits(tenant_id)
        reserved = int(credit_ledger_service.get_reserved(tenant_id))
    except Exception as exc:
        return _section_error("credits_unavailable", f"Credit service unavailable: {exc}")

    plan_id = str(public.get("plan_id") or "none")
    included = int(public.get("included_credits") or 0)
    extra = int(public.get("extra_credits") or 0)
    if included <= 0 and plan_id in PLAN_PRICES_USD:
        included = int(recommend_allowance(plan_id).included_credits)
    limit = included + extra
    if limit <= 0:
        limit = available + reserved
    used = max(0, limit - available - reserved) if limit > 0 else 0
    catalog = PLAN_CATALOG.get(plan_id)
    display_name = catalog.display_name if catalog else (plan_id if plan_id != "none" else None)

    # Never coerce missing subscription into a fake zero plan name.
    has_subscription = plan_id not in {"", "none"} or bool(public.get("subscription_exempt"))

    return _section_ok(
        {
            "plan_id": plan_id if has_subscription else None,
            "plan_name": display_name,
            "subscription_status": public.get("status"),
            "subscription_exempt": bool(public.get("subscription_exempt")),
            "app_access": bool(public.get("app_access")),
            "current_period_end": iso_z(public.get("current_period_end")),
            "current_period_end_ts": public.get("current_period_end"),
            "included_credits": included,
            "purchased_or_promotional_credits": extra,
            "reserved_credits": reserved,
            "available_credits": available,
            "total_available_credits": available,
            "credits_consumed_period_estimate": used,
            "credits_limit": limit,
            "usage_progress_ratio": (used / included) if included > 0 else None,
            "features": dict(public.get("features") or {}),
            "faq_enabled": public.get("faq_enabled"),
            "faq_max_entries": public.get("faq_max_entries"),
            "faq_used_entries": public.get("faq_used_entries"),
            "faq_quota_display": public.get("faq_quota_display"),
            "credit_source": "postgres_credit_ledger" if billing_uses_postgres() else "file_credit_ledger",
            "credit_source_note": (
                "Remaining credits are the credit-ledger available balance — the same wallet "
                "that gates Owner Copilot and channel AI."
            ),
            "has_subscription": has_subscription,
            "actions": {
                "manage_subscription": True,
                "upgrade_plan": upgrade_plan_allowed(plan_id),
                "buy_credits": True,
            },
        }
    )


def _content_readiness(tenant_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    try:
        cm = compute_cm_progress(tenant_id)
        last_published: str | None = None
        try:
            from services.cm.version_store import read_published_pointer

            pointer = read_published_pointer(tenant_id)
            if pointer and pointer.updated_at is not None:
                last_published = pointer.updated_at.isoformat().replace("+00:00", "Z")
        except Exception:
            last_published = None
        off_days_status = "unknown"
        try:
            rows = cm  # progress already computed
            missing = set(rows.get("sections_truly_missing") or [])
            weak = set(rows.get("sections_weak") or [])
            if "off_days" in missing:
                off_days_status = "missing"
            elif "off_days" in weak:
                off_days_status = "incomplete"
            elif "off_days" in set(rows.get("sections_filled") or []):
                off_days_status = "configured"
        except Exception:
            off_days_status = "unknown"
        return _section_ok(
            {
                "percent": int(cm.get("percent") or 0),
                "sections_present": int(cm.get("sections_present") or 0),
                "sections_total": int(cm.get("sections_total") or 0),
                "published": bool(cm.get("published")),
                "draft_vs_published": "published" if cm.get("published") else "draft",
                "last_published_at": last_published,
                "missing_sections": list(cm.get("sections_missing") or [])[:12],
                "weak_sections": list(cm.get("sections_weak") or [])[:8],
                "off_days_status": off_days_status,
                "faq_used": plan.get("faq_used_entries") if plan.get("availability") == "ok" else None,
                "faq_max": plan.get("faq_max_entries") if plan.get("availability") == "ok" else None,
                "faq_quota_display": plan.get("faq_quota_display") if plan.get("availability") == "ok" else None,
                "actions": {
                    "continue_setup": not bool(cm.get("published")) or int(cm.get("percent") or 0) < 100,
                    "open_cm": True,
                    "review_faq": True,
                    "publish_changes": not bool(cm.get("published")),
                },
            }
        )
    except Exception as exc:
        return _section_error("cm_progress_unavailable", str(exc))


def _team_capacity(tenant_id: str, plan_id: str | None) -> dict[str, Any]:
    seats = None
    unlimited = False
    if plan_id and plan_id in PLAN_CATALOG:
        seats = PLAN_CATALOG[plan_id].additional_seats
        unlimited = seats is None
    try:
        from services.user_service import user_service

        users = [u for u in user_service.get_all_users() if str(u.get("tenantId") or "").strip().lower() == tenant_id]
    except Exception as exc:
        return _section_error("users_unavailable", str(exc))

    owners = [u for u in users if str(u.get("role") or "").lower() in {"owner", "admin", "tenant_owner"}]
    # Prefer explicit owner; otherwise treat first active user as owner for seat math.
    owner = owners[0] if owners else (users[0] if users else None)
    owner_id = str(owner.get("id") or "") if owner else ""
    additional = [
        u
        for u in users
        if str(u.get("id") or "") != owner_id and str(u.get("status") or "active").lower() != "disabled"
    ]
    active_additional = len(additional)
    # Invitation system is not implemented — report honestly.
    pending_invitations = 0
    remaining = (
        None if unlimited else (None if seats is None else max(0, int(seats) - active_additional - pending_invitations))
    )
    return _section_ok(
        {
            "owner": {
                "id": owner_id or None,
                "name": (owner.get("name") or owner.get("displayName") or owner.get("email")) if owner else None,
                "email": owner.get("email") if owner else None,
            },
            "active_additional_users": active_additional,
            "pending_invitations": pending_invitations,
            "pending_invitations_source": "none",
            "pending_invitations_note": (
                "Tenant invitations are not implemented yet; pending invitation count is always 0."
            ),
            "additional_seat_allowance": seats,
            "additional_seats_unlimited": unlimited,
            "remaining_seats": remaining,
            "actions": {"manage_users": True},
        }
    )


def build_tenant_mobile_dashboard(
    *,
    tenant_id: str,
    user_id: str,
    period_raw: str | None = None,
    timezone_raw: str | None = None,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> dict[str, Any]:
    generated_at_ts = time.time()
    generated_at = iso_z(generated_at_ts) or ""
    tid = (tenant_id or "").strip().lower()
    if not tid:
        raise ValueError("tenant_id required")

    try:
        period = parse_period(period_raw)
        tz = parse_timezone(timezone_raw)
    except (PeriodValidationError, TimezoneValidationError):
        raise

    plan = _plan_and_credits(tid)
    period_end_ts = plan.get("current_period_end_ts") if plan.get("availability") == "ok" else None
    window = resolve_period_window(
        period=period,
        tz=tz,
        current_period_end=period_end_ts,
        custom_start=custom_start,
        custom_end=custom_end,
    )

    try:
        usage = aggregate_tenant_usage(tid, start_ts=float(window["start_ts"]), end_ts=float(window["end_ts"]))
        usage_section = (
            _section_ok(usage)
            if usage.get("status") == "ok"
            else {
                "availability": "empty",
                **usage,
            }
        )
    except Exception as exc:
        usage_section = _section_error("usage_unavailable", str(exc))
        usage = {
            "instagram_dms": None,
            "facebook_dms": None,
            "instagram_comments": None,
            "facebook_comments": None,
        }

    features = dict(plan.get("features") or {}) if plan.get("availability") == "ok" else {}
    try:
        channels = build_channel_breakdown(
            tid,
            features=features,
            usage=usage_section if usage_section.get("availability") in {"ok", "empty"} else usage,
        )
        channels_section = _section_ok(channels)
    except Exception as exc:
        channels_section = _section_error("channels_unavailable", str(exc))
        channels = {
            "any_connected": False,
            "connection_issue": False,
            "dm_operational": False,
            "channels": [],
        }

    content = _content_readiness(tid, plan)
    team = _team_capacity(tid, plan.get("plan_id") if plan.get("availability") == "ok" else None)

    credits_known = plan.get("availability") == "ok"
    available = int(plan["available_credits"]) if credits_known else None
    included = int(plan.get("included_credits") or 0) if credits_known else 0
    suspended = platform_owner_service.is_suspended(tid)
    cm_published = bool(content.get("published")) if content.get("availability") == "ok" else False
    cm_percent = int(content.get("percent") or 0) if content.get("availability") == "ok" else 0
    cm_has_draft = content.get("availability") == "ok" and (
        int(content.get("sections_present") or 0) > 0 or int(content.get("percent") or 0) > 0
    )

    workspace_status = derive_workspace_status(
        suspended=suspended,
        plan_id=str(plan.get("plan_id") or "none") if credits_known else "none",
        subscription_status=str(plan.get("subscription_status") or "none") if credits_known else "none",
        subscription_exempt=bool(plan.get("subscription_exempt"))
        if credits_known
        else is_subscription_exempt_tenant(tid),
        available_credits=available,
        included_credits=included,
        credits_known=credits_known,
        cm_published=cm_published,
        cm_percent=cm_percent,
        any_connected=bool(channels.get("any_connected")),
        connection_issue=bool(channels.get("connection_issue")),
        dm_ok=bool(channels.get("dm_operational")),
    )

    faq_used = plan.get("faq_used_entries") if credits_known else None
    faq_max = plan.get("faq_max_entries") if credits_known else None
    seats_remaining = team.get("remaining_seats") if team.get("availability") == "ok" else None
    seats_unlimited = bool(team.get("additional_seats_unlimited")) if team.get("availability") == "ok" else False

    alerts = build_alerts(
        workspace_status=workspace_status,
        available_credits=available,
        credits_known=credits_known,
        included_credits=included,
        subscription_status=str(plan.get("subscription_status") or "none") if credits_known else "none",
        cm_published=cm_published,
        cm_has_draft_progress=bool(cm_has_draft),
        faq_used=int(faq_used) if isinstance(faq_used, int) else None,
        faq_max=int(faq_max) if isinstance(faq_max, int) else None,
        seats_remaining=seats_remaining if isinstance(seats_remaining, int) else None,
        seats_unlimited=seats_unlimited,
        channels=list(channels.get("channels") or []),
        generated_at=generated_at,
    )

    distribution = None
    if usage_section.get("availability") in {"ok", "empty"}:
        distribution = {
            "availability": usage_section.get("availability"),
            "mode_default": "interactions",
            "modes_supported": ["interactions"],
            "credits_mode_available": False,
            "credits_mode_note": usage_section.get("credits_by_bucket_note"),
            "items": usage_section.get("distribution") or [],
            "total_interactions": usage_section.get("total_interactions"),
        }
    else:
        distribution = _section_unavailable(
            "usage_distribution_unavailable", "Usage distribution depends on interaction logs."
        )

    smart_followup_section: dict[str, Any]
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.whatsapp_cloud.smart_followup.analytics import build_smart_followup_analytics

        start_dt = datetime.fromtimestamp(float(window["start_ts"]), tz=UTC)
        end_dt = datetime.fromtimestamp(float(window["end_ts"]), tz=UTC)
        with whatsapp_session() as wa_db:
            analytics = build_smart_followup_analytics(
                wa_db,
                tenant_id=tid,
                start=start_dt,
                end=end_dt,
                timezone_name=str(window["timezone"]),
            )
        smart_followup_section = _section_ok(analytics.get("metrics") or {})
    except WhatsAppDatabaseUnavailable:
        smart_followup_section = _section_unavailable(
            "WHATSAPP_DB_UNAVAILABLE",
            "WhatsApp Cloud database is not configured",
        )
    except Exception as exc:
        # Honest error — never invent zero metrics when the API fails.
        smart_followup_section = _section_error("smart_followup_unavailable", str(exc))

    try:
        from services.integration_capabilities import list_tenant_integration_status

        integration_rows = list_tenant_integration_status(tid)
        activity_summary = build_activity_summary(
            tid,
            start_ts=float(window["start_ts"]),
            end_ts=float(window["end_ts"]),
            integrations=integration_rows,
        )
    except Exception as exc:
        activity_summary = _section_error("activity_unavailable", str(exc))

    partial_failures = [
        key
        for key, section in {
            "plan_and_credits": plan,
            "usage": usage_section,
            "channels": channels_section,
            "content_readiness": content,
            "team_capacity": team,
            "smart_followup": smart_followup_section,
            "activity_summary": activity_summary,
        }.items()
        if section.get("availability") == "error"
    ]

    return {
        "success": True,
        "generated_at": generated_at,
        "period": {
            "id": window["period"],
            "label": window["label"],
            "timezone": window["timezone"],
            "start": window["start"],
            "end": window["end"],
            "custom_start": custom_start if period == "custom" else None,
            "custom_end": custom_end if period == "custom" else None,
        },
        "workspace": _workspace_identity(tenant_id=tid, user_id=user_id),
        "workspace_status": workspace_status,
        "plan_and_credits": plan,
        "usage_summary": usage_section,
        "usage_distribution": distribution,
        "channels": channels_section,
        "activity_summary": activity_summary,
        "content_readiness": content,
        "team_capacity": team,
        "smart_followup": smart_followup_section,
        "alerts": alerts,
        "partial_failures": partial_failures,
        "privacy": {
            "excludes_openai_usd": True,
            "excludes_global_owner_metrics": True,
            "excludes_other_tenants": True,
            "excludes_company_profit_fields": True,
        },
    }
