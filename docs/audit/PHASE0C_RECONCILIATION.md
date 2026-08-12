# Phase 0C — Audit Integrity Reconciliation

**Owner:** Mahmoud  
**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**Mode:** AUDIT-ONLY (no application source changes)

## 1. Baseline freeze (dual accounting)

| Metric | Value |
|---|---|
| Original pre–Phase 0A baseline SHA | `d4f16c5537fe08f6eab927dbab2c62d0e670697f` (parent of first Phase 0A commit `82152df`) |
| First Phase 0A audit commit | `82152df` |
| Tracked files at baseline SHA (`git ls-files`) | **1544** |
| App-only at baseline (excl. `docs/audit/**`) | **1522** |
| Current tracked files at HEAD (incl. audit docs) | **1544** |
| App-only current | **1522** |
| `FILE_INVENTORY.csv` rows | **1544** |

### Policy (explicit)

- **Inventory rows = current `git ls-files` including `docs/audit/**` artifacts.**
- Application baseline for “did Phase 0 change product code?” uses **app-only** counts and `git diff` excluding `docs/audit/**`.
- `PHASE0A_BASELINE.md` historically claimed **1539**; live `git ls-files` at Phase 0A birth and now is **1544**. Phase 0C treats **1544** as the frozen tracked truth and documents the 1539 figure as a superseded recount error (not a silent app baseline inflation).

## 2. Ranges re-run / validated

| Range | Action | Result |
|---|---|---|
| 521–800 | Full open+read (lead pass + subagents) | Forensic fields rewritten; COMPLETE |
| 801–1100 | Full open+read + JSON reconcile | Forensic fields rewritten; seq 801 elevated |
| 206–520 | Thin-evidence gaps re-read (95) | Purposes/callers repaired |
| 1101–1539 | Validate agent JSON evidence; re-read 5 thin rows | MERGE / FP documented |

### Files fully re-reviewed in Phase 0C

- **675** lead-pass targets (95 thin ∈ 206–520 + 580 ∈ 521–1100)
- **+5** thin service rows in 1101–1539 (1175, 1176, 1302, 1303, 1319)
- **Critical manual verifies:** `modules/live_chat_api_debug.py`, `scripts/delete_all_conversations.py`, `modules/api_security.py`, `modules/core.py`, `modules/wallet_api.py`, `services/auth_rate_limits.py`, `services/rate_limit_service.py`, `services/media_service.py`, `services/cm/shadow_eval.py`

## 3. Seq 801 — `modules/live_chat_api_debug.py`

| Question | Answer |
|---|---|
| Registered in production? | **Yes** — `main.py` imports `modules.live_chat_api`, which side-effect imports `live_chat_api_debug` |
| Public / unauthenticated? | **No** — not in `_PUBLIC_EXACT` / `_PUBLIC_PREFIX` |
| Auth required? | **Yes** — `DashboardAuthMiddleware` requires session |
| Permission? | **`liveChat`** via `required_permission_for` for `/api/live-chat*` |
| Tenant gate? | Non-`linas` sessions get 403 on `/api/live-chat*` |
| Handler-level elevation? | **No** — no admin/ops role check on debug/rebuild |
| Exposes metadata? | **Yes** — `GET /api/live-chat/debug-firestore` dumps all users’ conversation metadata (ids, counts, status, human_takeover, index `last_message_text`) |
| Rebuild reachable? | **Yes** — `POST /api/live-chat/rebuild-index` any `liveChat` operator |
| Disposition | **`KEEP_SECURITY_FIX` (HIGH)** — authenticated but insufficiently authorized |

## 4. Seq 870 — `scripts/delete_all_conversations.py`

| Topic | Finding |
|---|---|
| How invoked | `python scripts/delete_all_conversations.py --dry-run` or `--confirm` |
| Who can invoke | Anyone with shell + working Firestore creds (`get_firestore_db` / `data/firebase_data.json`) |
| Prod credentials | Firebase service account JSON path used by app; no separate script auth |
| Confirmation | `--confirm` flag only (no typed phrase / ticket id) |
| Auditability | stdout only; no structured audit log |
| Repo placement | **MOVE_TO_ARCHIVE** / protected-ops — official security finding retained; **not deleted** this phase |

## 5. Untracked agent JSON reconciliation

| File | SHA-256 | Size | Disposition |
|---|---|---:|---|
| `docs/audit/_phase0b_batch_801_1100.json` | `0fc143230c575fe9cf974c506405e1f42bcb4d28ccd83ba4db018f9c18a51258` | 370362 | Findings merged into inventory / SECURITY_FINDINGS; **not committed** (evidence hash retained here) |
| `docs/audit/_phase0b_batch_1101_1539_final.json` | `c23f641eb2abd662129a1392960a491193c05b6f93627b7f2a8b757e323157bc` | 449735 | Validated; thin rows rewritten; **not committed** |
| `docs/audit/_phase0c_lead_pass_partial.json` | `f1feafa44fa15455e705ca2216a2e5271fce2e0d59eeb7fc7ae91f427d72b0c4` | 766752 | Working merge input; **not committed** |

Actions used: **MERGE** (most), **FALSE_POSITIVE** (`shadow_eval` eval claim), **BLOCKED** (none).

## 6. Official security totals

