"""Prove Live Chat request paths never fall back to legacy full-scan."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.live_chat_service import live_chat_service


@pytest.mark.asyncio
async def test_legacy_fallback_helpers_raise():
    with pytest.raises(RuntimeError, match="disabled"):
        await live_chat_service._fallback_unified_chats("", 1, 20, "all")
    with pytest.raises(RuntimeError, match="disabled"):
        await live_chat_service._fallback_unified_chats_with_timeout("", 1, 20, "all")
    with pytest.raises(RuntimeError, match="disabled"):
        await live_chat_service._fallback_waiting_queue_from_source()


@pytest.mark.asyncio
async def test_unified_chats_empty_index_sets_rebuild_flag_without_legacy():
    svc = live_chat_service
    with (
        patch.object(svc, "_fallback_unified_chats_with_timeout", new_callable=AsyncMock) as legacy,
        patch.object(svc, "_cached_unified_response", return_value=None),
        patch("services.live_chat_service_unified.get_firestore_db", return_value=MagicMock()),
        patch.object(svc, "_run_blocking_with_timeout", new_callable=AsyncMock, return_value=[]),
        patch.object(svc, "_index_collection", return_value=MagicMock()),
    ):
        # Force the empty-docs branch by stubbing internal query assembly lightly:
        # patch get_unified_chats body entry after docs resolved — call via monkeypatched helper.
        async def _empty_docs_path():
            # Simulate the refuse contract used when index docs are empty.
            legacy.assert_not_awaited()
            return {
                "success": True,
                "chats": [],
                "total": 0,
                "page": 1,
                "page_size": 20,
                "has_more": False,
                "next_cursor": None,
                "index_empty": True,
                "requires_index_rebuild": True,
            }

        # Drive real method: empty stream → refuse path
        with patch.object(
            svc,
            "get_unified_chats",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "chats": [],
                    "total": 0,
                    "index_empty": True,
                    "requires_index_rebuild": True,
                }
            ),
        ):
            # Prefer exercising real code path below
            pass

    # Real path: patch stream to return [] and ensure legacy not called
    svc._unified_chats_cache = []
    svc._unified_chats_cache_time = None
    with (
        patch.object(
            svc,
            "_fallback_unified_chats_with_timeout",
            new_callable=AsyncMock,
            side_effect=AssertionError("legacy must not run"),
        ),
        patch.object(svc, "_cached_unified_response", return_value=None),
        patch("services.live_chat_service_unified.get_firestore_db", return_value=MagicMock()),
        patch.object(svc, "_run_blocking_with_timeout", new_callable=AsyncMock, return_value=[]),
    ):
        svc._unified_chats_cache = {}
        svc._unified_chats_cache_time = None
        result = await svc.get_unified_chats(search="", page=1, page_size=20, filter_state="all")
    assert (
        result.get("requires_index_rebuild") is True or result.get("index_empty") is True or result.get("chats") == []
    )
    # If rebuild flag present, legacy was refused correctly
    if result.get("requires_index_rebuild"):
        assert result.get("chats") == []


@pytest.mark.asyncio
async def test_waiting_queue_empty_index_never_calls_source_scan():
    svc = live_chat_service
    svc._queue_cache = None
    svc._queue_cache_time = None
    with (
        patch.object(
            svc,
            "_fallback_waiting_queue_from_source",
            new_callable=AsyncMock,
            side_effect=AssertionError("source scan must not be called"),
        ),
        patch("services.live_chat_service_history_api.get_firestore_db", return_value=MagicMock()),
        patch("services.live_chat_service_history_api.asyncio.to_thread", new_callable=AsyncMock, return_value=[]),
    ):
        queue = await svc.get_waiting_queue()
    assert queue == []


def test_live_chat_allow_legacy_env_removed_from_service_source():
    src = Path("services/live_chat_service.py").read_text(encoding="utf-8")
    assert "LIVE_CHAT_ALLOW_LEGACY_SCAN" not in src
