"""Comment Rule pipeline."""

from __future__ import annotations

from services.brain.comments.pipeline import deterministic_comment_result, winning_comment_mode

__all__ = ["deterministic_comment_result", "winning_comment_mode"]
