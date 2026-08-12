"""SSE CORS: reflect allowlisted Origin; never emit Access-Control-Allow-Origin: *."""

from __future__ import annotations

from starlette.requests import Request

from modules.core import cors_allow_origins
from modules.live_chat_api import _sse_response_headers


def _request_with_origin(origin: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"origin", origin.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/live-chat/events",
            "raw_path": b"/api/live-chat/events",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        }
    )


def test_sse_cors_reflects_allowlisted_origin() -> None:
    allowed = cors_allow_origins(environment="production")
    assert "https://linasaibot.com" in allowed
    headers = _sse_response_headers(_request_with_origin("https://linasaibot.com"))
    assert headers.get("Access-Control-Allow-Origin") == "https://linasaibot.com"
    assert headers.get("Access-Control-Allow-Credentials") == "true"
    assert "*" not in headers.values()


def test_sse_cors_omits_header_for_disallowed_origin() -> None:
    headers = _sse_response_headers(_request_with_origin("https://evil.example"))
    assert "Access-Control-Allow-Origin" not in headers
    assert "*" not in headers.values()


def test_sse_cors_omits_header_when_origin_missing() -> None:
    headers = _sse_response_headers(_request_with_origin(None))
    assert "Access-Control-Allow-Origin" not in headers


def test_sse_cors_never_uses_wildcard() -> None:
    for env in ("production", "development"):
        for origin in cors_allow_origins(environment=env):
            headers = _sse_response_headers(_request_with_origin(origin))
            assert headers.get("Access-Control-Allow-Origin") != "*"
            assert headers.get("Access-Control-Allow-Origin") == origin
