# Phase 3 — FAQ + structured

## Objective
Bridge CM FAQ authoring to the existing 4-language Local Q&A pipeline (Franco→Arabic answers
preserved) without duplicating Q&A storage; CM's `faq` draft section tracks group metadata only.

## Implementation
- `services/cm/faq_integration.py` — `create_faq_pair()` translates/creates 4-language variants
  via the existing `LocalQAService` + `language_detection_service.translate_training_pair`
  pipeline, appends to `qa_pairs.jsonl`, then mirrors group id/tags/variant metadata into the
  CM `faq` draft section (optimistic-concurrency `put_draft`). `list_faq_groups()` reads the
  mirrored draft for the dashboard.
- `modules/cm_faq_api.py` — `GET /api/cm/faq` (list groups) and `POST /api/cm/faq` (create,
  requires `contentManagers` permission).

## Acceptance
- Franco input question → answer stored/served in Arabic script (frozen `RESPONSE_LANGUAGE_MAP`).
- Every create produces 4 language variants (ar/en/fr/franco).
- Exact/direct FAQ match still resolves before any semantic step (`FAQ_EXACT_THRESHOLD = 0.90`).
- CM `faq` draft section never becomes the source of Q&A text — `qa_pairs.jsonl` remains
  authoritative; the draft only mirrors group ids/tags for the CM UI.

## Tests
`pytest tests/test_cm_faq_lang.py`

## Notes
No production `qa_pairs.jsonl` is touched by tests — `LINASBOT_DATA_ROOT` is redirected per test.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
