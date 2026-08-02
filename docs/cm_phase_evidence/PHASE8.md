# Phase 8 — Cutover rehearsal + SoT audit

## Objective
Give the team read-only tooling to rehearse a full publish safely and to see, at a glance,
which legacy hardcoded business-fact sources are still in play before flipping
`CM_RUNTIME_MODE=published` for real traffic. Nothing in this phase changes runtime behavior or
deletes any file.

## Implementation
- `services/cm/sot_audit.py::audit_sot_sources()` — a hand-maintained registry of known legacy
  business-fact sources (`price_list.txt`, `style_guide.txt`, `knowledge_base.txt`,
  `system_prompt_template.txt`, `qa_pairs.jsonl`, `DEFAULT_SOCIAL_WHATSAPP_CONTACTS`,
  `DEFAULT_DYNAMIC_MESSAGES`), each checked for on-disk existence and for references inside a
  fixed set of response-generation files. A source is flagged
  `fully_gated_by_cm_runtime_mode: false` when it's referenced by code that does **not** also
  contain the `CM_RUNTIME_MODE == "published"` early-return gate — i.e. it would still be an
  active fallback risk once published mode is the default. Report only; never deletes/edits.
- `services/cm/cutover.py`
  - `seed_rehearsal_tenant_from_draft()` / `run_publish_rehearsal()` — deep-copies the real
    tenant's current draft into an isolated `{tenant}__cutover_rehearsal` tenant and runs a
    real `publish_draft()` against *that* tenant only. The real tenant's draft is only ever
    read; its published pointer is never touched.
  - `evaluate_cutover_readiness()` — aggregates draft validation + the SoT audit into a single
    read-only report. It never flips `CM_RUNTIME_MODE` or `CM_PUBLISH_ENABLED` — those remain
    explicit, human-approved environment changes.

## Acceptance
- SoT audit lists all known legacy sources with existence + reference-site + gating status.
- Rehearsal publish never creates/advances the real tenant's published pointer.
- Rehearsal seeding is idempotent (safe to re-run to pick up the latest draft).
- Readiness gate `ready=True` only reflects hard draft-validation blockers; ungated legacy
  sources are surfaced as a warning list for human review, not auto-blocked.

## Tests
`pytest tests/test_cm_publish_rollback.py` (SoT audit + cutover rehearsal + readiness gate
cases are included in this file alongside publish/rollback, per the task's requested file list).

## Notes
- Enabling `CM_RUNTIME_MODE=published` and/or `CM_PUBLISH_ENABLED=true` in any real environment
  is a server/infra config change and requires explicit approval — this phase only builds the
  tooling; it does not change any default.
- `dashboard/src/pages/Training.jsx` now shows a "moving to Content Management" banner behind a
  new `CM_FAQ_CANONICAL` flag (default `false`), matching the same "no behavior change by
  default" posture.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
