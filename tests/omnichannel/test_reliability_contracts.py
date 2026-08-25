"""Regression: every confirmed omnichannel reliability defect."""

from __future__ import annotations

import fakeredis
import pytest

from services.omnichannel.backoff import delay_for_provider
from services.omnichannel.classify import classify_http_delivery, returned_rejection_is_definitive
from services.omnichannel.comment_limit import comment_send_allowed, configure_comment_limiter
from services.omnichannel.dlq import replay_delivery_only
from services.omnichannel.gates import TIKTOK_DM_GATE_REASON, tiktok_dm_live_allowed
from services.omnichannel.headers import parse_meta_usage, parse_retry_after_seconds
from services.omnichannel.limiter import DistributedProviderLimiter
from services.omnichannel.meta_errors import MetaProviderError
from services.omnichannel.queues import logical_for_channel, outbound_logical, physical_queue_for
from services.rate_limit_service import RateLimitService
from services.scale.provider_limiter import ProviderLimiter
from services.tiktok_business.comment_sync import enqueue_tiktok_comment_ai


def test_dms_and_comments_use_different_physical_queues():
    dm = physical_queue_for(logical_for_channel(channel="instagram", surface="dm"))
    comment = physical_queue_for(logical_for_channel(channel="instagram", surface="comment"))
    wa = physical_queue_for(logical_for_channel(channel="whatsapp", surface="dm"))
    assert dm == "high_priority"
    assert wa == "high_priority"
    assert comment == "background"
    assert dm != comment


def test_comment_polling_never_uses_high_priority():
    assert physical_queue_for("polling") == "background"
    assert physical_queue_for(outbound_logical(channel="tiktok", surface="comment")) == "background"


def test_retry_after_and_meta_usage_headers_are_preserved():
    headers = {
        "Retry-After": "7",
        "X-App-Usage": '{"call_count":90}',
        "X-Page-Usage": '{"call_count":80}',
        "X-Business-Use-Case-Usage": '{"instagram":[{"call_count":70}]}',
    }
    assert parse_retry_after_seconds(headers) == 7.0
    usage = parse_meta_usage(headers)
    assert usage["x_app_usage"]
    assert usage["x_page_usage"]
    assert usage["x_business_use_case_usage"]
    delay = delay_for_provider(attempt=0, headers=headers)
    assert delay == 7.0


def test_meta_429_and_613_are_retryable_not_owner_action():
    throttled = classify_http_delivery(http_status=429, provider_code="613")
    assert throttled.kind == "transient"
    assert throttled.retryable is True
    err = MetaProviderError("throttled", http_status=429, error_code=613, headers={"Retry-After": "3"})
    assert err.retryable is True
    assert err.retry_after_seconds == 3.0
    assert returned_rejection_is_definitive({"http_status": 429}) is False
    owner = classify_http_delivery(http_status=None, error_text="unclassified")
    assert owner.kind == "ambiguous"
    assert owner.retryable is False


@pytest.mark.parametrize(
    ("kwargs", "kind", "retryable"),
    [
        ({"http_status": 500}, "transient", True),
        ({"http_status": 502}, "transient", True),
        ({"http_status": 503}, "transient", True),
        ({"http_status": 504}, "transient", True),
        ({"http_status": 408}, "transient", True),
        ({"connection_reset_before_submit": True}, "transient", True),
        ({"submitted": True, "http_status": 504}, "ambiguous", False),
        ({"malformed_response": True}, "transient", True),
        ({"malformed_response": True, "submitted": True}, "ambiguous", False),
        ({"http_status": 400}, "permanent", False),
        ({"http_status": 401}, "permission_blocked", False),
        ({"http_status": 403}, "permission_blocked", False),
        ({"token_expired": True}, "permission_blocked", False),
        ({"submitted": True, "local_update_failed": True}, "ambiguous", False),
        ({"http_status": 200}, "success", False),
    ],
)
def test_delivery_classes(kwargs, kind, retryable):
    decision = classify_http_delivery(**kwargs)
    assert decision.kind == kind
    assert decision.retryable is retryable


def test_comment_rate_limit_is_redis_not_process_memory():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    service = RateLimitService(backend="redis", redis_client=redis_client)
    configure_comment_limiter(service)
    allowed = 0
    denied = 0
    for _ in range(35):
        if comment_send_allowed(tenant_id="t1", app_key="a", channel="instagram", asset_id="ig1"):
            allowed += 1
        else:
            denied += 1
    assert allowed == 30
    assert denied == 5
    other = comment_send_allowed(tenant_id="t2", app_key="a", channel="instagram", asset_id="ig1")
    assert other is True


