"""WAVE L freezes: save-time chunker only; no customer_ai revival; inbound never calls it."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_customer_ai_package_not_revived() -> None:
    assert not (ROOT / "services/customer_ai").exists()
    assert not (ROOT / "services/cm").exists()
    assert not (ROOT / "services/search_metadata").exists()


def test_luna_chunker_not_imported_outside_compiler() -> None:
    offenders: list[str] = []
    for folder in ("services", "modules"):
        for path in (ROOT / folder).rglob("*.py"):
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if rel.startswith("services/brain/compiler/"):
                continue
            text = path.read_text(encoding="utf-8")
            if "luna_chunker" in text:
                offenders.append(rel)
    assert not offenders, offenders


def test_inbound_reply_path_has_no_luna_chunker() -> None:
    roots = (
        ROOT / "services/brain/reply",
        ROOT / "services/brain/comments",
        ROOT / "services/brain/media",
        ROOT / "services/brain/retrieve/orchestrate.py",
    )
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if "luna_chunker" in text or "apply_save_chunks" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_voyage_index_still_voyage_embeddings() -> None:
    index_job = (ROOT / "services/brain/search/index_job.py").read_text(encoding="utf-8")
    contextual = (ROOT / "services/brain/search/contextual_index.py").read_text(encoding="utf-8")
    storage = (ROOT / "services/ai_setup/storage.py").read_text(encoding="utf-8")
    compiler = (ROOT / "services/brain/compiler/chunks.py").read_text(encoding="utf-8")
    init = (ROOT / "services/brain/compiler/__init__.py").read_text(encoding="utf-8")
    assert "embed_texts" in index_job
    assert "embed_contextual_groups" in contextual
    assert "luna_chunker" not in index_job
    assert "luna_chunker" not in contextual
    assert "chunk_document" not in index_job
    assert "chunk_document" not in contextual
    assert "def chunk_document" not in compiler
    assert "chunk_document" not in init
    assert "apply_save_chunks" in storage
    assert "luna" not in storage.lower()


def test_live_py_never_imports_chunk_document() -> None:
    offenders: list[str] = []
    for folder in ("services", "modules"):
        for path in (ROOT / folder).rglob("*.py"):
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            text = path.read_text(encoding="utf-8")
            if "chunk_document" in text:
                offenders.append(rel)
    assert not offenders, offenders


def test_chunker_model_not_contiguous_retrieval_id() -> None:
    chunker = (ROOT / "services/brain/compiler/luna_chunker.py").read_text(encoding="utf-8")
    policy = (ROOT / "services/brain/model_policy.py").read_text(encoding="utf-8")
    assert "gpt-5.6-luna" not in chunker
    assert "gpt-5.6-luna" not in policy
    assert "_CHUNK_MODEL" in chunker
