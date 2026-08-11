"""Booking-related numeric IDs used across the bot (aligned with CRM + slot rules)."""

from __future__ import annotations

# Branches
BEIRUT_BRANCH_ID = 1
ANTELIAS_BRANCH_ID = 2

# Services (common; full list from GET /services)
HAIR_MEN = 1
HAIR_WOMEN = 12
TATTOO_SERVICE_ID = 13
CO2_SERVICE_IDS: frozenset[int] = frozenset({2, 11})
WHITENING_SERVICE_IDS: frozenset[int] = frozenset({4, 5, 14})

LASER_HAIR_REMOVAL_SERVICE_IDS: frozenset[int] = frozenset({HAIR_MEN, HAIR_WOMEN})

# Machines that are hair-removal class in current CRM mapping (not Pico/tattoo).
# Trio (id=10) is no longer available.
HAIR_REMOVAL_MACHINE_IDS: frozenset[int] = frozenset({9, 13, 15})

# Services that can be booked without selecting a machine.
# As requested: tattoo removal + CO2 laser + whitening.
MACHINE_OPTIONAL_SERVICE_IDS: frozenset[int] = frozenset(
    set(CO2_SERVICE_IDS) | set(WHITENING_SERVICE_IDS) | {TATTOO_SERVICE_ID}
)

DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS: frozenset[int] = frozenset({1, 2, 4, 5, 11, 12, 13, 14})

BOOKING_TIMEZONE_LABEL = "Asia/Beirut"


def service_requires_machine(service_id: int | None) -> bool:
    """Only laser hair removal services use customer-selected machines."""
    if service_id is None:
        return False
    return int(service_id) in LASER_HAIR_REMOVAL_SERVICE_IDS


# Backward-compatible alias used by booking_fsm / intent_pipeline.
_service_requires_machine = service_requires_machine

