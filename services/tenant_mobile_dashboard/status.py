"""Workspace status reason codes and tenant alerts for mobile dashboard."""

from __future__ import annotations

from typing import Any

LOW_CREDIT_RATIO = 0.10
LOW_CREDIT_ABSOLUTE = 100


def _plan_allows_comments(features: dict[str, Any]) -> bool:
    return bool(features.get("comment_automation"))


def derive_workspace_status(
    *,
    suspended: bool,
    plan_id: str,
    subscription_status: str,
    subscription_exempt: bool,
    available_credits: int | None,
    included_credits: int,
    credits_known: bool,
    cm_published: bool,
    cm_percent: int,
    any_connected: bool,
    connection_issue: bool,
    dm_ok: bool,
) -> dict[str, Any]:
    """Server-derived workspace state — client must not invent Ready."""

    if suspended:
        return {
            "state": "suspended",
            "reason_code": "tenant_suspended",
            "title": "Suspended",
            "explanation": "This workspace is suspended. Contact support for help.",
            "primary_action": {"code": "contact_support", "label": "Contact support"},
        }

    if not subscription_exempt and (
        subscription_status in {"none", "expired", "canceled", "refunded", "revoked"} or plan_id in {"", "none"}
    ):
        return {
            "state": "subscription_issue",
            "reason_code": "subscription_inactive",
            "title": "Subscription issue",
            "explanation": "An active subscription is required to run this workspace.",
            "primary_action": {"code": "renew_subscription", "label": "Renew subscription"},
        }

    if credits_known and available_credits is not None and available_credits <= 0:
        return {
            "state": "credits_depleted",
            "reason_code": "credits_depleted",
            "title": "Credits depleted",
            "explanation": "No credits remain. Buy credits or upgrade to continue AI operations.",
            "primary_action": {"code": "buy_credits", "label": "Buy credits"},
        }

    if connection_issue:
        return {
            "state": "connection_issue",
            "reason_code": "channel_connection_issue",
            "title": "Connection issue",
            "explanation": "A connected channel needs attention before automation can run reliably.",
            "primary_action": {"code": "review_permissions", "label": "Review permissions"},
        }

    if credits_known and available_credits is not None:
        threshold = (
            max(LOW_CREDIT_ABSOLUTE, int(included_credits * LOW_CREDIT_RATIO))
            if included_credits
            else LOW_CREDIT_ABSOLUTE
        )
        if available_credits <= threshold:
            return {
                "state": "credits_low",
                "reason_code": "credits_low",
                "title": "Credits low",
                "explanation": "Credit balance is running low for this billing period.",
                "primary_action": {"code": "buy_credits", "label": "Buy credits"},
            }

    if not cm_published or cm_percent < 50 or not any_connected:
        action = {"code": "complete_setup", "label": "Complete setup"}
        if cm_published and not any_connected:
            action = {"code": "connect_instagram", "label": "Connect Instagram"}
        elif not cm_published and cm_percent >= 50:
            action = {"code": "publish_cm", "label": "Publish Content Management"}
        return {
            "state": "setup_needed",
            "reason_code": "setup_incomplete",
            "title": "Setup needed",
            "explanation": "Finish Content Management and channel connections so customer AI can operate.",
            "primary_action": action,
        }

    if not dm_ok and any_connected:
        return {
            "state": "connection_issue",
            "reason_code": "dm_not_operational",
            "title": "Connection issue",
            "explanation": "Channels are connected but DM automation is not fully operational yet.",
            "primary_action": {"code": "review_permissions", "label": "Review permissions"},
        }

    return {
        "state": "active",
        "reason_code": "workspace_active",
        "title": "Active",
        "explanation": "Your AI workspace is operating with the current plan and connections.",
        "primary_action": None,
    }


