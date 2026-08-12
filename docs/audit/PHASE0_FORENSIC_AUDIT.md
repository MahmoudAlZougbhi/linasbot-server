# Phase 0 — Complete forensic audit (0A + 0B)

## Rules in force

- Audit-only: no application behavior or application source changes.
- Only `docs/audit/*` may be updated/committed during this phase.
- Every tracked path from `git ls-files -z` gets one inventory row.
- Hand-written / config source: `fully_read=YES` required before `review_status=COMPLETE`.
- Generated / binary / media / data dumps: `fully_read=NOT_APPLICABLE` with usage/metadata review.
- Stop for owner approval when audit gate is met — no Phase 1 implementation from this phase.

## Phase 0A status

- `docs/audit/FILE_INVENTORY.csv` regenerated to **1539** rows (= tracked count).
- `docs/audit/PHASE0A_BASELINE.md` written.
- Prior `TRACKED_FILE_INVENTORY.csv` superseded (stale shell).

## Phase 0B status

- Method: deterministic batches of 20–30 by `sequence_number`.
- Log: `docs/audit/FILE_REVIEW_LOG.md`.
- In progress — see review log for COMPLETE count.
