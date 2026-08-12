# ARCHIVE_PROVEN: B2 docs/scripts + design binaries

**Status:** MOVED to `archive/` with caller proof  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg  
**Agent:** B2

## Batch

- Scripts (7): appointment_api_manual_probe, audit/line_count_gate, check_message_flow, check_provider_status, montymobile_manual_probe, meta_webhook_contract, wa_app_review_temp_bind
- Docs/evidence (~23 files): PHASE2 reports (safe subset), LIVE_CHAT_FIX_SUMMARY, META_VERIFIED cutover runbook, WA coexistence, design handoff.txt, customer_reply/system_copilot evidence (not capability_manifest), dashboard/README.md
- Binary design evidence dirs: docs/design/pdf_pages, docs/design/landing, docs/evidence/mobile_design_handoff/screenshots, docs/evidence/public-landing, plus design PDF

## Stopped / not moved (live callers)

- CM control-plane plan docs (`tests/test_cm_control_plane_plan_loc_split.py`)
- MAHMOUD_MOBILE_PROMPT* (`tests/test_mahmoud_mobile_prompt_loc_split.py`)
- `docs/evidence/system_copilot_v2/capability_manifest.json` (quality-gates + check_copilot_v2_manifest)
- Workflow-bound prod_cm_* / prod_apply_* / audit_meta_app_a_scopes / scan_* / run_queue_worker / manage_meta_page_subscription
- `PHASE2_PRE_RELEASE_REPORT` (platform_api), `PHASE2_PRODUCTION_RECONCILE` (deploy unit)
- `dashboard/public/brand` + mobile icons (LANDING/MOBILE KEEP)

## Action

`git mv` originals → `archive/<same relative path>`
