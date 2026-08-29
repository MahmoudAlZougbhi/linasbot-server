"""Latency-first autoscaling recommendation. Does not call cloud APIs."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ScaleRecommendation:
    action: str
    api_replicas: int
    worker_replicas: int
    reason: str
    signals: dict[str, Any]


def recommend(
    *,
    current_api: int,
    current_workers: int,
    queue_depth: int,
    oldest_age_seconds: float,
    wait_p95_ms: float,
    wait_p99_ms: float,
    ingress_per_sec: float,
    complete_per_sec: float,
    error_ratio: float = 0.0,
    cooldown_ok: bool = True,
    api_p95_ms: float = 0.0,
    api_p99_ms: float = 0.0,
    api_error_ratio: float = 0.0,
    cpu_pct: float = 0.0,
    mem_pct: float = 0.0,
    request_per_sec: float = 0.0,
    api_inflight: float = 0.0,
    provider_limited: bool = False,
    busy_ratio: float = 0.0,
    in_node_worker_cap: int = 0,
    extra_quiet: bool = False,
    event_loop_lag_ms: float = 0.0,
) -> ScaleRecommendation:
    """Scale up early on wait-time; scale down only after a quiet, cool period."""
    api_min = _int_env("LINAS_AUTOSCALE_API_MIN", 2)
    api_max = _int_env("LINAS_AUTOSCALE_API_MAX", 8)
    worker_min = _int_env("LINAS_AUTOSCALE_WORKER_MIN", 2)
    worker_max = _int_env("LINAS_AUTOSCALE_WORKER_MAX", 32)
    p95_up = _float_env("LINAS_AUTOSCALE_WAIT_P95_UP_MS", 250.0)
    p95_strong = _float_env("LINAS_AUTOSCALE_WAIT_P95_STRONG_MS", 800.0)
    oldest_up = _float_env("LINAS_AUTOSCALE_OLDEST_UP_SEC", 1.0)
    p95_down = _float_env("LINAS_AUTOSCALE_WAIT_P95_DOWN_MS", 50.0)
    api_p95_up = _float_env("LINAS_AUTOSCALE_API_P95_UP_MS", 250.0)

    api = max(api_min, min(api_max, int(current_api)))
    workers = max(worker_min, min(worker_max, int(current_workers)))
    signals = {
        "queue_depth": int(queue_depth),
        "oldest_age_seconds": float(oldest_age_seconds),
        "wait_p95_ms": float(wait_p95_ms),
        "wait_p99_ms": float(wait_p99_ms),
        "ingress_per_sec": float(ingress_per_sec),
        "complete_per_sec": float(complete_per_sec),
        "error_ratio": float(error_ratio),
        "cooldown_ok": bool(cooldown_ok),
        "api_p95_ms": float(api_p95_ms),
        "api_p99_ms": float(api_p99_ms),
        "api_error_ratio": float(api_error_ratio),
        "cpu_pct": float(cpu_pct),
        "mem_pct": float(mem_pct),
        "request_per_sec": float(request_per_sec),
        "api_inflight": float(api_inflight),
        "provider_limited": bool(provider_limited),
        "busy_ratio": float(busy_ratio),
        "in_node_worker_cap": int(in_node_worker_cap),
        "extra_quiet": bool(extra_quiet),
        "event_loop_lag_ms": float(event_loop_lag_ms),
        "api_min": api_min,
        "api_max": api_max,
        "worker_min": worker_min,
        "worker_max": worker_max,
    }

    backlog_growing = ingress_per_sec > complete_per_sec + 0.5
    rate_pressure = backlog_growing
    if provider_limited:
        return ScaleRecommendation(
            action="hold",
            api_replicas=api,
            worker_replicas=workers,
            reason="provider_limited_do_not_add_workers",
            signals=signals,
        )
    node_capped = in_node_worker_cap > 0 and workers >= in_node_worker_cap
    api_hot = (
        api_p95_ms >= api_p95_up
        or api_p99_ms >= api_p95_up * 2
        or api_error_ratio >= 0.02
        or cpu_pct >= 75.0
        or mem_pct >= 85.0
        or (request_per_sec > 0 and api_inflight >= max(8.0, request_per_sec * 2))
    )
    strong = wait_p95_ms >= p95_strong or oldest_age_seconds >= oldest_up * 3 or (backlog_growing and queue_depth >= 20)
    mild = (
        wait_p95_ms >= p95_up
        or oldest_age_seconds >= oldest_up
        or rate_pressure
        or api_hot
        or busy_ratio >= 0.8
        or event_loop_lag_ms >= 80.0
    )
    if node_capped and (strong or mild):
        return ScaleRecommendation(
            action="hold",
            api_replicas=api,
            worker_replicas=workers,
            reason="in_node_cap_need_node_layer",
            signals=signals,
        )

    if strong:
        step = max(2, workers)
        next_workers = min(worker_max, workers + step)
        next_api = min(api_max, api + 1) if api_hot else api
        action = "scale_up_strong" if next_workers > workers or next_api > api else "hold"
        return ScaleRecommendation(
            action=action,
            api_replicas=next_api,
            worker_replicas=next_workers,
            reason="wait_p95_or_oldest_or_backlog_strong",
            signals=signals,
        )
    if mild:
        next_workers = min(worker_max, workers + 1)
        next_api = min(api_max, api + 1) if api_hot else api
        action = "scale_up" if next_workers > workers or next_api > api else "hold"
        return ScaleRecommendation(
            action=action,
            api_replicas=next_api,
            worker_replicas=next_workers,
            reason="wait_p95_or_oldest_or_backlog_rising",
            signals=signals,
        )

    quiet = (
        wait_p95_ms <= p95_down
        and queue_depth == 0
        and oldest_age_seconds < 0.2
        and ingress_per_sec <= complete_per_sec + 0.1
        and error_ratio < 0.05
    )
    if quiet and cooldown_ok and (workers > worker_min or api > api_min):
        if extra_quiet and workers > worker_min:
            next_workers = max(worker_min, workers // 2)
        else:
            next_workers = max(worker_min, workers - 1)
        next_api = api if api <= api_min else max(api_min, api - 1)
        return ScaleRecommendation(
            action="scale_down",
            api_replicas=next_api,
            worker_replicas=next_workers,
            reason="quiet_after_cooldown",
            signals=signals,
        )
    return ScaleRecommendation(
        action="hold",
        api_replicas=api,
        worker_replicas=workers,
        reason="within_latency_targets" if not quiet else "cooldown_hold",
        signals=signals,
    )


def recommendation_dict(**kwargs: Any) -> dict[str, Any]:
    return asdict(recommend(**kwargs))
