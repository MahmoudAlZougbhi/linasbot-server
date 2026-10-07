"""Security headers on API responses. Nginx sets the same headers on the SPA."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Nginx is the only header source. Adding them here duplicated every /api response."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        return await call_next(request)
