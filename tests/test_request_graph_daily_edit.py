"""Request-rule save/delete share one daily-edit slot with the CM draft."""

from __future__ import annotations

from inspect import getsource

from services.customer_ai.actions.request_fields import merge_fields_for_persist, published_request_fields
from services.request_graphs.cm_sync import publish_with_optional_draft


def test_publish_and_delete_use_one_guarded_edit() -> None:
    from modules.cm_request_graphs_api import request_graph_delete, request_graph_publish

    pub = getsource(request_graph_publish)
    assert pub.count("guarded_edit(") == 1
    assert "publish_with_optional_draft" in pub
    assert "require_permission" in pub
    delete = getsource(request_graph_delete)
    assert delete.count("guarded_edit(") == 1
    assert "delete_with_optional_draft" in delete
    assert "require_permission" in delete


def test_publish_helper_writes_draft_before_graph() -> None:
    src = getsource(publish_with_optional_draft)
    assert src.index("_optional_draft") < src.index("publish_graph")
    assert "write_request_draft" in getsource(
        __import__("services.request_graphs.cm_sync", fromlist=["_optional_draft"])._optional_draft
    )


def test_published_request_fields_fail_closed_without_db() -> None:
    assert published_request_fields("", "APPOINTMENT") == {}
    assert published_request_fields("t1", "UNKNOWN") == {}


def test_merge_fields_for_persist_keeps_values_and_published_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.customer_ai.actions.request_fields.published_request_fields",
        lambda _tid, _kind: {"collected_fields": {"name": "", "date": ""}, "graph_id": "g1"},
    )
    assert merge_fields_for_persist("t1", "APPOINTMENT", {"name": "Ada"}) == {"name": "Ada", "date": ""}
    assert merge_fields_for_persist("t1", "APPOINTMENT", None) == {"name": "", "date": ""}
