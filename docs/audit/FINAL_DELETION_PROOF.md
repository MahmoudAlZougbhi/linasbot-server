# FINAL_DELETION_PROOF.md

**Agent:** Phase R (docs)  
**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**FINAL_APPLICATION_CANDIDATE_SHA:** `72d1d439b589f4d111b0a4cc7cd61030ceaca677`  
**FINAL_FREEZE_DOCS_SHA:** `__PENDING_FREEZE_DOCS_SHA__`  
**Rule:** Summarize only deletes/archives/disables that landed in git. Link caller-proof docs under `docs/audit/deletions/` where present. Do not invent removals.

---

## Index of proof docs

| Proof | Path |
|---|---|
| Wave / orphan deletes (dashboard pages) | [`deletions/DELETE_PROVEN_disabled_dashboard_pages.md`](deletions/DELETE_PROVEN_disabled_dashboard_pages.md) |
| Analytics page | [`deletions/DELETE_PROVEN_Analytics_page.md`](deletions/DELETE_PROVEN_Analytics_page.md) |
| Creative Studio mobile screen | [`deletions/DELETE_PROVEN_CreativeStudioScreen.md`](deletions/DELETE_PROVEN_CreativeStudioScreen.md) |
| Creative Python stack (not deleted) | [`deletions/BLOCKED_creative_cancelled_stack.md`](deletions/BLOCKED_creative_cancelled_stack.md) |
| `live_chat_archive/` | [`deletions/DELETE_PROVEN_live_chat_archive.md`](deletions/DELETE_PROVEN_live_chat_archive.md) |
| `cleanup_reports/` | [`deletions/DELETE_PROVEN_cleanup_reports.md`](deletions/DELETE_PROVEN_cleanup_reports.md) |
| Third-provider adapter orphan | [`deletions/DELETE_PROVEN_third_provider_adapter.md`](deletions/DELETE_PROVEN_third_provider_adapter.md) |
| Runtime logs / tmp probes | [`deletions/DELETE_PROVEN_runtime_logs_and_tmp.md`](deletions/DELETE_PROVEN_runtime_logs_and_tmp.md) |
| Content-files / instructions **410** | [`deletions/DISABLED_PROVEN_content_files_instructions.md`](deletions/DISABLED_PROVEN_content_files_instructions.md) |
| `delete_all_conversations` archive | [`deletions/DELETE_PROVEN_delete_all_conversations.md`](deletions/DELETE_PROVEN_delete_all_conversations.md) |
| B2 archive batch (`6ea0a81`) | [`deletions/ARCHIVE_PROVEN_b2_docs_scripts_binaries.md`](deletions/ARCHIVE_PROVEN_b2_docs_scripts_binaries.md) |
| Bot chat MD / misc | [`deletions/DELETE_PROVEN_bot_chat_md.md`](deletions/DELETE_PROVEN_bot_chat_md.md) |

---

## 1. Wave 1 deletes (orphans / dead surfaces)

**Theme commits:** `3c3bf72` … `81319fe` (`chore(wave1): …`).

| Batch | Commit | What left the tree |
|---|---|---|
| TrainingFileEditor cluster | `3c3bf72` | Orphan dashboard training editor UI |
| Instruction/content panels | `ff4918f` | Orphan dashboard panels |
| Landing mascot / brand constant | `9539214` | Unwired landing assets |
| `usePermissions` hook | `dfa98d4` | Orphan hook |
| GuestBanner / HistoryDrawer | `2467dfb` | Unused mobile chrome |
| Mobile create-post orphan cluster | `95b98f6` | Unwired create-post UI |
| ControlCenterDrawer | `fdee7cb` | Unused drawer |
| LiveChatComposer | `afe0332` | Unused composer |
| live-chat-android WebView app | `ae1f84c` | Superseded tracked sources |
| Dead services batch A | `33eb644` | Unused services |
| `live_monitoring` | `16aed24` | Unused service |
| `message_queue` / `message_sync` | `6555463` | Unused services |
| Diagnostic / simulation scripts | `81319fe` | Orphan scripts |

**Related deletion proofs (later waves, same cleanup branch):**

- Disabled unmounted SPA pages → [`DELETE_PROVEN_disabled_dashboard_pages.md`](deletions/DELETE_PROVEN_disabled_dashboard_pages.md)  
- Analytics page → [`DELETE_PROVEN_Analytics_page.md`](deletions/DELETE_PROVEN_Analytics_page.md)  
- CreativeStudioScreen → [`DELETE_PROVEN_CreativeStudioScreen.md`](deletions/DELETE_PROVEN_CreativeStudioScreen.md)  
- `third_provider_adapter.py` → [`DELETE_PROVEN_third_provider_adapter.md`](deletions/DELETE_PROVEN_third_provider_adapter.md)  
- `live_chat_archive/` / `cleanup_reports/` → W09 proofs above  

Caller proof for Wave 1 orphans is the Phase 1 reinspect “FIXED_CLEAN” list in `PHASE1_REINSPECT_REPORT.md` (no remaining imports of deleted units).

---

## 2. Content-files / instructions APIs → 410 Gone

**Commit:** `648bc02` — `fix(security): disable legacy content-files and instructions APIs`  
**Proof:** [`DISABLED_PROVEN_content_files_instructions.md`](deletions/DISABLED_PROVEN_content_files_instructions.md)

