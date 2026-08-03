"""Publish enablement gate (plan Phase 2 — no fake/no-op publish)."""

from __future__ import annotations

from services.cm.constants import PUBLISH_DISABLED_MESSAGE, cm_publish_enabled


class PublishDisabledError(RuntimeError):
    """Raised when publish/rollback is attempted while CM publish is disabled."""

    code: str = "PUBLISH_DISABLED"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or PUBLISH_DISABLED_MESSAGE)
        self.message = message or PUBLISH_DISABLED_MESSAGE


def ensure_publish_enabled() -> None:
    """Raise PublishDisabledError unless CM_PUBLISH_ENABLED is truthy."""
    if not cm_publish_enabled():
        raise PublishDisabledError(PUBLISH_DISABLED_MESSAGE)


def publish_status() -> dict[str, object]:
    enabled = cm_publish_enabled()
    return {
        "publish_enabled": enabled,
        "message": None if enabled else PUBLISH_DISABLED_MESSAGE,
    }
