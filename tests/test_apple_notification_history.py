"""Notification-history full pagination for Apple ASSN reconcile."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.apple_notification_reconcile import _process_history_pages
from services.apple_app_store_client import AppleAppStoreClient


def test_iter_notification_history_two_pages() -> None:
    client = AppleAppStoreClient()
    pages = [
        {
            "notificationHistory": [{"signedPayload": "a.b.c"}],
            "hasMore": True,
            "paginationToken": "page-2-token",
        },
        {
            "notificationHistory": [{"signedPayload": "d.e.f"}],
            "hasMore": False,
        },
    ]
    tokens: list[str | None] = []

    def _fake_get(
        start_ms: int,
        end_ms: int,
        *,
        notification_type: str | None = None,
        pagination_token: str | None = None,
        only_failures: bool = False,
    ) -> dict[str, Any]:
        tokens.append(pagination_token)
        return pages[len(tokens) - 1]

    client.get_notification_history = _fake_get  # type: ignore[method-assign]
    got = list(client.iter_notification_history(1, 2, max_pages=100))
    assert len(got) == 2
    assert tokens == [None, "page-2-token"]
    assert got[0]["hasMore"] is True
    assert got[1]["hasMore"] is False


def test_iter_notification_history_stops_without_token() -> None:
    client = AppleAppStoreClient()
    calls = {"n": 0}

    def _fake_get(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls["n"] += 1
        return {"notificationHistory": [], "hasMore": True}

    client.get_notification_history = _fake_get  # type: ignore[method-assign]
    got = list(client.iter_notification_history(1, 2, max_pages=100))
    assert len(got) == 1
    assert calls["n"] == 1


def test_process_history_pages_aggregates_multi_page(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        {
            "notificationHistory": [
                {"signedPayload": "page1.one.sig"},
                {"signedPayload": "page1.two.sig"},
            ],
            "hasMore": True,
            "paginationToken": "tok2",
        },
        {
            "notificationHistory": [{"signedPayload": "page2.one.sig"}],
            "hasMore": False,
        },
    ]
    state = {"i": 0}

    def _iter(*_a: Any, **_k: Any):
        while state["i"] < len(pages):
            page = pages[state["i"]]
            state["i"] += 1
            yield page

    monkeypatch.setattr(
        "services.apple_app_store_client.apple_app_store_client.iter_notification_history",
        _iter,
    )

    outcomes = [
        {"ok": True, "duplicate": False},
        {"ok": True, "duplicate": True},
        {"ok": True, "duplicate": False},
    ]

    def _process(body: dict[str, Any]) -> dict[str, Any]:
        return outcomes.pop(0)

    monkeypatch.setattr(
        "services.apple_iap_processor.process_notification_v2",
        _process,
    )
    summary = _process_history_pages(start_ms=1, end_ms=2, notification_type="")
    assert summary == {
        "ok": True,
        "processed": 3,
        "duplicates": 1,
        "errors": 0,
        "pages": 2,
    }


def test_process_history_pages_respects_max_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    def _iter(*_a: Any, max_pages: int = 100, **_k: Any):
        for i in range(max_pages):
            yield {
                "notificationHistory": [{"signedPayload": f"p.{i}.x"}],
                "hasMore": True,
                "paginationToken": f"t{i}",
            }

    monkeypatch.setattr(
        "services.apple_app_store_client.apple_app_store_client.iter_notification_history",
        _iter,
    )
    monkeypatch.setattr(
        "services.apple_iap_processor.process_notification_v2",
        lambda _body: {"ok": True, "duplicate": False},
    )
    summary = _process_history_pages(start_ms=1, end_ms=2, notification_type="", max_pages=3)
    assert summary["pages"] == 3
    assert summary["processed"] == 3
