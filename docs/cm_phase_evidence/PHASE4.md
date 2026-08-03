# Phase 4 — Migration

## Objective
One-way, idempotent copy from legacy/fixture content into a tenant's CM **draft** (never
published, never production-mutating), flagging Restricted conflicts for human review.

## Implementation
- `services/cm/migration.py` — `migrate_legacy_fixture(source_root, tenant_id)` reads legacy
  `price_list.txt`, `knowledge_base.txt`, `qa_pairs.jsonl`, and `knowledge_files/*.json` from a
  given source root, converts them into CM `faq`/`knowledge`/`care`/`handoff` draft payloads,
  imports `social_contact_routing.DEFAULT_SOCIAL_WHATSAPP_CONTACTS` into the `handoff` draft,
  and archives the original legacy files under the tenant's CM `archive/` dir. IDs are
  deterministic hashes of source content, so re-running migration on unchanged input is a no-op
  (idempotent) rather than creating duplicates.
- Restricted-conflict detection reuses `services/cm/conflict_validation.py` against the
  migrated draft and surfaces a conflict report (e.g. legacy tattoo-removal price rows).
- `scripts/cm/run_migration_dry.py` — CLI that runs migration against a fixture dir and writes
  a JSON conflict report to `docs/cm_phase_evidence/`.

## Acceptance
- Migration only ever writes under `{LINASBOT_DATA_ROOT}/tenants/{tenant}/cm/{draft,archive}`.
- Running migration twice on the same fixture produces the same draft state (no duplicate FAQ
  groups/knowledge/care items).
- Legacy files are archived (not deleted) after migration.
- Restricted conflicts (e.g. tattoo removal price/knowledge) are flagged, not silently dropped.

## Tests
`pytest tests/test_cm_migration.py`

## Notes
Migration never touches `CM_PUBLISH_ENABLED`/published state — output is draft-only until a
human reviews and an operator explicitly publishes.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
