# Phase 0 — CLEAN

## Objective
Frozen contracts, fixture inventory, restricted defaults, runtime flags.

## Changed
- services/cm/constants.py, paths.py
- tests/fixtures/cm_migration/**
- scripts/cm/inventory_snapshot.py
- tests/test_cm_phase0_contracts.py

## Gates
- pytest test_cm_phase0_contracts: passed
- fixture inventory hashed (not production)

## Audit
CLEAN — contracts match plan §2.4–2.7; no production mutation.
