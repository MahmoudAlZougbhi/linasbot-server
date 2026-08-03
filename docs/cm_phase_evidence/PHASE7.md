# Phase 7 — Publish machinery

## Objective
Turn the `501`/hard-403 publish stubs into a real, atomic publish + rollback, gated by
`CM_PUBLISH_ENABLED` (still `false` by default) and `contentPublish` permission.

## Implementation
- `services/cm/publish.py`
  - `publish_draft()` — validates the current draft (`validate_cm`, hard-blocks on Restricted
    conflicts / notes-override errors), writes the draft as a brand-new immutable
    `content_version_id` under `versions/{id}/content/*.json` with per-section checksums,
    builds a semantic index over it (`services/cm/semantic_index.py`), writes a
    `PublishManifest`, and finally flips the tenant's `PublishedPointer` (content + index
    version ids together, never partially) under `tenant_server_lock`.
  - `rollback_to_version()` — restores a **previously published** version's pointer (content +
    index together) from its manifest; never rebuilds content, so it is a pure, fast pointer
    flip.
  - Validation/content-write/index-build (which may `await` a real embedding provider call)
    intentionally run *outside* `tenant_server_lock`, each writing to a brand-new unique path —
    so there is no cross-request contention and no `await` is ever held while blocking the OS
    lock. Only the final pointer read+write is under the lock.
- `modules/cm_api.py` — `POST /api/cm/publish` and `POST /api/cm/versions/{id}/rollback` now
  call the real machinery (still hard-403 via `ensure_publish_enabled()` when
  `CM_PUBLISH_ENABLED` is not true; `422 PUBLISH_BLOCKED` with itemized errors on validation
  failure).

## Bug fixed during this phase
`services/cm/storage.py::tenant_server_lock` was not safe to re-enter from the same thread: a
multi-step caller holding the lock while calling a helper (`get_draft`/`put_draft`) that also
acquires it would self-deadlock, because the underlying `fcntl.flock` is per-open-file-
description, not reentrant across a fresh `open()` even in the same thread. Fixed with a
thread-local re-entrancy guard so nested same-thread calls no-op instead of re-locking.

## Acceptance
- Publish is a hard 403 (`PUBLISH_DISABLED`) whenever `CM_PUBLISH_ENABLED` is not `true`
  (unchanged from Phase 2).
- A validation-blocked draft can never advance the published pointer.
- Two sequential publishes create two distinct immutable versions; the second publish result
  records the prior pointer for audit/rollback.
- Rollback restores both `content_version_id` and `index_version_id` together — never a mixed
  pointer — and fails honestly (`RollbackTargetError`) for an unknown version id.
- Repeated publish calls never deadlock (regression-guarded).

## Tests
`pytest tests/test_cm_publish_rollback.py`

## Notes
No production data was published as part of implementing/testing this phase — all tests run
against `LINASBOT_DATA_ROOT` temp dirs with synthetic tenant ids.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
