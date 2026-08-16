"""Branch attachments on Location & hours (schema + media kinds)."""

from __future__ import annotations

from services.cm.article_media import validate_upload
from services.cm.schemas import BranchAttachment, BranchesSection, BranchRecord, LocalizedLabels
from services.cm.structured_resolver import resolve_branch_facts


def test_branch_record_accepts_attachments() -> None:
    branch = BranchRecord(
        id="b1",
        labels=LocalizedLabels(en="Beirut"),
        maps_url="https://maps.google.com/?q=beirut",
        attachments=[
            BranchAttachment(
                id="cmed_img",
                kind="image",
                filename="entrance.jpg",
                mime="image/jpeg",
                size=12,
            ),
            BranchAttachment(
                id="link_1",
                kind="link",
                filename="Parking notes",
                url="https://example.com/parking",
            ),
        ],
    )
    dumped = branch.model_dump(mode="json")
    assert dumped["attachments"][0]["kind"] == "image"
    assert dumped["attachments"][1]["url"].startswith("https://")
    roundtrip = BranchRecord.model_validate(dumped)
    assert len(roundtrip.attachments) == 2


def test_legacy_branch_without_attachments_still_validates() -> None:
    branch = BranchRecord(id="b2", labels=LocalizedLabels(en="Antelias"))
    assert branch.attachments == []


def test_resolve_branch_facts_includes_link_attachments() -> None:
    section = BranchesSection(
        items=[
            BranchRecord(
                id="b3",
                labels=LocalizedLabels(en="Downtown"),
                attachments=[
                    BranchAttachment(
                        id="link_2",
                        kind="link",
                        filename="Menu",
                        url="https://example.com/menu",
                    )
                ],
            )
        ]
    )
    facts = resolve_branch_facts(section, "b3")
    kinds = {f.kind: f.value for f in facts}
    assert "Menu: https://example.com/menu" in kinds["branch_link"]


def test_validate_upload_accepts_mp4_video() -> None:
    ok = validate_upload(filename="tour.mp4", content_type="video/mp4", size=2048)
    assert ok["ok"] is True
    assert ok["kind"] == "video"
    assert ok["mime"] == "video/mp4"
