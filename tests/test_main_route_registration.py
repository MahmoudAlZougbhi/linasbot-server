"""Regression: main.py must import API modules before the SPA catch-all."""

from __future__ import annotations

from starlette.routing import Route


def test_main_registers_critical_public_routes() -> None:
    import main  # noqa: F401
    from modules.core import app

    paths = {
        route.path
        for route in app.routes
        if isinstance(route, Route) and isinstance(route.path, str)
    }
    assert "/api/health" in paths
    assert "/api/ready" in paths
    assert "/webhook" in paths
    assert "/api/auth/login" in paths
