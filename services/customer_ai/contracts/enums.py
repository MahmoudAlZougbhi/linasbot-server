"""Shared enums for Customer Brain contracts."""

from __future__ import annotations

from typing import Literal

InvocationKind = Literal["dm", "comment", "followup"]
Surface = Literal["dm", "comment", "web_chat"]

CommentMode = Literal[
    "ignore",
    "manual",
    "static_comment",
    "static_dm",
    "static_both",
    "ai_comment",
    "ai_dm",
    "ai_both",
]

TaskType = Literal[
    "information",
    "comparison",
    "resource_request",
    "hours",
    "service_request",
    "product_request",
    "draft_correction",
    "cancel_or_status",
    "human_request",
    "acknowledgement",
]

SourceFamily = Literal[
    "faq",
    "knowledge",
    "care",
    "services",
    "products",
    "branches",
    "hours",
    "prices",
    "requests",
    "none",
]

ActionType = Literal[
    "send_resource",
    "start_request",
    "update_draft",
    "submit_request",
    "cancel_request",
    "escalate_to_human",
    "no_op",
]

ActionState = Literal["success", "failure", "unknown", "pending", "rejected"]

ReplyDecision = Literal["reply", "clarify", "handoff_ack", "no_reply", "deterministic"]

TaskDisposition = Literal[
    "answered",
    "action_succeeded",
    "awaiting_customer",
    "pending_delivery",
    "not_found",
    "blocked",
    "failed",
    "policy_suppressed",
]

RetrievalOutcome = Literal[
    "found",
    "ambiguous",
    "not_found",
    "index_not_ready",
    "provider_not_configured",
    "provider_error",
    "source_unpublished",
    "version_conflict",
    "permission_denied",
    "context_overflow",
    "budget_exceeded",
]

StopReason = Literal[
    "ok",
    "engine_removed",
    "brain_disabled",
    "comments_toggle_off",
    "insufficient_credits",
    "insufficient_messages",
    "human_control",
    "restricted",
    "policy_suppressed",
    "provider_not_configured",
    "index_not_ready",
    "context_overflow",
    "unpublished",
    "failed_closed",
]