See `docs/audit/SECURITY_FINDINGS.md`.

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 18 |
| MEDIUM | 33 |
| LOW | 4 |
| INFO | 14 |
| **TOTAL** | **69** |

Inventory `KEEP_SECURITY_FIX` rows: **16** (includes seq 801).  
Official finding count **69** includes converted “extra security notes” + seq 870 ops finding.

## 7. Known concerns (9/9)

See `docs/audit/KNOWN_SECURITY_CONCERNS.md`.

| Concern | Status |
|---|---|
| Mobile login/refresh rate limiting | ALREADY_FIXED |
| Trusted proxy / client-IP | ALREADY_FIXED |
| Wallet admin-credit authz | ALREADY_FIXED |
| Production CORS | ALREADY_FIXED |
| Tenant assertions on shared handlers | CONFIRMED_FIX_REQUIRED |
| Role/permission elevation | CONFIRMED_FIX_REQUIRED |
| CSRF + constant-time compare | ALREADY_FIXED |
| Filename/path sanitization | ALREADY_FIXED |
| Distributed production rate limiting | CONFIRMED_FIX_REQUIRED |

## 8. Over-500 matrix

See `docs/audit/OVER_500_FILES.md`.

- **Exact hand-written application files >500 LOC:** **0**
- Why prior dispositions had zero `KEEP_SPLIT`: LOC gate already enforced splits before Phase 0B; stale `FILES_OVER_500.csv` was pre-split.

## 9. Machine checks (all PASS)

```
PASS inventory_row_count_vs_current_ls_files — inventory=1544 current_ls_files=1544
PASS baseline_app_unchanged_count — app-only baseline=1522 current=1522
PASS complete_implies_fully_read — bad=0
PASS no_unreviewed_or_in_review — COMPLETE=1544
PASS no_duplicate_seq
PASS contiguous_seq_1_to_n — 1..1544
PASS no_duplicate_paths
PASS blocked_have_reason — blocked_count=0
PASS findings_link_inventory_paths — findings=69 missing=[]
PASS over_500_matrix_covers_all — current_hw_over_500=[]
PASS no_keep_as_is_over_500_without_exception — N/A
PASS no_app_diff_baseline_to_head — empty diff excluding docs/audit/**
```

Raw JSON: `docs/audit/_phase0c_machine_checks.json` (optional working file; may remain untracked).

## 10. Proof — no application source changed

```bash
git diff --name-status d4f16c55..HEAD -- . ':(exclude)docs/audit/**'
# → empty
```

App-only tracked count unchanged: **1522 → 1522**.  
Phase 0C commits touch **only** `docs/audit/**`.

## 11. Reclassified rows (Phase 0C highlights)

| Seq | Path | From | To |
|---:|---|---|---|
| 801 | `modules/live_chat_api_debug.py` | KEEP_AS_IS | KEEP_SECURITY_FIX |
| 818–845 (selected) | webhook/smart-messaging/settings modules | KEEP_AS_IS | KEEP_FIX |
| 980 | `services/chat_response_runtime_tool_create_name.py` | KEEP_AS_IS | KEEP_FIX |
| 865–878,930 (selected) | orphan scripts | MOVE_TO_ARCHIVE | DELETE_CANDIDATE |
| 875 | `scripts/montymobile_manual_probe.py` | DELETE_CANDIDATE | MOVE_TO_ARCHIVE |
| 1099 | `services/gender_detection.py` | KEEP_AS_IS | DELETE_CANDIDATE |
| workflow-linked `scripts/prod_*` | various | MOVE_TO_ARCHIVE (0B) | KEEP_AS_IS (active CI) |

Full machine list snapshot: `docs/audit/_phase0c_reclassified.json` (working; hash in git status if untracked).

## 12. False positives / blocked

| Item | Status |
|---|---|
| `services/cm/shadow_eval.py` “eval() present” | **FALSE_POSITIVE** |
| Blocked inventory rows | **0** |
| Seq 870 JSON `KEEP_SECURITY_FIX` vs archive | **RESOLVED** by lead: disposition `MOVE_TO_ARCHIVE` + official SEC finding (not inventory BLOCKED) |
| `services/retrieval_debug.py` eval claim | **FALSE_POSITIVE** |

## 13. Official problem counts (post–Phase 0C)

| Class | Count |
|---|---:|
| KEEP_SECURITY_FIX (inventory) | 17 |
| Official SEC findings (all severities) | 69 |
| KEEP_FIX (correctness/product) | 100 |
| KEEP_PERFORMANCE_FIX | 3 |
| DELETE_CANDIDATE | 46 |
| MOVE_TO_ARCHIVE | 100 |
| KEEP_SPLIT | 0 |
| Hand-written >500 LOC | 0 |

## 14. STOP

Phase 0C complete for owner approval. **Do not begin Phase 1.**

## 15. Follow-up elevation merge (same Phase 0C)

After late W0C-B* completions, lead merged **35** remaining disposition elevations into `FILE_INVENTORY.csv` (notably seq 535 KEEP_SECURITY_FIX). App source still untouched.

Post-follow-up totals: KEEP_SECURITY_FIX=17, KEEP_FIX=100, DELETE_CANDIDATE=46, KEEP_AS_IS=1145.
