"""Security headers on API responses. Nginx sets the same headers on the SPA."""

from __future__ import annotations

import socket
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Nginx is the only source of security headers. X-Served-By names the app host."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-Served-By"] = socket.gethostname()
        return response
