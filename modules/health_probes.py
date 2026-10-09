"""Container health routes. /api/health stays the public liveness summary."""

from __future__ import annotations

import os

from fastapi.responses import JSONResponse

from modules.core import app
from services.platform.feature_flags import flag_value
from services.platform.health_checks import live_payload, ready_payload, startup_payload


def _strict() -> bool:
    return (os.getenv("LINAS_HEALTH_STRICT") or "").strip().lower() in {"1", "true", "yes"}


def _pg_seconds() -> float | None:
    import time

    from sqlalchemy import create_engine, text

    url = (os.getenv("LINAS_PLATFORM_DATABASE_URL") or os.getenv("LINAS_WHATSAPP_DATABASE_URL") or "").strip()
    if not url:
        return None
    started = time.perf_counter()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return 1.0
    return time.perf_counter() - started


def _valkey_ok() -> bool | None:
    url = (os.getenv("REDIS_URL") or os.getenv("LINAS_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2)
        client.ping()
    except Exception:
        return False
    return True


def _spaces_configured() -> bool | None:
    names = ("LINAS_SPACES_KEY", "LINAS_SPACES_SECRET", "LINAS_SPACES_BUCKET")
    present = [(os.getenv(name) or "").strip() for name in names]
    if not any(present):
        return None
    return all(present)


@app.get("/api/health/live")
async def health_live() -> dict[str, object]:
    return live_payload()


@app.get("/api/health/startup")
async def health_startup() -> JSONResponse:
    payload = startup_payload(migrations_at_head=None)
    return JSONResponse(status_code=200 if payload["ok"] else 503, content=payload)


@app.get("/api/health/ready")
async def health_ready() -> JSONResponse:
    payload = ready_payload(
        pg_seconds=_pg_seconds(),
        valkey_ok=_valkey_ok(),
        spaces_configured=_spaces_configured(),
        flags_ok=bool(flag_value("queue_backend")),
        strict=_strict(),
    )
    return JSONResponse(status_code=200 if payload["ok"] else 503, content=payload)
