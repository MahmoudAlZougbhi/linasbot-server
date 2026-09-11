"""Source authority ranks for contradiction / rerank hints."""

from __future__ import annotations

from typing import Mapping

# Inspected against CM section families used by retrieve/cards.py.
# Higher wins. Do not invent families not present in product model.
AUTHORITY: Mapping[str, int] = {
    "hours": 100,
    "services": 90,
    "products": 90,
    "faq": 85,
    "policies": 80,
    "knowledge": 70,
    "resources": 60,
    "none": 0,
}


def authority_for_family(family: str) -> int:
    return int(AUTHORITY.get((family or "").strip(), 40))


def prefer_higher_authority(left_family: str, right_family: str) -> str:
    if authority_for_family(left_family) >= authority_for_family(right_family):
        return left_family
    return right_family
