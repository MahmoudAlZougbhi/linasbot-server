"""Deterministic policy precedence. Higher rank wins; no incidental list order."""

from __future__ import annotations

from typing import Literal

Gate = Literal[
    "platform_security",
    "unpublished",
    "human_control",
    "credits_limits",
    "restricted",
    "comment_ignore_or_static",
    "semantic_handoff",
    "faq_fast_path",
    "planner",
]

PRECEDENCE: tuple[Gate, ...] = (
    "platform_security",
    "unpublished",
    "human_control",
    "credits_limits",
    "restricted",
    "comment_ignore_or_static",
    "semantic_handoff",
    "faq_fast_path",
    "planner",
)


def rank(gate: Gate) -> int:
    return PRECEDENCE.index(gate)


def wins(left: Gate, right: Gate) -> Gate:
    return left if rank(left) <= rank(right) else right