def build_alerts(
    *,
    workspace_status: dict[str, Any],
    available_credits: int | None,
    credits_known: bool,
    included_credits: int,
    subscription_status: str,
    cm_published: bool,
    cm_has_draft_progress: bool,
    faq_used: int | None,
    faq_max: int | None,
    seats_remaining: int | None,
    seats_unlimited: bool,
    channels: list[dict[str, Any]],
    generated_at: str,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    def add(
        *,
        severity: str,
        reason_code: str,
        title: str,
        explanation: str,
        action_code: str | None,
        action_label: str | None,
    ) -> None:
        alerts.append(
            {
                "severity": severity,
                "reason_code": reason_code,
                "title": title,
                "explanation": explanation,
                "timestamp": generated_at,
                "action": ({"code": action_code, "label": action_label} if action_code and action_label else None),
            }
        )

    state = str(workspace_status.get("state") or "")
    if state == "credits_depleted":
        add(
            severity="critical",
            reason_code="credits_depleted",
            title="Credits depleted",
            explanation="AI operations will stop until credits are available.",
            action_code="buy_credits",
            action_label="Buy credits",
        )
    elif state == "credits_low" and credits_known and available_credits is not None:
        add(
            severity="warning",
            reason_code="credits_low",
            title="Credits running low",
            explanation=f"{available_credits} credits remain"
            + (f" of {included_credits} included." if included_credits else "."),
            action_code="buy_credits",
            action_label="Buy credits",
        )

    if subscription_status in {"grace", "canceled", "expired"}:
        add(
            severity="warning" if subscription_status == "grace" else "critical",
            reason_code="subscription_renewal_issue",
            title="Subscription needs attention",
            explanation=f"Subscription status is {subscription_status}.",
            action_code="renew_subscription",
            action_label="Manage subscription",
        )

    for ch in channels:
        platform = str(ch.get("platform") or "")
        connected = bool(ch.get("connected"))
        if not connected:
            continue
        dm = ch.get("dm") if isinstance(ch.get("dm"), dict) else {}
        comments = ch.get("comments") if isinstance(ch.get("comments"), dict) else {}
        if dm.get("operational") and not comments.get("operational"):
            blocker = str(comments.get("blocker_code") or "comments_unavailable")
            add(
                severity="warning",
                reason_code=f"{platform}_dms_ok_comments_blocked",
                title=f"{platform.title()} comments need attention",
                explanation=str(comments.get("blocker_message") or "DMs work but comments are not ready."),
                action_code="review_permissions"
                if "permission" in blocker or "scope" in blocker
                else "manage_integrations",
                action_label="Review permissions"
                if "permission" in blocker or "scope" in blocker
                else "Manage integrations",
            )
        if connected and not bool(dm.get("connection_healthy", True)):
            add(
                severity="critical",
                reason_code=f"{platform}_disconnected_or_unhealthy",
                title=f"{platform.title()} connection issue",
                explanation=str(dm.get("blocker_message") or "Channel connection is not healthy."),
                action_code="review_permissions",
                action_label="Review permissions",
            )

    if cm_has_draft_progress and not cm_published:
        add(
            severity="info",
            reason_code="cm_unpublished_changes",
            title="Content changes waiting to publish",
            explanation="Publish Content Management so customer AI uses your latest setup.",
            action_code="publish_cm",
            action_label="Publish changes",
        )

    if faq_used is not None and faq_max is not None and faq_max > 0 and faq_used / faq_max >= 0.9:
        add(
            severity="warning",
            reason_code="faq_capacity_nearly_full",
            title="FAQ capacity nearly full",
            explanation=f"{faq_used} / {faq_max} FAQ pairs used.",
            action_code="review_faq",
            action_label="Review FAQ",
        )

    if not seats_unlimited and seats_remaining is not None and seats_remaining <= 0:
        add(
            severity="warning",
            reason_code="team_capacity_reached",
            title="Team capacity reached",
            explanation="No additional seats remain on the current plan.",
            action_code="manage_users",
            action_label="Manage users",
        )

    return alerts


def plan_comment_entitlement(features: dict[str, Any]) -> dict[str, Any]:
    allowed = _plan_allows_comments(features)
    return {
        "membership_allows_comments": allowed,
        "reason_code": None if allowed else "plan_comments_disabled",
    }
