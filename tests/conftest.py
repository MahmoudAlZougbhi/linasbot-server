"""Shared pytest fixtures and deterministic test environment."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

# Deterministic env before any app imports in test modules.
_ROOT = tempfile.mkdtemp(prefix="linas_pytest_")
os.environ.setdefault("LINASBOT_DATA_ROOT", _ROOT)
os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
os.environ.setdefault("LINASLASER_API_TOKEN", "pytest-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")
os.environ.setdefault("ENVIRONMENT", "test")
# Hash embeddings are test-harness only (rejected when CM_RUNTIME_MODE=published or
# outside ENVIRONMENT=test). Published-mode tests override to openai + a mocked transport.
os.environ.setdefault("CM_EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("DISABLE_API_DOCS", "true")
os.environ.pop("ALLOW_DEBUG_SIMULATE_WEBHOOK", None)


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Keep a usable loop for modules that construct asyncio.Lock at import time."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


@pytest.fixture
def enable_faq_plan(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Active starter plan so CM FAQ write tests pass plan entitlements."""
    import services.entitlements_service as es
    from services.entitlements_service import EntitlementsStore

    store = EntitlementsStore(root=tmp_path / "entitlements")
    real_get = store.get

    def get(tenant_id: str):
        ent = real_get(tenant_id)
        if ent.plan_id != "none" and ent.status != "none":
            return ent
        # set_plan() calls get(); use the real getter to avoid recursion.
        store.get = real_get
        try:
            return store.set_plan(
                tenant_id=tenant_id,
                plan_id="starter",
                status="active",
                source="admin",
            )
        finally:
            store.get = get

    monkeypatch.setattr(store, "get", get)
    monkeypatch.setattr(es, "entitlements_store", store)
    return store
