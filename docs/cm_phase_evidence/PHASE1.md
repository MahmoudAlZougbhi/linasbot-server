# Phase 1 — CLEAN

## Objective
Schemas, validators, publish gate, RBAC contentPublish, UI IA cards.

## Changed
- services/cm/schemas.py, notes_validation.py, conflict_validation.py, publish_gate.py, atomic_io.py
- dashboard permissions contentPublish
- cmSections.js landing IA

## Gates
- mypy/ruff on schemas: passed (with full suite later)
- ContentManagers landing tests: passed

## Audit
CLEAN — Notes deterministic validators; Restricted hard blockers encoded.
