"""Public landing stats: aggregate-only, no PII, real sources."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from modules.api_security import is_public_api
from services.public_landing_stats import collect_public_landing_stats, reset_public_landing_stats_cache


def _write_entitlement(root: Path, tenant_id: str, *, status: str, plan_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{tenant_id}.json").write_text(
        json.dumps({"tenant_id": tenant_id, "status": status, "plan_id": plan_id}),
        encoding="utf-8",
    )


def _write_flow(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture()
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


def test_landing_stats_is_public_api() -> None:
    assert is_public_api("GET", "/api/public/landing-stats")
    assert not is_public_api("POST", "/api/public/landing-stats")


def test_collects_subscribers_and_ai_replies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reset_public_landing_stats_cache()
    ents = tmp_path / "ent"
    _write_entitlement(ents, "alpha", status="active", plan_id="growth")
    _write_entitlement(ents, "beta", status="trial", plan_id="lite")
    _write_entitlement(ents, "gone", status="canceled", plan_id="starter")
    _write_entitlement(ents, "noneplan", status="active", plan_id="none")

    now = datetime.now(tz=UTC)
    log = tmp_path / "activity_flow.jsonl"
    _write_flow(
        log,
        [
            {
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "tenant_id": "alpha",
                "channel": "instagram",
                "source": "gpt",
                "bot_to_user": True,
            },
            {
                "timestamp": (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "alpha",
                "channel": "instagram_comment",
                "source": "gpt",
                "bot_to_user": True,
            },
            {
                "timestamp": (now - timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "beta",
                "channel": "whatsapp",
                "source": "gpt",
                "bot_to_user": True,
            },
            {
                "timestamp": (now - timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "alpha",
                "channel": "instagram",
                "source": "error",
                "bot_to_user": True,
            },
            {
                "timestamp": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "alpha",
                "channel": "owner",
                "source": "owner_ai",
                "bot_to_user": True,
            },
        ],
    )
    monkeypatch.setattr("services.public_landing_stats._count_requests", lambda: (3, "customer_requests_db"))
    payload = collect_public_landing_stats(
        entitlements_root=ents,
        log_path=str(log),
        use_cache=False,
    )
    assert payload["success"] is True
    assert payload["businesses_using_linas"] == 2
    assert payload["businesses_source"] == "entitlements_files"
    assert payload["messages_replied"] == 2
    assert payload["comments_replied"] == 1
    assert payload["ai_replies"] == 3
    assert payload["requests"] == 3
    assert "email" not in json.dumps(payload)
    assert "tenant_id" not in json.dumps(payload)


def test_endpoint_returns_aggregates(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    reset_public_landing_stats_cache()
    monkeypatch.setattr(
        "modules.public_landing_stats_api.collect_public_landing_stats",
        lambda: {
            "success": True,
            "businesses_using_linas": 4,
            "businesses_source": "entitlements_files",
            "messages_replied": 10,
            "comments_replied": 2,
            "ai_replies": 12,
            "activity_source": "interaction_logs",
            "scanned_entries": 12,
            "requests": 1,
            "requests_source": "customer_requests_db",
            "refresh_seconds": 20,
            "generated_at": "2026-08-16T00:00:00Z",
        },
    )
    response = app_client.get("/api/public/landing-stats")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["businesses_using_linas"] == 4
    assert body["ai_replies"] == 12
    assert body["comments_replied"] == 2
