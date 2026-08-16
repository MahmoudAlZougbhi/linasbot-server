"""Process/runtime helpers for Website Chat acceptance (dual servers + real concurrency)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import create_engine, func, select, text

from services.web_chat.pg_models import WebChatMessageRow, WebChatOperationRow
from tests.web_chat_acceptance_support import ROOT, _alembic_python, _free_port, _probe_live_http

T = TypeVar("T")


@dataclass(frozen=True)
class HaSideEffectCounts:
    user_messages: int
    assistant_messages: int
    pending_outbox: int
    operations: int


@dataclass
class WebChatServerProcess:
    proc: subprocess.Popen[str]
    base_url: str
    data_root: Path
    port: int


def fetch_ha_side_effect_counts(postgres_url: str, *, session_id: str) -> HaSideEffectCounts:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        user = conn.execute(
            text("SELECT COUNT(*) FROM web_chat_messages WHERE session_id = :sid AND role = 'user'"),
            {"sid": session_id},
        ).scalar_one()
        assistant = conn.execute(
            text("SELECT COUNT(*) FROM web_chat_messages WHERE session_id = :sid AND role = 'assistant'"),
            {"sid": session_id},
        ).scalar_one()
        pending = conn.execute(
            text(
                "SELECT COUNT(*) FROM web_chat_messages "
                "WHERE session_id = :sid AND role = 'assistant' AND acked_at IS NULL"
            ),
            {"sid": session_id},
        ).scalar_one()
        operations = conn.execute(
            text("SELECT COUNT(*) FROM web_chat_operations WHERE session_id = :sid"),
            {"sid": session_id},
        ).scalar_one()
    return HaSideEffectCounts(
        user_messages=int(user),
        assistant_messages=int(assistant),
        pending_outbox=int(pending),
        operations=int(operations),
    )


def count_operation_rows_for_session(postgres_url: str, *, session_id: str) -> int:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as conn:
        return int(
            conn.execute(
                select(func.count())
                .select_from(WebChatOperationRow)
                .where(WebChatOperationRow.session_id == session_id)
            ).scalar_one()
        )


def count_messages_by_role(postgres_url: str, *, session_id: str, role: str) -> int:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as conn:
        return int(
            conn.execute(
                select(func.count())
                .select_from(WebChatMessageRow)
                .where(
                    WebChatMessageRow.session_id == session_id,
                    WebChatMessageRow.role == role,
                )
            ).scalar_one()
        )


def run_threaded_barrier_async(
    *,
    workers: int,
    coro_factory: Callable[[], Awaitable[T]],
    timeout: float = 60.0,
) -> list[T]:
    """Run ``workers`` independent event loops released together by a threading barrier."""
    barrier = threading.Barrier(workers)
    results: list[T] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def _worker(_: int) -> None:
        try:
            barrier.wait(timeout=10)
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                outcome = loop.run_until_complete(coro_factory())
            finally:
                loop.close()
            with lock:
                results.append(outcome)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, idx) for idx in range(workers)]
        for future in futures:
            future.result(timeout=timeout)
    if errors:
        raise errors[0]
    return results


def _web_chat_server_env(
    *,
    postgres_url: str,
    data_root: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "LINASBOT_DATA_ROOT": str(data_root),
            "LINAS_WHATSAPP_DATABASE_URL": postgres_url,
            "DATABASE_URL": postgres_url,
            "WEB_CHAT_PUBLIC_AVAILABILITY": "true",
            "ENVIRONMENT": "test",
            "PYTHONPATH": str(ROOT),
            "DISABLE_API_DOCS": "true",
            "LINAS_BILLING_BACKEND": "postgres",
            "LINAS_AUTH_TOKEN_BACKEND": "file",
            "META_REGISTRY_BACKEND": "file",
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "sk-test-ci-not-real"),
            "LINASLASER_API_BASE_URL": os.environ.get("LINASLASER_API_BASE_URL", "https://example.com"),
            "LINASLASER_API_TOKEN": os.environ.get("LINASLASER_API_TOKEN", "pytest-token"),
            "DASHBOARD_AUTH_SECRET": os.environ.get("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret"),
        }
    )
    env.pop("LINAS_WHATSAPP_ALLOW_SQLITE", None)
    env.pop("WEB_CHAT_ALLOW_FILE_STORE", None)
    if extra_env:
        env.update(extra_env)
    return env


def _python_executable() -> str:
    return _alembic_python()


def spawn_web_chat_server(
    *,
    postgres_url: str,
    data_root: Path,
    port: int | None = None,
    extra_env: dict[str, str] | None = None,
    startup_timeout: float = 30.0,
) -> WebChatServerProcess:
    data_root.mkdir(parents=True, exist_ok=True)
    chosen_port = port or _free_port()
    env = _web_chat_server_env(postgres_url=postgres_url, data_root=data_root, extra_env=extra_env)
    proc = subprocess.Popen(
        [
            _python_executable(),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(chosen_port),
            "--log-level",
            "error",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{chosen_port}"
    deadline = time.time() + startup_timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = (proc.stderr.read() if proc.stderr else "") or ""
            raise RuntimeError(f"web chat server exited early: {stderr.strip()}")
        if _probe_live_http(base_url, "/web-chat/widget-runtime.js"):
            return WebChatServerProcess(proc=proc, base_url=base_url, data_root=data_root, port=chosen_port)
        time.sleep(0.1)
    stop_web_chat_server(WebChatServerProcess(proc=proc, base_url=base_url, data_root=data_root, port=chosen_port))
    raise RuntimeError("web chat server did not become ready")


def stop_web_chat_server(server: WebChatServerProcess, *, grace_seconds: float = 5.0) -> None:
    if server.proc.poll() is not None:
        return
    server.proc.terminate()
    try:
        server.proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        server.proc.kill()
        server.proc.wait(timeout=grace_seconds)


def _post_json(base_url: str, path: str, payload: dict[str, Any], *, origin: str) -> dict[str, Any]:
    status, body = http_post_json_response(base_url, path, payload, origin=origin)
    if status >= 400:
        raise AssertionError(f"HTTP {status} for {path}: {body!r}")
    return body


def http_post_json_response(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    origin: str = "https://shop.example.com",
) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return int(exc.code), parsed


def http_poll_session(
    base_url: str,
    *,
    widget_key: str,
    session_id: str,
    session_authority: str,
    cursor: str | None = None,
    origin: str = "https://shop.example.com",
) -> dict[str, Any]:
    return _post_json(
        base_url,
        "/api/web-chat/session/poll",
        {
            "session_id": session_id,
            "session_authority": session_authority,
            "widget_key": widget_key,
            "cursor": cursor,
        },
        origin=origin,
    )


def http_ack_session(
    base_url: str,
    *,
    widget_key: str,
    session_id: str,
    session_authority: str,
    message_ids: list[str],
    origin: str = "https://shop.example.com",
) -> dict[str, Any]:
    return _post_json(
        base_url,
        "/api/web-chat/session/ack",
        {
            "session_id": session_id,
            "session_authority": session_authority,
            "widget_key": widget_key,
            "message_ids": message_ids,
        },
        origin=origin,
    )


def wait_for_http(base_url: str, path: str, *, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _probe_live_http(base_url, path):
            return
        time.sleep(0.1)
    raise RuntimeError(f"HTTP endpoint not ready: {base_url}{path}")
