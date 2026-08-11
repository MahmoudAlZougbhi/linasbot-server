"""LOC split: meta_oauth graph/webhooks under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services import meta_oauth
from services.meta_oauth_graph import MetaOAuthError as GraphError
from services.meta_oauth_graph import _safe_json as graph_safe_json
from services.meta_oauth_graph import subscribe_binding_webhook as graph_subscribe


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_meta_oauth_modules_under_500_lines() -> None:
    assert _line_count("services/meta_oauth.py") < 500
    assert _line_count("services/meta_oauth_graph.py") < 500


def test_meta_oauth_preserves_public_api() -> None:
    assert meta_oauth.MetaOAuthError is GraphError
    assert meta_oauth._safe_json is graph_safe_json
    assert meta_oauth.subscribe_binding_webhook is graph_subscribe
    assert callable(meta_oauth.begin_meta_business_login)
    assert callable(meta_oauth.complete_meta_business_login)
    assert callable(meta_oauth.disconnect_binding_webhook)
    assert callable(meta_oauth.unsubscribe_binding_webhook)
