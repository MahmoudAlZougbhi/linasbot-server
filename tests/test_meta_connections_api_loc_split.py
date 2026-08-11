"""LOC split: meta_connections_api helpers/lifecycle under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_meta_connections_api_modules_under_500_lines() -> None:
    assert _line_count("modules/meta_connections_api.py") < 500
    assert _line_count("modules/meta_connections_api_helpers.py") < 500
    assert _line_count("modules/meta_connections_api_lifecycle.py") < 500


def test_meta_connections_api_preserves_helper_exports() -> None:
    from modules.meta_connections_api_helpers import _query_text, _tenant_binding
    from modules import meta_connections_api

    assert meta_connections_api._query_text is _query_text
    assert callable(meta_connections_api.list_meta_connections)
    assert hasattr(meta_connections_api, "meta_connections_api_lifecycle")
