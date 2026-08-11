# BLOCKED: Creative cancelled Python stack (W12/partial)

**Status:** BLOCKED — not deleted  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg

Candidates reviewed for “zero product use” deletion. Each remains referenced by runtime, tests, and/or CI.

| Unit | Blocker evidence |
|---|---|
| `modules/creative_api.py` | `main.py` import; `tests/test_endpoint_auth_matrix.py` `_ROUTE_MODULES`; `modules/api_security.py` allows `/api/creative/` for non-linas tenants |
| `services/creative_studio_service.py` | Imported by `creative_api` and `owner_ai_tools_creative` |
| `services/owner_ai_tools_creative.py` | Imported + registered in `services/owner_ai_tools.py` TOOL_HANDLERS; dormant path exercised by `tests/test_owner_ai_create_post_chat.py` when `OWNER_COPILOT_V2=false` |
| `services/owner_copilot_v2/creative_policy.py` | Used by `brain.py` + `tool_dispatch.py`; imported by `tests/test_owner_copilot_v2.py`; listed in `capability_manifest.json` `source_files`; required for cancelled refusals |
| Registry / manifest | `scripts/check_copilot_v2_manifest.py` requires `creative_studio` unavailable in manifest and cancelled wording in `system_knowledge_registry.py` — **must keep** |

Mobile screen deleted separately as `DELETE_PROVEN_CreativeStudioScreen.md` (unwired).
