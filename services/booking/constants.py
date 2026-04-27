# -*- coding: utf-8 -*-
"""Booking-related numeric IDs used across the bot (aligned with CRM + slot rules)."""

from __future__ import annotations

from typing import FrozenSet

# Branches
BEIRUT_BRANCH_ID = 1
ANTELIAS_BRANCH_ID = 2

# Services (common; full list from GET /services)
HAIR_MEN = 1
HAIR_WOMEN = 12
TATTOO_SERVICE_ID = 13
CO2_SERVICE_IDS: FrozenSet[int] = frozenset({2, 11})
WHITENING_SERVICE_IDS: FrozenSet[int] = frozenset({4, 5, 14})

LASER_HAIR_REMOVAL_SERVICE_IDS: FrozenSet[int] = frozenset({HAIR_MEN, HAIR_WOMEN})

# Machines that are hair-removal class in current CRM mapping (not Pico/tattoo).
# Trio (id=10) is no longer available.
HAIR_REMOVAL_MACHINE_IDS: FrozenSet[int] = frozenset({9, 13, 15})

# Services that can be booked without selecting a machine.
# As requested: tattoo removal + CO2 laser + whitening.
MACHINE_OPTIONAL_SERVICE_IDS: FrozenSet[int] = frozenset(
    set(CO2_SERVICE_IDS) | set(WHITENING_SERVICE_IDS) | {TATTOO_SERVICE_ID}
)

DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS: FrozenSet[int] = frozenset({1, 2, 4, 5, 11, 12, 13, 14})

BOOKING_TIMEZONE_LABEL = "Asia/Beirut"
