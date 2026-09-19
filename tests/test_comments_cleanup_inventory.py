"""Comments media cache is tenant-scoped; Graph-poll modules stay deleted."""

from __future__ import annotations

from pathlib import Path

from services.brain.media.cache import analysis_key

ROOT = Path(__file__).resolve().parents[1]


def test_post_media_cache_key_is_tenant_safe() -> None:
    left = analysis_key(tenant_id="shop-a", post_id="post-1")
    right = analysis_key(tenant_id="shop-b", post_id="post-1")
    assert left != right
    assert "shop-a" in left
    assert "shop-b" in right


def test_legacy_comment_generate_and_graph_poll_modules_are_gone() -> None:
    assert not (ROOT / "services/integrations/meta/meta_comment_reply_generate.py").exists()
    assert not (ROOT / "services/integrations/meta/meta_social_comment_sync.py").exists()
    assert not (ROOT / "services/integrations/meta/meta_comment_sync_cursors.py").exists()
