"""Respond ctx bootstrap for worker / Meta DM paths."""

from __future__ import annotations

from handlers.text_handlers_respond_ctx import bootstrap_process_respond_ctx


def test_bootstrap_injects_language_detection_service() -> None:
    ctx: dict = {}
    bootstrap_process_respond_ctx(ctx)
    assert ctx.get("language_detection_service") is not None
    assert callable(ctx.get("get_firestore_db"))
    assert callable(ctx.get("log_interaction"))


def test_bootstrap_is_idempotent() -> None:
    ctx: dict = {}
    bootstrap_process_respond_ctx(ctx)
    first = ctx["language_detection_service"]
    bootstrap_process_respond_ctx(ctx)
    assert ctx["language_detection_service"] is first
