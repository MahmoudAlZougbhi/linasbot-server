"""Pytest fixtures for Customer Reply AI V2 tests."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import install_mocked_openai_embeddings


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("CUSTOMER_MEDIA_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LINAS_CUSTOMER_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("LINAS_CUSTOMER_ANSWER_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("LINAS_CUSTOMER_RETRIEVAL_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("MAX_CUSTOMER_RETRIEVAL_ROUNDS", "2")
    monkeypatch.setenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS", "1.5")
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "true")
    install_mocked_openai_embeddings(monkeypatch)
    from services.customer_reply_v2.manifest import clear_manifest_cache

    clear_manifest_cache()
    monkeypatch.setattr(
        "services.credit_ai_gate.ai_generation_blocked",
        lambda *_a, **_k: False,
    )
    return tmp_path
