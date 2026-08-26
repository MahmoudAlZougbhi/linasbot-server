"""HTTP provider/OpenAI stubs for isolated certification. Never bind production hosts."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:  # noqa: A003
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        mode = str((query.get("mode") or ["ok"])[0])
        self._read_body()
        if mode == "delay":
            time.sleep(min(2.0, float((query.get("sec") or ["0.05"])[0])))
            self._ok()
            return
        if mode == "429":
            self._send(
                429,
                json.dumps({"error": {"message": "rate limited", "code": 4}}).encode(),
                {"Retry-After": str((query.get("retry") or ["2"])[0])},
            )
            return
        if mode == "meta613":
            self._send(
                429,
                json.dumps({"error": {"message": "custom limit", "code": 613}}).encode(),
                {
                    "Retry-After": "3",
                    "X-App-Usage": '{"call_count":91,"total_cputime":10,"total_time":10}',
                    "X-Business-Use-Case-Usage": '{"instagram":[{"call_count":80}]}',
                },
            )
            return
        if mode in {"408", "500", "502", "503", "504"}:
            self._send(int(mode), json.dumps({"error": mode}).encode())
            return
        if mode == "expired":
            self._send(401, json.dumps({"error": {"message": "token expired", "code": 190}}).encode())
            return
        if mode == "malformed":
            self._send(200, b"<not-json>")
            return
        if mode == "reset":
            self.close_connection = True
            return
        if mode == "timeout-after-accept":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            time.sleep(min(3.0, float((query.get("sec") or ["2"])[0])))
            return
        if mode == "lost-ack":
            self.wfile.close()
            return
        self._ok()

    def _ok(self) -> None:
        payload = {
            "id": f"mid_{int(time.time() * 1000) % 10_000_000}",
            "request_id": f"req_{int(time.time() * 1000) % 10_000_000}",
        }
        self._send(200, json.dumps(payload).encode())


def start_stub_server(*, host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    if host not in {"127.0.0.1", "localhost"}:
        raise PermissionError("stub_http_must_bind_loopback")
    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assigned = int(server.server_address[1])
    return server, f"http://127.0.0.1:{assigned}"


def wait_port(host: str, port: int, *, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.05)
    raise TimeoutError(f"port_not_ready:{host}:{port}")
