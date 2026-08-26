"""Guards, stub HTTP classification, and TikTok pagination cursor contracts."""

from __future__ import annotations

import json
from urllib.request import urlopen

import pytest

from scripts.loadtest.omnichannel_cert_guards import CertGuardError, assert_staging_cert_allowed, sanitize_text
from scripts.loadtest.omnichannel_stub_http import start_stub_server
from services.omnichannel.classify import classify_http_delivery
from services.tiktok_business.comment_sync import persist_comment_page_cursor
from services.tiktok_business.config import MAX_COMMENT_PAGES_PER_VIDEO


def test_guards_reject_production_and_require_flag(monkeypatch):
    monkeypatch.delenv("LINAS_OMNI_CERT_STAGING", raising=False)
    with pytest.raises(CertGuardError, match="LINAS_OMNI_CERT_STAGING"):
        assert_staging_cert_allowed(
            target_url="http://127.0.0.1:9",
            tenant_id="omni-cert-t1",
            events_per_minute=10,
            duration_seconds=1,
        )
    monkeypatch.setenv("LINAS_OMNI_CERT_STAGING", "1")
    with pytest.raises(CertGuardError, match="production_host"):
        assert_staging_cert_allowed(
            target_url="https://www.linasaibot.com/api",
            tenant_id="omni-cert-t1",
            events_per_minute=10,
            duration_seconds=1,
        )
    with pytest.raises(CertGuardError, match="test_tenant"):
        assert_staging_cert_allowed(
            target_url="http://127.0.0.1:8080",
            tenant_id="linas",
            events_per_minute=10,
            duration_seconds=1,
        )


def test_guards_allow_loopback_cert_tenant(monkeypatch):
    monkeypatch.setenv("LINAS_OMNI_CERT_STAGING", "1")
    assert_staging_cert_allowed(
        target_url="http://127.0.0.1:18080/inbound",
        tenant_id="omni-cert-local",
        events_per_minute=1900,
        duration_seconds=3600,
        estimated_openai_usd=0.0,
    )


def test_sanitize_strips_phone_and_email():
    text = sanitize_text("call +961 71 000 000 or a@b.co please")
    assert "+961" not in text
    assert "a@b.co" not in text


def test_stub_http_modes_classify():
    from urllib.error import HTTPError

    server, base = start_stub_server()
    try:
        cases = [
            ("ok", 200, "success", False),
            ("429", 429, "transient", True),
            ("meta613", 429, "transient", True),
            ("500", 500, "transient", True),
            ("expired", 401, "permission_blocked", False),
        ]
        for mode, status, kind, retryable in cases:
            try:
                with urlopen(f"{base}/p?mode={mode}", timeout=3) as resp:
                    body = resp.read()
                    headers = dict(resp.headers)
                    got = int(resp.status)
            except HTTPError as exc:
                body = exc.read()
                headers = dict(exc.headers or {})
                got = int(exc.code)
            assert got == status
            payload = json.loads(body.decode()) if body.startswith(b"{") else {}
            nested = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = str((nested or {}).get("code") or "")
            decision = classify_http_delivery(http_status=got, provider_code=code, headers=headers)
            assert decision.kind == kind
            assert decision.retryable is retryable
        with urlopen(f"{base}/p?mode=malformed", timeout=3) as resp:
            raw = resp.read()
        assert raw == b"<not-json>"
        decision = classify_http_delivery(http_status=200, malformed_response=True, submitted=False)
        assert decision.kind == "transient"
        submitted = classify_http_delivery(http_status=504, submitted=True)
        assert submitted.kind == "ambiguous"
        assert submitted.retryable is False
    finally:
        server.shutdown()


def test_comment_pagination_persists_cursor_when_capped():
    stored, truncated = persist_comment_page_cursor(
        page_number=MAX_COMMENT_PAGES_PER_VIDEO,
        page_limit=MAX_COMMENT_PAGES_PER_VIDEO,
        has_more=True,
        cursor="next-page",
    )
    assert truncated is True
    assert stored == "next-page"
    done, truncated_done = persist_comment_page_cursor(page_number=1, page_limit=3, has_more=False, cursor="x")
    assert done == ""
    assert truncated_done is False


def test_mix_event_does_not_serialize_all_traffic_on_forty_conversations():
    from scripts.loadtest.omnichannel_cert_runtime import mix_event

    keys = {mix_event(seq=i, tenant_id="omni-cert-local", nonce="t").conversation_key for i in range(200)}
    assert len(keys) > 40
