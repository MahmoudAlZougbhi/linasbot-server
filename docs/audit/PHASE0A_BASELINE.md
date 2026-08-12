# Phase 0A — Inventory and baseline

Generated: 2026-08-12

## Tracked file count

- `git ls-files` count: **1539**
- `FILE_INVENTORY.csv` row count: **1539** (must match)
- Must fully read (hand-written / config source): **1440**
- Generated / binary / media / data dumps (`fully_read=NOT_APPLICABLE`): **99**

## Inventory columns

Matches Phase 0B required file-level output fields.

## Baseline notes

- Branch: `chore/project-cleanup-reorg`
- Prior inventory `TRACKED_FILE_INVENTORY.csv` is superseded by `FILE_INVENTORY.csv` (stale 1283-row shell).
- Application source will **not** be modified during Phase 0A/0B.
- Phase 0B proceeds immediately in sequence batches of 20–30 files.

## Over-500 hand-written check (inventory snapshot)

Count of must-read files with line_count > 500: **0**

## Next

Phase 0B file-by-file forensic review starting at sequence_number 1.

## Phase 0C correction

Live `git ls-files` at Phase 0A birth (`82152df` / parent `d4f16c55`) and at Phase 0C is **1544**, not 1539.
Inventory SoT is **1544 rows = current tracked files including docs/audit**. App-only count excluding `docs/audit/**` is **1522**.
