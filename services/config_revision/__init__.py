"""One revision counter per tenant and domain."""

from services.config_revision.store import DOMAINS, bump, current, subscribe

__all__ = ["DOMAINS", "bump", "current", "subscribe"]
