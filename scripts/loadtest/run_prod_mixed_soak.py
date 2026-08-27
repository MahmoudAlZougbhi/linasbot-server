"""Production mixed DM+comment soak. Graph send is skipped only when soak is armed.

Run on a production node after the scale release is committed. Uses real OpenAI
through the durable Meta inbound queue. Does not create DigitalOcean droplets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIRM = "I_ACCEPT_PRODUCTION_OPENAI_COST"


def _pick_bindings() -> tuple[Any, Any]:
    from services.meta_app_registry import APP_A_KEY, get_meta_app_registry

    registry = get_meta_app_registry()
    active = [
        item
        for item in registry.list_bindings(include_inactive=False, include_superseded=False)
        if str(item.status) == "active" and str(item.channel) in {"facebook", "instagram"}
    ]
    if not active:
        raise SystemExit("no active Meta bindings")
    dm = active[0]
    comment = next((item for item in active if item.app_key == APP_A_KEY), dm)
    return dm, comment


def _settings(binding: Any) -> Any:
    from services.meta_app_registry import get_meta_app_registry
    from services.meta_graph_routing import build_messaging_settings_for_binding

    registry = get_meta_app_registry()
    credential = registry.get_credential(binding)
    return build_messaging_settings_for_binding(binding, credential=credential)


def _enqueue_dm(binding: Any, settings: Any, text: str) -> str:
    from services.meta_multi_app_router import ResolvedMetaEvent
    from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_dm_accepted

    sender = f"soak_{uuid.uuid4().hex}"
    event = {
        "channel": binding.channel,
        "sender_id": sender,
        "sender": sender,
        "text": text,
        "message_id": f"m_{uuid.uuid4().hex}",
        "_linas_soak_simulation": True,
    }
    resolved = ResolvedMetaEvent(event=event, settings=settings, binding=binding)
    global_key = f"soak:dm:{binding.tenant_id}:{sender}:{event['message_id']}"
    event_id, _created = persist_meta_dm_accepted(resolved, global_key=global_key)
    status = enqueue_meta_inbound_event(event_id, claim_handle=None)
    if status != "queued":
        raise RuntimeError(f"dm_enqueue_{status}")
    return event_id


def _enqueue_comment(binding: Any, settings: Any, text: str) -> str:
    from services.meta_comment_events import ResolvedMetaCommentEvent
    from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_comment_accepted

    comment_id = f"soak_c_{uuid.uuid4().hex}"
    event = {
        "comment_id": comment_id,
        "text": text,
        "author_id": f"soak_a_{uuid.uuid4().hex}",
        "author_name": "Soak",
        "post_id": f"soak_p_{uuid.uuid4().hex}",
        "channel": binding.channel,
        "_linas_soak_simulation": True,
    }
    resolved = ResolvedMetaCommentEvent(event=event, settings=settings, binding=binding)
    global_key = f"soak:comment:{binding.tenant_id}:{comment_id}"
    event_id, _created = persist_meta_comment_accepted(resolved, global_key=global_key)
    status = enqueue_meta_inbound_event(event_id, claim_handle=None)
    if status != "queued":
        raise RuntimeError(f"comment_enqueue_{status}")
    return event_id


def _snapshot() -> dict[str, Any]:
    from services.job_queue import job_queue
    from services.scale.latency_histogram import snapshot as hist_snapshot
    from services.scale.rate_window import snapshot_rates
    from services.scale.replica_controller import current_replicas, recent_events

    depths = job_queue.depth() or {}
    ingress, complete = snapshot_rates()
    state = current_replicas()
    return {
        "ts": time.time(),
        "queue_depth": depths,
        "ingress_per_sec": ingress,
        "complete_per_sec": complete,
        "replicas": {"api": state.api, "workers": state.workers, "last_action": state.last_action},
        "latency": hist_snapshot(),
        "autoscale_events": recent_events(limit=8),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-sec", type=int, default=7200)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--dm-per-min", type=float, default=40.0)
    parser.add_argument("--comment-per-min", type=float, default=20.0)
    parser.add_argument("--artifact", type=Path, default=Path("logs/prod-mixed-soak.json"))
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise SystemExit(f"pass --confirm {CONFIRM}")
    if (os.getenv("ENVIRONMENT") or "").strip().lower() != "production":
        raise SystemExit("ENVIRONMENT=production is required")

    from services.scale.soak_arm import arm, disarm

    duration = max(60, min(int(args.duration_sec), 4 * 60 * 60))
    arm(ttl_seconds=duration + 300)
    dm_binding, comment_binding = _pick_bindings()
    dm_settings = _settings(dm_binding)
    comment_settings = _settings(comment_binding)
    print(
        json.dumps(
            {
                "dm_tenant": dm_binding.tenant_id,
                "dm_channel": dm_binding.channel,
                "comment_tenant": comment_binding.tenant_id,
                "comment_channel": comment_binding.channel,
                "duration_sec": duration,
            }
        )
    )
    started = time.time()
    samples: list[dict[str, Any]] = []
    sent = {"dm": 0, "comment": 0, "errors": 0}
    dm_interval = 60.0 / max(0.1, float(args.dm_per_min))
    comment_interval = 60.0 / max(0.1, float(args.comment_per_min))
    next_dm = started
    next_comment = started
    next_sample = started
    try:
        while time.time() - started < duration:
            now = time.time()
            try:
                if now >= next_dm:
                    _enqueue_dm(dm_binding, dm_settings, "شو ساعاتكن اليوم؟")
                    sent["dm"] += 1
                    next_dm = now + dm_interval
                if now >= next_comment:
                    _enqueue_comment(comment_binding, comment_settings, "السعر؟")
                    sent["comment"] += 1
                    next_comment = now + comment_interval
            except Exception as exc:
                sent["errors"] += 1
                print(json.dumps({"error": type(exc).__name__}))
                time.sleep(1.0)
            if now >= next_sample:
                snap = _snapshot()
                snap["sent"] = dict(sent)
                samples.append(snap)
                print(json.dumps({"elapsed_s": int(now - started), "sent": sent, "depth": snap["queue_depth"]}))
                next_sample = now + 30.0
            time.sleep(0.05)
    finally:
        disarm()
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "duration_sec": duration,
        "sent": sent,
        "samples": samples,
        "final": _snapshot(),
    }
    args.artifact.write_text(json.dumps(payload), encoding="utf-8")
    print(json.dumps({"artifact": str(args.artifact), "sent": sent}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
