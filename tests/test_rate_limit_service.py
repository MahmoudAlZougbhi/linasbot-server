"""Tests for Redis / file / memory rate-limit backends and fail-closed prod mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.rate_limit_service import RateLimitService, rate_limit_service


@pytest.fixture(autouse=True)
def _restore_global_limiter():
    yield
    rate_limit_service.reconfigure(backend=None, redis_client=None, redis_url=None)


def test_memory_backend_enforces_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("RATE_LIMIT_BACKEND", raising=False)
    svc = RateLimitService(backend="memory")
    key = "t:mem"
    assert svc.hit(key, limit=2, window_seconds=60) == (True, 0)
    assert svc.hit(key, limit=2, window_seconds=60) == (True, 0)
    allowed, retry = svc.hit(key, limit=2, window_seconds=60)
    assert allowed is False
    assert retry >= 1


def test_file_backend_non_prod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "file")
    svc = RateLimitService(backend="file", data_dir=tmp_path / "rl")
    key = "t:file"
    assert svc.hit(key, limit=1, window_seconds=60)[0] is True
    allowed, retry = svc.hit(key, limit=1, window_seconds=60)
    assert allowed is False
    assert retry >= 1
    assert list((tmp_path / "rl").glob("*.json"))


def test_non_prod_defaults_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("RATE_LIMIT_BACKEND", raising=False)
    svc = RateLimitService()
    assert svc.resolve_backend() == "file"


def test_prod_defaults_to_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RATE_LIMIT_BACKEND", raising=False)
    svc = RateLimitService()
    assert svc.resolve_backend() == "redis"


def test_multi_worker_shared_redis_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    server = fakeredis.FakeServer()
    client_a = fakeredis.FakeRedis(server=server, decode_responses=True)
    client_b = fakeredis.FakeRedis(server=server, decode_responses=True)

    worker_a = RateLimitService(backend="redis", redis_client=client_a)
    worker_b = RateLimitService(backend="redis", redis_client=client_b)

    key = "login:shared-ip"
    assert worker_a.hit(key, limit=3, window_seconds=60)[0] is True
    assert worker_b.hit(key, limit=3, window_seconds=60)[0] is True
    assert worker_a.hit(key, limit=3, window_seconds=60)[0] is True
    allowed_a, _ = worker_a.hit(key, limit=3, window_seconds=60)
    allowed_b, retry_b = worker_b.hit(key, limit=3, window_seconds=60)
    assert allowed_a is False
    assert allowed_b is False
    assert retry_b >= 1


def test_prod_redis_unavailable_fail_closed_no_file_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LINAS_REDIS_URL", raising=False)
    monkeypatch.setenv("RATE_LIMIT_UNAVAILABLE_RETRY_AFTER", "42")

    svc = RateLimitService(backend="redis", redis_url="", data_dir=tmp_path / "should_not_use")
    with caplog.at_level("ERROR"):
        allowed, retry = svc.hit("login:1.1.1.1", limit=5, window_seconds=300)
    assert allowed is False
    assert retry == 42
    assert svc.last_deny_reason == "backend_unavailable"
    assert "fail-closed" in caplog.text
    assert not list((tmp_path / "should_not_use").glob("*.json"))


def test_prod_redis_connection_error_fail_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _Boom:
        def register_script(self, *_a, **_k):
            raise ConnectionError("redis down")

        def pipeline(self):
            raise ConnectionError("redis down")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    svc = RateLimitService(backend="redis", redis_client=_Boom())
    with caplog.at_level("ERROR"):
        allowed, retry = svc.hit("k", limit=1, window_seconds=30)
    assert allowed is False
    assert retry >= 1
    assert svc.last_deny_reason == "backend_unavailable"
    assert "fail-closed" in caplog.text


@pytest.mark.asyncio
async def test_check_rate_limit_returns_503_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from services import auth_rate_limits as arl

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    rate_limit_service.reconfigure(backend="redis", redis_url="")

    req = MagicMock()
    req.client.host = "9.9.9.9"
    req.headers = {}
    req.method = "POST"
    req.cookies = {}

    async def _no_id(_request, _path):
        return None

    monkeypatch.setattr(arl, "_peek_auth_identifier", _no_id)
    monkeypatch.setattr(arl, "client_ip", lambda _r: "9.9.9.9")

    resp = await arl.check_rate_limit(req, "/api/auth/login")
    assert resp is not None
    assert resp.status_code == 503
    assert resp.body  # JSON body present
