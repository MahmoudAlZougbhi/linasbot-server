# Phase 2 — CLEAN

## Objective
Draft storage/API/UI; Publish visibly disabled (hard 403).

## Changed
- services/cm/storage.py, validation.py, preview_packet.py
- modules/cm_api.py
- ContentManagers hub + CmSectionPage + CmPublishPage

## Gates
- test_cm_draft_storage: passed
- Publish API returns 403 with PUBLISH_DISABLED_MESSAGE when CM_PUBLISH_ENABLED=false

## Audit
CLEAN — no fake/no-op publish; ETag concurrency present.
