"""Branch address breakdown fields (additive CM schema)."""

from __future__ import annotations

from services.cm.schemas import BranchRecord, BranchesSection, LocalizedLabels
from services.cm.structured_resolver import resolve_branch_facts


def test_branch_record_accepts_address_breakdown() -> None:
    branch = BranchRecord(
        id="b1",
        labels=LocalizedLabels(en="Beirut"),
        street="Hamra St",
        building="Tower A",
        floor="3",
        country="Lebanon",
        maps_url="https://maps.google.com/?q=beirut",
    )
    assert branch.composed_address() == "Hamra St, Tower A, 3, Lebanon"
    dumped = branch.model_dump(mode="json")
    assert dumped["street"] == "Hamra St"
    assert dumped["maps_url"].startswith("https://")


def test_branch_composed_address_falls_back_to_legacy_address() -> None:
    branch = BranchRecord(id="b2", address="Legacy full line")
    assert branch.composed_address() == "Legacy full line"


def test_resolve_branch_facts_includes_maps_url() -> None:
    section = BranchesSection(
        items=[
            BranchRecord(
                id="b3",
                labels=LocalizedLabels(en="Jounieh"),
                street="Coast Rd",
                country="Lebanon",
                maps_url="https://maps.example/jounieh",
            )
        ]
    )
    facts = resolve_branch_facts(section, "b3")
    kinds = {f.kind: f.value for f in facts}
    assert kinds["branch_address"] == "Coast Rd, Lebanon"
    assert kinds["branch_maps_url"] == "https://maps.example/jounieh"
