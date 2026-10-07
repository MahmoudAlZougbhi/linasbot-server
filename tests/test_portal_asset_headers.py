"""Owner portal deep links must load real JS, and responses must send security headers."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.security_headers import SecurityHeadersMiddleware

ROOT = Path(__file__).resolve().parents[1]


def test_vite_asset_base_is_site_root() -> None:
    text = (ROOT / "dashboard" / "vite.config.mjs").read_text(encoding="utf-8")
    assert 'base: "/",' in text
    assert 'base: "./"' not in text


def test_nginx_serves_assets_and_security_headers() -> None:
    text = (ROOT / "deploy" / "nginx-linasaibot.conf").read_text(encoding="utf-8")
    assert text.count("server_tokens off;") >= 2
    assert text.count("Strict-Transport-Security") >= 2
    assert text.count("X-Content-Type-Options") >= 2
    assert text.count("X-Frame-Options") >= 2
    assert text.count("Referrer-Policy") >= 2
    assert text.count("Content-Security-Policy") >= 2
    assert text.count("location ^~ /static/") >= 2
    assert text.count("try_files $uri =404;") >= 2


def test_security_headers_middleware_sets_nosniff() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/ping")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors" in response.headers["content-security-policy"]
