"""Universal AI Setup resources reuse CM attachments (no second store)."""

from __future__ import annotations

import pytest

from services.cm.resource_attachment import (
    ResourceAttachment,
    customer_resource_descriptors,
    resource_summary,
    validate_owner_resource_fields,
)
from services.cm.schemas import ArticleAttachment, ArticleRecord, BranchAttachment, BranchRecord
from services.cm.setup_resources import resolve_published_resource, summary_for_item
from tests.cm_test_helpers import publish_test_content

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def test_owner_resource_requires_title_and_description():
    assert validate_owner_resource_fields(title="", description="x", kind="image")["error"] == "title_required"
    assert (
        validate_owner_resource_fields(title="Before", description="", kind="image")["error"] == "description_required"
    )
    assert (
        validate_owner_resource_fields(title="Book", description="Send when booking", kind="link")["error"]
        == "url_required"
    )
    ok = validate_owner_resource_fields(
        title="Book",
        description="Send when booking",
        kind="link",
        url="https://example.test/book",
    )
    assert ok["ok"] is True


def test_legacy_caption_attachment_still_validates():
    att = ArticleAttachment(id="cmed_legacy", kind="image", caption="Use when asked", filename="before.png")
    dumped = att.model_dump(mode="json")
    assert dumped["caption"] == "Use when asked"
    assert dumped["title"] == ""
    assert dumped["status"] == "active"


def test_resource_summary_counts_only_active():
    atts = [
        ResourceAttachment(id="a", kind="image", title="Before", description="before", status="active"),
        ResourceAttachment(id="b", kind="image", title="Draft", description="d", status="draft"),
        ResourceAttachment(id="c", kind="video", title="Session", description="v", status="active"),
        ResourceAttachment(id="d", kind="file", title="PDF", description="p", status="deleted"),
        ResourceAttachment(
            id="e",
            kind="link",
            title="Book",
            description="book",
            url="https://example.test",
            status="active",
        ),
    ]
    summary = resource_summary(atts)
    assert summary == {"images": 1, "videos": 1, "files": 0, "links": 1, "has_resources": True}
    descriptors = customer_resource_descriptors(atts, source_item_id="knowledge:kn_women")
    refs = {row["resource_ref"] for row in descriptors}
    assert refs == {"a", "c", "e"}
    blob = str(descriptors)
    assert "https://example.test" not in blob
    assert "storage" not in blob.lower()
    assert all("resource_ref" in row and "title" in row and "description" in row for row in descriptors)


def test_article_and_branch_keep_title_description():
    article = ArticleRecord(
        id="kn_women",
        title="Laser Hair Removal Women",
        body="Women-specific content.",
        attachments=[
            ArticleAttachment(
                id="res_women_before",
                kind="image",
                title="Women Before Laser Hair Removal",
                description="Send this image when the customer asks for a before-treatment example for women.",
                filename="women-before.png",
                mime="image/png",
                sort_order=1,
            )
        ],
    )
    dumped = article.model_dump(mode="json")
    assert dumped["attachments"][0]["title"].startswith("Women Before")
    branch = BranchRecord(
        id="br_1",
        attachments=[
            BranchAttachment(
                id="map1",
                kind="link",
                title="Map",
                description="Parking map",
                url="https://maps.example",
            )
        ],
    )
    assert branch.attachments[0].title == "Map"


@pytest.mark.asyncio
async def test_published_resource_tenant_and_parent_isolation(v2_env):
    women = {
        "id": "kn_women",
        "title": "Laser Hair Removal Women",
        "body": "Women file.",
        "status": "active",
        "attachments": [
            {
                "id": "res_women_before",
                "kind": "image",
                "title": "Women Before",
                "description": "Women before example.",
                "filename": "women-before.png",
                "status": "active",
            },
            {
                "id": "res_women_draft",
                "kind": "image",
                "title": "Unpublished shot",
                "description": "Still draft.",
                "filename": "draft.png",
                "status": "draft",
            },
        ],
    }
    general = {
        "id": "kn_general",
        "title": "Laser Hair Removal Service",
        "body": "Generic file.",
        "status": "active",
        "attachments": [
            {
                "id": "res_general_before",
                "kind": "image",
                "title": "General Before",
                "description": "Generic before example.",
                "filename": "general-before.png",
                "status": "active",
            }
        ],
    }
    await publish_test_content("t_res_a", {"knowledge": {"items": [women, general]}})
    await publish_test_content(
        "t_res_b",
        {
            "knowledge": {
                "items": [
                    {
                        "id": "kn_other",
                        "title": "Other",
                        "body": "Other tenant",
                        "status": "active",
                        "attachments": [
                            {
                                "id": "res_other",
                                "kind": "image",
                                "title": "Other",
                                "description": "Other tenant image.",
                                "status": "active",
                            }
                        ],
                    }
                ]
            }
        },
    )

    ok = resolve_published_resource(
        tenant_id="t_res_a",
        resource_ref="res_women_before",
        allowed_source_ids=["knowledge:kn_women"],
    )
    assert ok["ok"] is True
    assert ok["resource"]["source_item_id"] == "knowledge:kn_women"
    assert ok["resource"]["tenant_id"] == "t_res_a"

    cross_file = resolve_published_resource(
        tenant_id="t_res_a",
        resource_ref="res_general_before",
        allowed_source_ids=["knowledge:kn_women"],
    )
    assert cross_file["ok"] is False
    assert cross_file["error"] == "resource_not_on_selected_file"

    draft = resolve_published_resource(tenant_id="t_res_a", resource_ref="res_women_draft")
    assert draft["ok"] is False
    assert draft["error"] == "resource_not_found"

    invented = resolve_published_resource(tenant_id="t_res_a", resource_ref="res_invented")
    assert invented["ok"] is False

    cross_tenant = resolve_published_resource(tenant_id="t_res_a", resource_ref="res_other")
    assert cross_tenant["ok"] is False

    other_ok = resolve_published_resource(tenant_id="t_res_b", resource_ref="res_other")
    assert other_ok["ok"] is True
    assert other_ok["resource"]["tenant_id"] == "t_res_b"

    summary = summary_for_item(women)
    assert summary["images"] == 1
    assert summary["has_resources"] is True
