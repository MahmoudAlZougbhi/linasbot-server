"""Web Chat API route registration."""

from modules import web_chat_mobile_routes as _mobile  # noqa: F401
from modules import web_chat_public_routes as _public  # noqa: F401

__all__ = ["_mobile", "_public"]