| Surface | Disposition |
|---|---|
| `/api/content-files/*`, `/api/retrieval-debug/logs` | Handlers return **410** `CONTENT_FILES_API_GONE` |
| `/api/instructions/*` | Handlers return **410** `INSTRUCTIONS_API_GONE` |
| `services/content_files_service.py` | **Kept** (retrieval/greeting runtime) |
| Dashboard hooks | Dead `getContentFiles*` / `getInstructions*` removed; CM `/api/cm/...` remains SoT |

Not a file delete — intentional fail-closed disable with routes still registered.

---

## 3. `delete_all_conversations` → harden + archive

**Commits:** `3e22e82` (harden) → `88f0d81` (archive)  
**Proof:** [`DELETE_PROVEN_delete_all_conversations.md`](deletions/DELETE_PROVEN_delete_all_conversations.md)  
**SEC:** SEC-017 FIXED in `FINAL_SECURITY_FINDINGS.md`

| Item | Detail |
|---|---|
| Former path | `scripts/delete_all_conversations.py` |
| New path | `archive/scripts/delete_all_conversations.py` |
| Callers | None in HTTP/runtime/workflows; unit guards only |
| Default | Dry-run; execute requires typed phrase + env gate |

**Do not run against production.**

---

## 4. APK / jsonl untrack

**Commits:**

- `a924227` — removed tracked `data/*.jsonl`, `logs/content_violations.jsonl`, `mobile/releases/linas-live-chat-android.apk` from the index (infra/repo sync batch).
- `9b9cb62` — `.gitignore`: `data/*.jsonl`, `logs/content_violations.jsonl`, `*.apk`, `mobile/releases/*.apk`.

**Proof companion:** [`DELETE_PROVEN_runtime_logs_and_tmp.md`](deletions/DELETE_PROVEN_runtime_logs_and_tmp.md) (earlier `logs/*.out` / `.tmp_8010_*.json`).

Files may remain on disk under `LINASBOT_DATA_ROOT` / local cwd; they are no longer git seeds.

---

## 5. Archive batch `6ea0a81`

**Commit:** `6ea0a81` — `chore(archive): move B2 docs, probe scripts, and design binaries`  
**Proof:** [`ARCHIVE_PROVEN_b2_docs_scripts_binaries.md`](deletions/ARCHIVE_PROVEN_b2_docs_scripts_binaries.md)

Moved to `archive/<same relative path>`:

- Probe/manual scripts (appointment probe, montymobile_manual_probe, line_count_gate, etc.)
- Safe-subset Phase 2 / Meta / WA evidence docs
- Design PDF/screenshot trees under `docs/design/*` and `docs/evidence/*` (not brand icons)

Live callers (CM control-plane plans, capability_manifest, workflow-bound scripts, landing brand) were **not** moved.

---

## 6. `montymobile_templates.json` deleted

**Commit:** `70e2105` — `fix(whatsapp): Meta Cloud-only transport; remove Monty/Qiscus/360 runtime fallback`

| Former | Replacement |
|---|---|
| `config/montymobile_templates.json` (**deleted**) | `config/whatsapp_cloud_templates.json` |
| Factory runtime fallback to Monty/Qiscus/360 | Meta Cloud-only factory + tests (`tests/test_whatsapp_factory_cloud_only.py`) |

Live Meta secret cutover remains **LIVE_ACTIVATION_PENDING** (SEC-026) — see `FINAL_EXTERNAL_ACTIVATION_CHECKLIST.md` A1. Template file deletion is repo-complete.

---

## 7. Operator SPA routes redirected (landing-only web)

**Commit:** `20a8eb2` — `feat(web): landing-only dashboard; operator UX deferred to mobile`  
**Parity precondition:** `FINAL_WEB_TO_MOBILE_PARITY_MATRIX.csv` (`6fa5b68`)

`dashboard/src/App.jsx` keeps marketing + thin auth + `/mobile/live-chat` APK bridge. Former operator paths redirect to `/#get-app` (or `UseMobileAppPage`), including:

`/app`, `/training`, `/content-managers/*`, `/activity-flow`, `/live-chat`, `/analytics`, `/smart-messaging`, `/social-posts`, `/wallet`, `/settings`, `/testing`, `/api-debug`, `/register`, catch-all `/*`.

Page modules may still exist in the tree for a later delete pass; **routing no longer mounts the operator shell**. Earlier product-disable deletes for unmounted pages remain documented in [`DELETE_PROVEN_disabled_dashboard_pages.md`](deletions/DELETE_PROVEN_disabled_dashboard_pages.md).

---

## Summary table

| Action | Mechanism | Evidence |
|---|---|---|
| Wave 1 orphans | `git rm` | Wave1 commits + Phase 1 reinspect |
| Content/instructions HTTP | 410 disable | `648bc02` + DISABLED_PROVEN |
| Destructive CLI | Harden + `git mv` → archive | `3e22e82` / `88f0d81` + DELETE_PROVEN |
| jsonl + APK | Untrack + gitignore | `a924227` / `9b9cb62` |
| B2 docs/scripts/binaries | `git mv` → archive | `6ea0a81` + ARCHIVE_PROVEN |
| Monty templates | Delete + Cloud templates | `70e2105` |
| Operator SPA | Redirect / landing-only | `20a8eb2` |
| Creative Python stack | **Not deleted** (BLOCKED) | BLOCKED_creative_cancelled_stack.md |
