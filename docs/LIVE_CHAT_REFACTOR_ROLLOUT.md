# Live Chat Refactor Rollout Notes

This rollout record tracks the phased implementation and validation performed during the balanced Live Chat refactor.

## Phase 1 - Contract Baseline + Normalization

- Added API baseline contract documentation in `docs/LIVE_CHAT_API_CONTRACT.md`.
- Introduced shared normalization layer in `services/live_chat_contracts.py`.
- Standardized UTC-aware timestamps on write/read paths in:
  - `utils/utils.py`
  - `services/live_chat_service.py`
- Unified dedupe rules across save/read by reusing shared contract helpers.

Validation:

- Python syntax checks completed for touched backend files.
- Smoke import and basic normalization checks completed.

## Phase 2 - Backend Reliability + Performance

- Added query/cache helper methods in `LiveChatService` to reduce duplicated Firestore traversal logic.
- Switched heavy user conversation reads to bounded parallel fetch helpers.
- Unified cache freshness strategy (`_is_cache_fresh`) for active, queue, and unified chat list caches.
- Normalized conversation docs before read-side shaping.

Validation:

- Backend module syntax checks passed.
- Basic service smoke checks passed.

## Phase 3 - SSE Hardening

- Added dedicated broadcaster service in `services/live_chat_sse_broadcaster.py`.
- Rewired `modules/live_chat_api.py` to stream/broadcast through shared broadcaster instead of ad-hoc global set.
- Added sequence metadata and queue pressure handling for robust fanout.
- Removed direct `_sse_clients` coupling from `utils/utils.py`.

Validation:

- Backend syntax checks passed.
- SSE module import and runtime smoke checks passed.

## Phase 4 - Frontend Modularization + API Cleanup

- Split Live Chat UI concerns into focused modules:
  - `dashboard/src/components/LiveChat/ModernAudioPlayer.js`
  - `dashboard/src/components/LiveChat/ConversationIndicators.js`
  - `dashboard/src/hooks/useLiveChatSSE.js`
  - `dashboard/src/hooks/useLiveChatMediaComposer.js`
- Kept `LiveChat.js` as orchestration for data/state flow.
- Consolidated API base URL and message-fetch normalization:
  - `dashboard/src/utils/apiBaseUrl.js`
  - `dashboard/src/utils/liveChatApi.js`
- Updated `dashboard/src/hooks/useApi.js` and Live Chat consumers to use shared helpers.

Validation:

- IDE lint diagnostics for modified frontend files: no new issues.
- Dashboard build still fails due pre-existing warnings in unrelated files; Live Chat-specific warnings introduced by this refactor were resolved.

## Regression Verification Summary

Executed targeted checks relevant to this refactor:

- Live chat backend module syntax compilation passed.
- Shared contract normalization and dedupe smoke checks passed.
- Frontend lint checks for modified files passed.
- Frontend production build rechecked; only pre-existing unrelated warnings remain.
