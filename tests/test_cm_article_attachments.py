"""CM article case-example attachments (schema, media store, index text)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.article_media import (
    format_attachments_block,
    store_article_media,
    validate_upload,
)
from services.cm.schemas import ArticleAttachment, ArticleRecord, KnowledgeSection
from services.cm.semantic_index import _article_entries


def test_article_record_accepts_attachments() -> None:
    article = ArticleRecord(
        id="a1",
        title="Intake forms",
        body="How forms look when filled.",
        attachments=[
            ArticleAttachment(
                id="cmed_abc",
                kind="image",
                caption="Use when customer asks what a filled intake form looks like",
                mime="image/jpeg",
                filename="filled.jpg",
                size=12,
            )
        ],
    )
    dumped = article.model_dump(mode="json")
    assert dumped["attachments"][0]["caption"].startswith("Use when")
    roundtrip = ArticleRecord.model_validate(dumped)
    assert roundtrip.attachments[0].id == "cmed_abc"


def test_article_record_accepts_video_and_link_attachments() -> None:
    article = ArticleRecord(
        id="a3",
        title="Laser guide",
        body="Suitable areas.",
        updated_at="2026-08-16T10:00:00Z",
        attachments=[
            ArticleAttachment(
                id="cmed_vid",
                kind="video",
                caption="Show aftercare clip",
                mime="video/mp4",
                filename="aftercare-video.mp4",
                size=800_000,
                duration_seconds=84,
            ),
            ArticleAttachment(
                id="link_1",
                kind="link",
                caption="Official page",
                filename="example.com",
                url="https://example.com/guide",
            ),
        ],
    )
    dumped = article.model_dump(mode="json")
    assert dumped["attachments"][0]["kind"] == "video"
    assert dumped["attachments"][0]["duration_seconds"] == 84
    assert dumped["attachments"][1]["url"].startswith("https://")
    roundtrip = ArticleRecord.model_validate(dumped)
    assert roundtrip.attachments[1].kind == "link"


def test_validate_upload_accepts_mp4() -> None:
    ok = validate_upload(filename="clip.mp4", content_type="video/mp4", size=1024)
    assert ok["ok"] is True
    assert ok["kind"] == "video"


def test_article_record_default_attachments_empty() -> None:
    article = ArticleRecord(id="a2", title="Plain", body="text only")
    assert article.attachments == []


def test_validate_upload_rejects_bad_mime() -> None:
    bad = validate_upload(filename="x.exe", content_type="application/x-msdownload", size=10)
    assert bad["ok"] is False
    assert bad["error"] == "unsupported_mime"


def test_store_and_format_attachments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))

    stored = store_article_media(
        tenant_id="t1",
        user_id="u1",
        filename="case.txt",
        content=b"Line A\nLine B",
        content_type="text/plain",
    )
    assert stored["ok"] is True
    mid = str(stored["media_id"])

    block = format_attachments_block(
        [
            {
                "id": mid,
                "kind": "file",
                "caption": "Send when quoting package A",
                "mime": "text/plain",
                "filename": "case.txt",
            }
        ],
        tenant_id="t1",
    )
    assert "CASE EXAMPLES" in block
    assert "Send when quoting package A" in block
    assert "Line A" in block


def test_article_entries_include_captions() -> None:
    knowledge = KnowledgeSection(
        items=[
            ArticleRecord(
                id="a1",
                title="Forms",
                body="Body text",
                status="active",
                attachments=[
                    ArticleAttachment(
                        id="cmed_x",
                        kind="image",
                        caption="filled form example for laser intake",
                        mime="image/png",
                        filename="filled.png",
                    )
                ],
            )
        ]
    )
    entries = _article_entries(knowledge.model_dump(mode="json"), "knowledge")
    assert len(entries) == 1
    _sid, _kind, _lang, text, meta = entries[0]
    assert "filled form example for laser intake" in text
    assert "CASE EXAMPLES" in text
    assert meta.get("attachment_count") == 1
