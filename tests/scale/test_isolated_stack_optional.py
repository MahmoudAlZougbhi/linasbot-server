"""Optional live isolated stack probe. Skips unless cert Redis is already up.

Never targets production. Never starts a 12-hour soak from this module.
"""

from __future__ import annotations

import os
import socket

import pytest


def _cert_redis_up() -> bool:
    if (os.getenv("LINAS_OMNI_CERT_STAGING") or "").strip() != "1":
        return False
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", 56379)) == 0


@pytest.mark.skipif(not _cert_redis_up(), reason="isolated cert redis :56379 is not running")
def test_cert_redis_ping_when_stack_is_up() -> None:
    import redis

    client = redis.Redis(host="127.0.0.1", port=56379, decode_responses=True, socket_timeout=1.5)
    assert client.ping() is True