def test_tiktok_enqueue_failure_is_not_swallowed(monkeypatch):
    class Boom:
        def enqueue(self, **_kwargs):
            raise RuntimeError("redis_down")

    monkeypatch.setattr("services.job_queue.job_queue", Boom())
    with pytest.raises(RuntimeError, match="redis_down"):
        enqueue_tiktok_comment_ai(tenant_id="t", connection_id="c", comment_id="x", item_id="v")


def test_tiktok_dm_stays_permission_gated_without_connection():
    allowed, reason = tiktok_dm_live_allowed(None)
    assert allowed is False
    assert reason == TIKTOK_DM_GATE_REASON


def test_worker_concurrency_uses_configured_defaults(monkeypatch):
    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_HIGH", "8")
    from importlib import reload

    import services.omnichannel.worker_pool as pool
    import services.queues.config as config

    reload(config)
    reload(pool)
    assert pool.concurrency_for("high_priority") == config.DEFAULT_CONCURRENCY["high_priority"]
    assert pool.concurrency_for("high_priority") > 1


def test_provider_limiter_inflight_enter_exit():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    inner = ProviderLimiter(redis_client)
    limiter = DistributedProviderLimiter(redis_client, inner=inner)
    first = limiter.try_enter(provider="openai", tenant_id="t1")
    assert first.allowed is True
    assert int(redis_client.get("linas:prov:inflight:openai") or 0) == 1
    limiter.exit(provider="openai", tenant_id="t1")
    assert int(redis_client.get("linas:prov:inflight:openai") or 0) == 0


def test_replay_is_delivery_only():
    with pytest.raises(PermissionError):
        replay_delivery_only({"mode": "full", "regenerate_ai": True})
    assert replay_delivery_only({"mode": "delivery_only"})["ok"] is True


def test_operator_outbound_logical_queue():
    assert outbound_logical(channel="instagram", surface="dm") == "outbound_dm"
    assert physical_queue_for("outbound_dm") == "high_priority"
    assert outbound_logical(channel="tiktok", surface="operator") == "outbound_dm"


def test_tiktok_claim_does_not_mark_processed():
    import inspect

    from services.tiktok_business.repository_content import TikTokContentRepository

    src = inspect.getsource(TikTokContentRepository.claim_comment_for_ai)
    assert "ai_processed=True" not in src
    assert "ai_claimed_at" in src


def test_operator_idempotency_uses_sha256_not_hash():
    import inspect

    from services.omnichannel import operator_enqueue

    src = inspect.getsource(operator_enqueue.enqueue_operator_reply)
    assert "hash(text)" not in src
    assert "sha256" in src


def test_meta_429_exception_is_definitive_failure_not_owner_action():
    from services.omnichannel.meta_errors import finish_status_for_send_exception

    err = MetaProviderError("throttled", http_status=429, error_code=613, headers={"Retry-After": "2"})
    status, reason = finish_status_for_send_exception(err)
    assert status == "definitive_failure"
    assert "throttl" in reason
    timeout_status, _ = finish_status_for_send_exception(TimeoutError("maybe accepted"))
    assert timeout_status == "needs_owner_action"


def test_omnichannel_job_types_are_registered():
    from services.queues.handlers import get_handler

    assert get_handler("omnichannel_generate") is not None
    assert get_handler("omnichannel_deliver") is not None
    assert get_handler("whatsapp_intent_deliver") is not None


def test_whatsapp_retry_skips_reconciliation_required():
    import inspect

    from services.whatsapp_cloud import delivery_retry

    src = inspect.getsource(delivery_retry.retry_pending_outbound_intents)
    assert '"reconciliation_required"' not in src
    assert '("failed", "pending")' in src


def test_whatsapp_webhook_marks_processed_after_enqueue():
    import inspect

    from services.whatsapp_cloud import webhook_processor

    src = inspect.getsource(webhook_processor._process_one_event)
    assert src.rindex("enqueue_job") < src.rindex("_complete_claimed_webhook(claim_id)")


def test_load_cert_smoke_zero_loss():
    from scripts.loadtest.run_omnichannel_cert import run_cert

    result = run_cert(minutes=0.02, burst_scale=2.0, duplicate_ratio=0.1)
    assert result["lost"] == 0
    assert result["passed"] is True
    assert result["inbound_rows"] == result["accepted"]
    assert result["outbox_rows"] == result["accepted"]
    assert result["queue_mix"]["high_priority"] > result["queue_mix"]["background"]
