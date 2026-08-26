"""In-process mix + checkpoint helpers for isolated omnichannel certification."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.omnichannel.contract import NormalizedInbound

MIX = (
    ("instagram", "comment", 200),
    ("tiktok", "comment", 200),
    ("instagram", "dm", 300),
    ("facebook", "dm", 300),
    ("tiktok", "dm", 300),
    ("whatsapp", "dm", 600),
)


def artifact_dir() -> Path:
    path = Path("artifacts/omnichannel-cert")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_checkpoint(name: str, payload: dict[str, Any]) -> Path:
    path = artifact_dir() / f"{name}.json"
    raw = json.dumps(payload, indent=2, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    payload = {**payload, "report_sha256": digest}
    raw = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(raw + "\n", encoding="utf-8")
    (artifact_dir() / f"{name}.sha256").write_text(digest + "\n", encoding="utf-8")
    return path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def mix_event(*, seq: int, tenant_id: str, scale: float = 1.0, nonce: str = "") -> NormalizedInbound:
    total = max(1, int(sum(rate for _c, _s, rate in MIX) * scale))
    cursor = seq % total
    running = 0
    channel, surface = "instagram", "dm"
    for ch, surf, rate in MIX:
        running += max(1, int(rate * scale))
        if cursor < running:
            channel, surface = ch, surf
            break
    pid = f"{channel}-{surface}-{nonce}-{seq}" if nonce else f"{channel}-{surface}-{seq}"
    return NormalizedInbound(
        provider_event_id=pid,
        tenant_id=tenant_id,
        account_id=f"acct-{seq % 7}",
        channel=channel,  # type: ignore[arg-type]
        surface=surface,  # type: ignore[arg-type]
        conversation_key=(
            f"{tenant_id}:{channel}:shared-{seq % 25}" if seq % 10 == 3 else f"{tenant_id}:{channel}:c-{seq}"
        ),
        provider_timestamp=time.time() - (seq % 7) * 0.05,
        payload_hash=pid,
        payload={"text": "cert", "i": seq, "control_epoch": 0},
    )


def post_inbound(url: str, event: NormalizedInbound, *, timeout: float = 5.0) -> tuple[int, float, bool]:
    body = json.dumps(
        {
            "provider_event_id": event.provider_event_id,
            "tenant_id": event.tenant_id,
            "account_id": event.account_id,
            "channel": event.channel,
            "surface": event.surface,
            "conversation_key": event.conversation_key,
            "provider_timestamp": event.provider_timestamp,
            "payload_hash": event.payload_hash,
            "payload": event.payload,
        }
    ).encode()
    req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            return int(resp.status), (time.perf_counter() - t0) * 1000.0, bool(payload.get("created"))
    except HTTPError as exc:
        return int(exc.code), (time.perf_counter() - t0) * 1000.0, False
    except (URLError, TimeoutError, OSError):
        return 0, (time.perf_counter() - t0) * 1000.0, False
