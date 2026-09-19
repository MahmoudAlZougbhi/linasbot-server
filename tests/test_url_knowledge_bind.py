"""Knowledge kind=link is an identity key: pin + scoped + full retrieve, never auto-send."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.ai_setup.knowledge_link_index import normalize_knowledge_url
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.retrieve.url_knowledge_bind import apply_url_knowledge_bind

_SECTIONS = {
    "knowledge": {
        "items": [
            {
                "id": "laser-card",
                "title": "Laser package",
                "body": "Full laser details live on this card.",
                "attachments": [
                    {
                        "id": "lnk-laser",
                        "kind": "link",
                        "title": "Laser URL",
                        "url": "https://www.example.com/laser?utm_source=ig&fbclid=abc",
                        "status": "active",
                    }
                ],
            }
        ]
    }
}


def _pointer() -> SimpleNamespace:
    return SimpleNamespace(content_version_id="v1", revision="v1")


@pytest.mark.asyncio
async def test_known_knowledge_url_pins_and_dual_retrieve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ai_setup.knowledge_link_index.load_published_content",
        lambda _tid: (_pointer(), _SECTIONS),
    )
    scoped = {"ran": False}

    async def fake_scoped(*, tenant_id, query, hits):
        scoped["ran"] = True
        assert hits
        assert "شو" in query or "هيدا" in query or query
        return [
            EvidenceItem(
                evidence_id="knowledge:laser-card:chunk",
                source_family="knowledge",
                source_id="laser-card",
                title="Laser package",
                text="scoped chunk about laser",
                extra={"scoped": True},
            )
        ], True

    monkeypatch.setattr("services.brain.retrieve.url_knowledge_bind.scoped_knowledge_retrieve", fake_scoped)
    full = EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="knowledge:other",
                source_family="knowledge",
                source_id="other",
                title="Other",
                text="full hybrid hit",
            )
        ],
    )
    bundle, meta = await apply_url_knowledge_bind(
        tenant_id="shop",
        message="https://example.com/laser?utm_campaign=x شو هيدا؟",
        full_bundle=full,
    )
    assert meta["url_bind"] is True
    assert meta["scoped_retrieve"] is True
    assert meta["full_retrieve"] is True
    assert meta["auto_send"] is False
    assert scoped["ran"] is True
    ids = {item.evidence_id for item in bundle.items}
    assert "knowledge:laser-card" in ids
    assert "knowledge:other" in ids
    assert "knowledge:laser-card:chunk" in ids
    pinned = next(item for item in bundle.items if item.evidence_id == "knowledge:laser-card")
    assert pinned.extra.get("url_bind") is True


@pytest.mark.asyncio
async def test_unknown_url_does_not_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ai_setup.knowledge_link_index.load_published_content",
        lambda _tid: (_pointer(), _SECTIONS),
    )
    scoped = {"ran": False}

    async def fake_scoped(**_k):
        scoped["ran"] = True
        return [], True

    monkeypatch.setattr("services.brain.retrieve.url_knowledge_bind.scoped_knowledge_retrieve", fake_scoped)
    full = EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="knowledge:other",
                source_family="knowledge",
                source_id="other",
                title="Other",
                text="full hybrid hit",
            )
        ],
    )
    bundle, meta = await apply_url_knowledge_bind(
        tenant_id="shop",
        message="https://unknown.example/nope شو هيدا؟",
        full_bundle=full,
    )
    assert meta.get("url_bind") is False
    assert meta.get("reason") == "unknown_url"
    assert scoped["ran"] is False
    assert [item.evidence_id for item in bundle.items] == ["knowledge:other"]


@pytest.mark.asyncio
async def test_knowledge_url_match_does_not_enqueue_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ai_setup.knowledge_link_index.load_published_content",
        lambda _tid: (_pointer(), _SECTIONS),
    )

    async def fake_scoped(**_k):
        return [], True

    monkeypatch.setattr("services.brain.retrieve.url_knowledge_bind.scoped_knowledge_retrieve", fake_scoped)
    bundle, meta = await apply_url_knowledge_bind(
        tenant_id="shop",
        message="https://example.com/laser",
        full_bundle=EvidenceBundle(outcome="not_found"),
    )
    assert meta["auto_send"] is False
    assert bundle.items
    assert "resource_delivery" not in meta
    assert meta.get("sent") is None


def test_normalize_strips_tracking_and_www() -> None:
    left = normalize_knowledge_url("HTTPS://WWW.Example.com/laser/?utm_source=ig&fbclid=1")
    right = normalize_knowledge_url("http://example.com/laser")
    assert left == right == "example.com/laser"
