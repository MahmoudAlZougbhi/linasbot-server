# SECURITY_FINDINGS.md — Phase 0C Official Security Findings

**Scope:** Audit-only Phase 0C W0C-E lead helper. Application source was not modified.

**Sources merged into this official register:**
1. All current `KEEP_SECURITY_FIX` rows from `docs/audit/FILE_INVENTORY.csv` (**16**, including seq 801)
2. All items under `## Other substantive security notes` in `docs/audit/ALL_PROBLEMS_FOUND.md` (**52**)
3. Confirmed Phase 0C finding for `modules/live_chat_api_debug.py` (seq 801) — folded into inventory KEEP_SECURITY_FIX row with Phase 0C confirmation evidence (not double-counted)
4. `scripts/delete_all_conversations.py` (seq 870) — destructive CLI ops finding (disposition may be `MOVE_TO_ARCHIVE` but **MUST** appear here)

**Official total:** 69 findings (= 16 inventory KEEP_SECURITY_FIX + 1 Phase 0C seq 870 + 52 substantive notes).

**Status:** All findings listed here are **OPEN**.

---

## Severity summary

| Severity | Count |
|----------|------:|
| CRITICAL | 2 |
| HIGH | 15 |
| MEDIUM | 18 |
| LOW | 16 |
| INFO | 19 |
| **TOTAL** | **70** |

### Source breakdown

| Source | Count |
|--------|------:|
| KEEP_SECURITY_FIX inventory (incl. Phase 0C seq 801) | 16 |
| Phase 0C confirmed (seq 870) | 1 |
| Other substantive security notes | 52 |

---

## Findings

### SEC-001 — HIGH

- **Inventory seq:** 6
- **File:** `.github/workflows/dashboard-auth-secret-apply.yml`
- **Symbol / route:** workflow_dispatch secret apply (no confirmation string)
- **Exploit / failure scenario:** Anyone with Actions write can rotate DASHBOARD_AUTH_SECRET without typed confirmation.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: NO confirmation input unlike sibling secret-apply workflows — anyone with Actions write on repo can rotate dashboard auth. Secret passed via envs to SSH (expected). | disposition_evidence: Missing confirmation string gate on high-impact secret apply
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Add confirmation-string gate; workflow dry-run assert fails without confirmation.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-002 — HIGH

- **Inventory seq:** 7
- **File:** `.github/workflows/deploy.yml`
- **Symbol / route:** workflow_run / workflow_dispatch production deploy
- **Exploit / failure scenario:** Emergency bypass skips Quality Gates; ssh-action@v1.0.3 version skew; data/ copied to world-readable /tmp during reset.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Emergency bypass skips gate verification (documented). Uses appleboy/ssh-action@v1.0.3 while siblings use v1.2.0 (supply-chain version skew). data/ backup to /tmp/linasbot_data_backup_$$ then restore after hard reset — /tmp world-readable risk window if perms loose. | disposition_evidence: Pin/update ssh-action version consistency; harden data backup path permissions; keep confirmation for emergency
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Workflow review checklist: pin ssh-action; assert backup dir permissions; keep emergency confirmation.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-003 — HIGH

- **Inventory seq:** 8
- **File:** `.github/workflows/instagram-login-secrets-apply.yml`
- **Symbol / route:** workflow_dispatch Instagram Login secrets apply
- **Exploit / failure scenario:** Actions write can apply Instagram app secret + webhook verify token without typed confirmation.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: No typed confirmation; secrets via SSH envs; never logs values (stated) | disposition_evidence: Secret apply without confirmation string
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Add confirmation-string gate like sibling workflows.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-004 — HIGH

- **Inventory seq:** 21
- **File:** `.github/workflows/meta-webhook-nginx-setup.yml`
- **Symbol / route:** workflow_dispatch Meta webhook nginx/token setup
- **Exploit / failure scenario:** Rotates META_WEBHOOK_VERIFY_TOKEN without typed confirmation — webhook auth impact.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: No confirmation string; rotates verify token — webhook auth impact | disposition_evidence: Verify-token apply without typed confirmation
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Add confirmation-string gate; assert non-empty token still required.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-005 — HIGH

- **Inventory seq:** 23
- **File:** `.github/workflows/openai-api-key-apply.yml`
- **Symbol / route:** workflow_dispatch OPENAI_API_KEY apply
- **Exploit / failure scenario:** Billing-critical OpenAI key can be rotated without typed confirmation.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: No confirmation; applies billing-critical API key | disposition_evidence: OpenAI key apply without typed confirmation
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Add confirmation-string gate; retain post-apply verify script.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-006 — HIGH

- **Inventory seq:** 27
- **File:** `.github/workflows/subscription-exempt-probe.yml`
- **Symbol / route:** workflow_dispatch subscription-exempt-probe
- **Exploit / failure scenario:** CI logs print entitlement env values, linas.json entitlement raw[:400], and all dashboard_users tenant/role/display rows; unbounded Firestore stream.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Prints SUBSCRIPTION_EXEMPT_TENANT_IDS value, TOKEN_WALLET_UNLIMITED value, linas.json entitlement raw[:400], and per-user tenant/role/status/display names into Actions logs (no emails but business display names + tenant map). Firestore stream of all dashboard_users unbounded. | disposition_evidence: Logs entitlement raw + tenant env values + all user display rows to CI logs
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Assert redaction of env/raw entitlement; bound Firestore reads; no display-name dump in logs.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-007 — MEDIUM

- **Inventory seq:** 30
- **File:** `.github/workflows/whatsapp-cloud-phase1-apply.yml`
- **Symbol / route:** workflow_dispatch WhatsApp Cloud Phase1 apply
- **Exploit / failure scenario:** Confirmation-gated but runs git reset --hard origin/main on /opt/linasbot — can discard server-local state.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Confirmation-gated but runs git reset --hard origin/main on /opt/linasbot before ops — can discard server-local uncommitted state | disposition_evidence: Production git reset --hard inside workflow
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Document intentional sync or remove hard reset; regression: confirmation still required.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-008 — HIGH

- **Inventory seq:** 95
- **File:** `dashboard/src/App.jsx`
- **Symbol / route:** ProtectedRoute /mobile/live-chat (App.jsx)
- **Exploit / failure scenario:** Authenticated user without liveChat permission can open /mobile/live-chat if URL known; tests expect requiredPermission but App omits it.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: /mobile/live-chat ProtectedRoute WITHOUT requiredPermission=liveChat (tests cover with permission but App omits). Client-side guards only. | disposition_evidence: Mobile live-chat route missing requiredPermission
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** App.routes / MobileLiveChat.auth.test: route requires requiredPermission="liveChat".
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-009 — HIGH

- **Inventory seq:** 126
- **File:** `dashboard/src/components/UserManagement/RoleManager.jsx`
- **Symbol / route:** RoleManager / permissions.jsx CUSTOM_ROLES_KEY
- **Exploit / failure scenario:** Custom roles in localStorage only — cross-admin/device authz inconsistency; custom roleId on server may not resolve elsewhere.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Custom roles persisted only in browser localStorage (dashboard/src/utils/permissions.jsx CUSTOM_ROLES_KEY) — not shared across admins/devices; assigning custom roleId to server users may not resolve on other browsers | disposition_evidence: Active in UserManagement; custom roles in localStorage create cross-admin authorization inconsistency
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Document client-only limitation or server-backed roles; test custom role not trusted server-side alone.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-010 — CRITICAL

- **Inventory seq:** 152
- **File:** `dashboard/src/contexts/AuthContext.helpers.js`
- **Symbol / route:** buildUserData (AuthContext.helpers.js)
- **Exploit / failure scenario:** If backend omits role/tenantId, client elevates to role=admin and tenantId=linas — privilege/tenant spoof.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: buildUserData defaults role to admin and tenantId to linas when missing — privilege/tenant spoof risk if backend omits fields | disposition_evidence: Default role=admin and tenantId=linas in buildUserData when fields absent | agent also flags admin/tenantId defaults as correctness risk
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Unit test: missing role/tenantId must not default to admin/linas.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-011 — HIGH

- **Inventory seq:** 153
- **File:** `dashboard/src/contexts/AuthContext.jsx`
- **Symbol / route:** AuthProvider session restore (AuthContext.jsx)
- **Exploit / failure scenario:** Fail-open keeps cached auth_session on transient session errors; console.log of auth payloads; CSRF in localStorage.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Fail-open: keeps cached auth_session on transient session errors and catch; console.log of login/session response shapes; CSRF stored in localStorage | disposition_evidence: Session fail-open on errors + debug console.log of auth payloads; active AuthProvider
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Explicit fail-open vs fail-closed policy test; no auth payload console.log in production builds.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-012 — MEDIUM

- **Inventory seq:** 168
- **File:** `dashboard/src/hooks/useLiveChatMediaComposer.jsx`
- **Symbol / route:** useLiveChatMediaComposer sendVoiceMessage/sendImageMessage
- **Exploit / failure scenario:** Hardcodes operatorId operator_001 — wrong attribution / authz risk on media sends.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Hardcodes operatorId "operator_001" for voice/image sends — wrong attribution / authz risk | disposition_evidence: operator_001 hardcoded in sendVoiceMessage and sendImageMessage | hardcoded operator_001; agent KEEP_FIX — elevated as attribution/authz risk
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Assert media sends use authenticated operator id from auth user.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-013 — HIGH

- **Inventory seq:** 192
- **File:** `dashboard/src/pages/LiveChatSidebar.jsx`
- **Symbol / route:** LiveChatSidebar rebuild + simulateWebhook controls
- **Exploit / failure scenario:** Any liveChat operator sees Rebuild index and Test flow (simulateWebhook 9613000000) — high-impact ops without elevated gate.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: UI exposes Rebuild index and Test flow (simulateWebhook phone 9613000000) to any liveChat user — high-impact ops without elevated gate | disposition_evidence: simulateWebhook and rebuildLiveChatIndex buttons visible in operator sidebar
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** UI/API gate: rebuild-index and simulate-webhook require admin (or elevated) permission.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-014 — HIGH

- **Inventory seq:** 197
- **File:** `dashboard/src/pages/MobileLiveChat.jsx`
- **Symbol / route:** MobileLiveChat route wrapper /mobile/live-chat
- **Exploit / failure scenario:** Same permission gap as App.jsx — route reachable without liveChat if URL known.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: route permission gap tracked on App.jsx | Route may be reachable without liveChat permission if URL known; Sidebar gates nav but route does not | disposition_evidence: Active mobile route wrapper | App.jsx ProtectedRoute for /mobile/live-chat omits requiredPermission=liveChat (agent + prior App audit)
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** ProtectedRoute on /mobile/live-chat requires liveChat (covered via App test).
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-015 — HIGH

- **Inventory seq:** 203
- **File:** `dashboard/src/pages/Settings.jsx`
- **Symbol / route:** Settings.jsx tenant gate (user?.tenantId || "linas")
- **Exploit / failure scenario:** Missing tenantId defaults to linas, unlocking general/notifications ops tabs.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: (user?.tenantId || "linas") === "linas" unlocks general/notifications when tenantId missing — same default-tenant risk | disposition_evidence: Missing tenantId defaults to linas enabling ops settings tabs | Missing tenantId defaults to linas enabling ops settings tabs | also loads unused botName/enableVoice/humanTakeoverNotifyMobiles (agent KEEP_FIX debt)
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** non-linas / missing-tenantId tab gating test must not unlock linas-only settings.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory

### SEC-016 — HIGH

- **Inventory seq:** 801
- **File:** `modules/live_chat_api_debug.py`
- **Symbol / route:** GET /api/live-chat/debug-firestore; GET /api/live-chat/status; POST /api/live-chat/rebuild-index (main→live_chat_api→live_chat_api_debug)
- **Exploit / failure scenario:** Authenticated liveChat operator (not necessarily admin) can GET debug-firestore (dumps all conversation metadata) and POST rebuild-index. Middleware requires auth+liveChat — NOT unauthenticated — but elevation is insufficient.
- **Evidence:** FILE_INVENTORY.csv disposition KEEP_SECURITY_FIX. security_findings: Routes registered in production via main→modules.live_chat_api→import live_chat_api_debug. NOT public: DashboardAuthMiddleware requires authenticated session + liveChat permission for /api/live-chat*. Non-linas tenants blocked from /api/live-chat*. Handler itself has no Depends/role check. GET /api/live-chat/debug-firestore streams all users' conversation metadata (ids, message_count, status, human_takeover, index last_message_text). GET /api/live-chat/status exposes index/users counts. POST /api/live-chat/rebuild-index triggers live_chat_service.rebuild_index_from_firestore (ops-level). Any liveChat operator can invoke — insufficient elevation → KEEP_SECURITY_FIX HIGH. | disposition_evidence: Authenticated+liveChat via middleware; insufficient authz for debug dump/rebuild; exposes Firestore conversation metadata | Phase 0C W0C confirmation: middleware requires auth+liveChat (NOT unauthenticated); insufficient elevation — any liveChat operator can dump metadata / rebuild index. Registered via main→live_chat_api→live_chat_api_debug. Severity HIGH.
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Auth matrix: anonymous 401; after fix only elevated role succeeds for debug-firestore/rebuild-index; non-liveChat 403.
- **Status:** OPEN
- **Source bucket:** KEEP_SECURITY_FIX inventory + Phase 0C confirmed (seq 801)

### SEC-017 — CRITICAL

- **Inventory seq:** 870
- **File:** `scripts/delete_all_conversations.py`
- **Symbol / route:** main / run_delete (--dry-run | --confirm)
- **Exploit / failure scenario:** Anyone with shell access and working Firebase creds (data/firebase_data.json / get_firestore_db) runs --confirm and deletes ALL conversations + live_chat_index under artifacts/linas-ai-bot-backend. No RBAC, no typed phrase beyond --confirm, no structured audit log.
- **Evidence:** Phase 0C confirmed destructive CLI ops finding. Guard is --dry-run/--confirm only; zero workflow callers; inventory disposition MOVE_TO_ARCHIVE — MUST appear as official security finding.
- **Disposition:** `MOVE_TO_ARCHIVE`
- **Required test:** Do not run against prod. Static: assert script requires --confirm for delete; no CI references; archive under protected ops.
- **Status:** OPEN
- **Source bucket:** Phase 0C confirmed (seq 870)

### SEC-018 — LOW

- **Inventory seq:** 3
- **File:** `.github/workflows/cm-linas-content-audit.yml`
- **Symbol / route:** seq 3 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Uses SSH secrets; masks phones to last4; avoids FAQ/customer bodies. Loads prod .env via setdefault (does not override existing env). Risk: Actions actors with workflow run + secrets can read CM structure summaries.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 3 [KEEP_AS_IS]: Uses SSH secrets; masks phones to last4; avoids FAQ/customer bodies. Loads prod .env via setdefault (does not override existing env). Risk: Actions actors with workflow run + secrets can read CM structure summaries.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-019 — LOW

- **Inventory seq:** 4
- **File:** `.github/workflows/cm-production-cutover.yml`
- **Symbol / route:** seq 4 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** High-impact prod mutations; mitigated by confirmation string + concurrency group. generic_tenant_proof fetches origin/main script mid-run.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 4 [KEEP_AS_IS]: High-impact prod mutations; mitigated by confirmation string + concurrency group. generic_tenant_proof fetches origin/main script mid-run.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-020 — LOW

- **Inventory seq:** 9
- **File:** `.github/workflows/meta-app-a-login-config-apply.yml`
- **Symbol / route:** seq 9 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Uses GH environment protection; fails if secret empty; hardcoded redirect https://www.linasaibot.com/oauth/meta/callback
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 9 [KEEP_AS_IS]: Uses GH environment protection; fails if secret empty; hardcoded redirect https://www.linasaibot.com/oauth/meta/callback
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-021 — LOW

- **Inventory seq:** 14
- **File:** `.github/workflows/meta-multi-app-secrets-apply.yml`
- **Symbol / route:** seq 14 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Large secret surface (App A/B + encryption key) over SSH envs; advanced access hardcoded false
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 14 [KEEP_AS_IS]: Large secret surface (App A/B + encryption key) over SSH envs; advanced access hardcoded false
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-022 — LOW

- **Inventory seq:** 16
- **File:** `.github/workflows/meta-social-atomic-cutover.yml`
- **Symbol / route:** seq 16 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Highest-impact Meta cutover; confirmation + environment; rollback encryption key required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 16 [KEEP_AS_IS]: Highest-impact Meta cutover; confirmation + environment; rollback encryption key required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-023 — LOW

- **Inventory seq:** 18
- **File:** `.github/workflows/meta-social-rollback-snapshot.yml`
- **Symbol / route:** seq 18 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** No confirmation; creates encrypted archive — lower risk than restore but still prod access
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 18 [KEEP_AS_IS]: No confirmation; creates encrypted archive — lower risk than restore but still prod access
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-024 — LOW

- **Inventory seq:** 28
- **File:** `.github/workflows/wa-app-review-connection-source-migrate.yml`
- **Symbol / route:** seq 28 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Blocks if public availability not false or App Review bind token set; flock lock; prints db host/name not password
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 28 [KEEP_AS_IS]: Blocks if public availability not false or App Review bind token set; flock lock; prints db host/name not password
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-025 — MEDIUM

- **Inventory seq:** 52
- **File:** `config.py`
- **Symbol / route:** seq 52 surface (KEEP_FIX)
- **Exploit / failure scenario:** In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 52 [KEEP_FIX]: In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for config.py.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-026 — LOW

- **Inventory seq:** 53
- **File:** `config/montymobile_templates.json`
- **Symbol / route:** seq 53 surface (DELETE_CANDIDATE)
- **Exploit / failure scenario:** Commits api_id, tenant UUID, source phone 96178974402; api_key empty (good). Template wa_message_id/record_guid are provider IDs.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 53 [DELETE_CANDIDATE]: Commits api_id, tenant UUID, source phone 96178974402; api_key empty (good). Template wa_message_id/record_guid are provider IDs.
- **Disposition:** `DELETE_CANDIDATE`
- **Required test:** No secrets in committed templates; scrub phone/tenant identifiers or archive.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-027 — MEDIUM

- **Inventory seq:** 97
- **File:** `dashboard/src/MobileLiveChat.auth.test.jsx`
- **Symbol / route:** seq 97 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** tests requiredPermission liveChat — App.jsx currently omits it (gap)
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 97 [KEEP_AS_IS]: tests requiredPermission liveChat — App.jsx currently omits it (gap)
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-028 — HIGH

- **Inventory seq:** 98
- **File:** `dashboard/src/components/Auth/ProtectedRoute.jsx`
- **Symbol / route:** seq 98 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** requiredPermission bypass when user.role===admin; client-only — server auth required. Path checks via canAccessPath.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 98 [KEEP_AS_IS]: requiredPermission bypass when user.role===admin; client-only — server auth required. Path checks via canAccessPath.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Server authz must not trust client admin bypass; API matrix rejects unauthorized despite client admin role claim.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-029 — LOW

- **Inventory seq:** 106
- **File:** `dashboard/src/components/Layout/Header.jsx`
- **Symbol / route:** seq 106 surface (KEEP_FIX)
- **Exploit / failure scenario:** shows user email in UI (expected); hardcoded fake notifications not from API
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 106 [KEEP_FIX]: shows user email in UI (expected); hardcoded fake notifications not from API
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for dashboard/src/components/Layout/Header.jsx.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-030 — MEDIUM

- **Inventory seq:** 109
- **File:** `dashboard/src/components/Layout/Sidebar.jsx`
- **Symbol / route:** seq 109 surface (KEEP_FIX)
- **Exploit / failure scenario:** Live Chat/Activity Flow/APK gated to tenantId===linas client-side; admin sees all permitted items; Missing tenantId defaults to linas unlocking Live Chat/Activity Flow/APK ops surfaces
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 109 [KEEP_FIX]: Live Chat/Activity Flow/APK gated to tenantId===linas client-side; admin sees all permitted items; Missing tenantId defaults to linas unlocking Live Chat/Activity Flow/APK ops surfaces
- **Disposition:** `KEEP_FIX`
- **Required test:** Missing tenantId must not unlock linas-only Sidebar ops surfaces.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-031 — LOW

- **Inventory seq:** 119
- **File:** `dashboard/src/components/SystemPromptKnowledgeStylePanel.jsx`
- **Symbol / route:** seq 119 surface (DELETE_CANDIDATE)
- **Exploit / failure scenario:** Would allow unauthenticated write only if mounted without ProtectedRoute; currently unreachable. updateTrainingFile requires authenticated api client when used.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 119 [DELETE_CANDIDATE]: Would allow unauthenticated write only if mounted without ProtectedRoute; currently unreachable. updateTrainingFile requires authenticated api client when used.
- **Disposition:** `DELETE_CANDIDATE`
- **Required test:** Confirm zero importers before delete; if remounted, require ProtectedRoute + server authz.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-032 — LOW

- **Inventory seq:** 120
- **File:** `dashboard/src/components/TrainingFileEditor.jsx`
- **Symbol / route:** seq 120 surface (DELETE_CANDIDATE)
- **Exploit / failure scenario:** restore uses window.confirm only; would POST restore with auth if mounted
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 120 [DELETE_CANDIDATE]: restore uses window.confirm only; would POST restore with auth if mounted
- **Disposition:** `DELETE_CANDIDATE`
- **Required test:** Confirm zero importers before delete; if remounted, require ProtectedRoute + server authz.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-033 — INFO

- **Inventory seq:** 129
- **File:** `dashboard/src/components/UserManagement/UserManagement.jsx`
- **Symbol / route:** seq 129 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Relies on AuthContext client permission check before API; server must enforce on /users endpoints
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 129 [KEEP_AS_IS]: Relies on AuthContext client permission check before API; server must enforce on /users endpoints
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-034 — LOW

- **Inventory seq:** 130
- **File:** `dashboard/src/components/landing/GuestChatPanel.jsx`
- **Symbol / route:** seq 130 surface (LANDING_KEEP)
- **Exploit / failure scenario:** Guest session ID in localStorage (linas_guest_session_id); no auth; input maxLength 2000; handles GUEST_INPUT_TOO_LARGE and GUEST_MEDIA_BLOCKED codes; rate limit via server session.limit_reached
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 130 [LANDING_KEEP]: Guest session ID in localStorage (linas_guest_session_id); no auth; input maxLength 2000; handles GUEST_INPUT_TOO_LARGE and GUEST_MEDIA_BLOCKED codes; rate limit via server session.limit_reached
- **Disposition:** `LANDING_KEEP`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-035 — LOW

- **Inventory seq:** 162
- **File:** `dashboard/src/hooks/useApiClient.js`
- **Symbol / route:** seq 162 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** 401 hard redirect; CSRF from localStorage; withCredentials true
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 162 [KEEP_AS_IS]: 401 hard redirect; CSRF from localStorage; withCredentials true
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-036 — MEDIUM

- **Inventory seq:** 164
- **File:** `dashboard/src/hooks/useApiLiveChat.js`
- **Symbol / route:** seq 164 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** simulateWebhook debug endpoint exposed via hook — UI must gate
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 164 [KEEP_AS_IS]: simulateWebhook debug endpoint exposed via hook — UI must gate
- **Disposition:** `KEEP_AS_IS`
- **Required test:** simulateWebhook API requires elevated permission; hook alone insufficient.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-037 — MEDIUM

- **Inventory seq:** 166
- **File:** `dashboard/src/hooks/useApiTesting.js`
- **Symbol / route:** seq 166 surface (KEEP_FIX)
- **Exploit / failure scenario:** test endpoints can drive bot with arbitrary phone — server must auth+entitle
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 166 [KEEP_FIX]: test endpoints can drive bot with arbitrary phone — server must auth+entitle
- **Disposition:** `KEEP_FIX`
- **Required test:** Testing endpoints require auth+entitlement; arbitrary phone rejected when unauthorized.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-038 — MEDIUM

- **Inventory seq:** 179
- **File:** `dashboard/src/pages/ActivityFlowCard.jsx`
- **Symbol / route:** seq 179 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Show technical JSON dumps full entry (phones/messages/CM) to any operator with activityFlow — intentional observability but high PII surface
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 179 [KEEP_AS_IS]: Show technical JSON dumps full entry (phones/messages/CM) to any operator with activityFlow — intentional observability but high PII surface
- **Disposition:** `KEEP_AS_IS`
- **Required test:** activityFlow PII dump access limited to entitled roles; consider redaction policy test.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-039 — MEDIUM

- **Inventory seq:** 183
- **File:** `dashboard/src/pages/Dashboard.jsx`
- **Symbol / route:** seq 183 surface (KEEP_FIX)
- **Exploit / failure scenario:** links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 183 [KEEP_FIX]: links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for dashboard/src/pages/Dashboard.jsx.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-040 — MEDIUM

- **Inventory seq:** 186
- **File:** `dashboard/src/pages/LiveChat.jsx`
- **Symbol / route:** seq 186 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** permission via route (mobile missing requiredPermission noted in App audit)
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 186 [KEEP_AS_IS]: permission via route (mobile missing requiredPermission noted in App audit)
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-041 — MEDIUM

- **Inventory seq:** 191
- **File:** `dashboard/src/pages/LiveChatModals.jsx`
- **Symbol / route:** seq 191 surface (KEEP_FIX)
- **Exploit / failure scenario:** FAQ save-all-languages actions — server must authz
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 191 [KEEP_FIX]: FAQ save-all-languages actions — server must authz
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for dashboard/src/pages/LiveChatModals.jsx.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-042 — LOW

- **Inventory seq:** 195
- **File:** `dashboard/src/pages/LiveChatThreadMessages.jsx`
- **Symbol / route:** seq 195 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** renders image_url/audio_url from server — trust media URLs; media send via composer operator_001 issue upstream
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 195 [KEEP_AS_IS]: renders image_url/audio_url from server — trust media URLs; media send via composer operator_001 issue upstream
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-043 — LOW

- **Inventory seq:** 201
- **File:** `dashboard/src/pages/ResetPassword.jsx`
- **Symbol / route:** seq 201 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** token in URL query (email link pattern); no client min-length beyond required — server must enforce
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 201 [KEEP_AS_IS]: token in URL query (email link pattern); no client min-length beyond required — server must enforce
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-044 — INFO

- **Inventory seq:** 306
- **File:** `deploy/nginx-linasaibot.conf`
- **Symbol / route:** seq 306 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** HTTP redirect strips query string (line 12); sensitive endpoints use linasbot_safe log format via access_log directive; webhook/oauth/data-deletion logging minimized.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 306 [KEEP_AS_IS]: HTTP redirect strips query string (line 12); sensitive endpoints use linasbot_safe log format via access_log directive; webhook/oauth/data-deletion logging minimized.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-045 — INFO

- **Inventory seq:** 307
- **File:** `deploy/nginx-privacy-log.conf`
- **Symbol / route:** seq 307 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Deliberately excludes $request_uri/$args—reduces OAuth/webhook token leakage into access logs.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 307 [KEEP_AS_IS]: Deliberately excludes $request_uri/$args—reduces OAuth/webhook token leakage into access logs.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-046 — LOW

- **Inventory seq:** 308
- **File:** `deploy/systemd/linasbot-worker@.service`
- **Symbol / route:** seq 308 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** Runs as root; loads EnvironmentFile .env—ensure file permissions restricted.
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 308 [KEEP_AS_IS]: Runs as root; loads EnvironmentFile .env—ensure file permissions restricted.
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-047 — MEDIUM

- **Inventory seq:** 463
- **File:** `handlers/text_handlers_message.py`
- **Symbol / route:** seq 463 surface (KEEP_FIX)
- **Exploit / failure scenario:** verbose DEBUG prints include user_id, phone, message preview — log PII risk
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 463 [KEEP_FIX]: verbose DEBUG prints include user_id, phone, message preview — log PII risk
- **Disposition:** `KEEP_FIX`
- **Required test:** DEBUG logs must not emit phone/message preview at production log level.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-048 — MEDIUM

- **Inventory seq:** 477
- **File:** `handlers/text_handlers_respond_phase6.py`
- **Symbol / route:** seq 477 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** coerces unauthorized human_handover after post-release cooldown
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 477 [KEEP_AS_IS]: coerces unauthorized human_handover after post-release cooldown
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-049 — INFO

- **Inventory seq:** 489
- **File:** `main.py`
- **Symbol / route:** seq 489 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** access_log=False to avoid webhook query secrets in logs; APK route requires auth+liveChat permission
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 489 [KEEP_AS_IS]: access_log=False to avoid webhook query secrets in logs; APK route requires auth+liveChat permission
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-050 — INFO

- **Inventory seq:** 1101
- **File:** `services/guest_ai_service.py`
- **Symbol / route:** seq 1101 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** FORBIDDEN_GUEST_TOOLS denylist blocks CM/tool writes; no tenant mutation by design
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1101 [KEEP_AS_IS]: FORBIDDEN_GUEST_TOOLS denylist blocks CM/tool writes; no tenant mutation by design
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-051 — INFO

- **Inventory seq:** 1145
- **File:** `services/meta_app_registry_oauth.py`
- **Symbol / route:** seq 1145 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1145 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-052 — INFO

- **Inventory seq:** 1157
- **File:** `services/meta_instagram_login_oauth.py`
- **Symbol / route:** seq 1157 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1157 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-053 — INFO

- **Inventory seq:** 1160
- **File:** `services/meta_instagram_login_tokens.py`
- **Symbol / route:** seq 1160 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1160 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-054 — MEDIUM

- **Inventory seq:** 1161
- **File:** `services/meta_messaging.py`
- **Symbol / route:** seq 1161 surface (KEEP_FIX)
- **Exploit / failure scenario:** HMAC signature verification on webhooks; page tokens from env/registry
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1161 [KEEP_FIX]: HMAC signature verification on webhooks; page tokens from env/registry
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for services/meta_messaging.py.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-055 — INFO

- **Inventory seq:** 1163
- **File:** `services/meta_oauth.py`
- **Symbol / route:** seq 1163 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** tokens encrypted via meta_app_registry AES-GCM; state TTL 10min; scopes validated
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1163 [KEEP_AS_IS]: tokens encrypted via meta_app_registry AES-GCM; state TTL 10min; scopes validated
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-056 — INFO

- **Inventory seq:** 1164
- **File:** `services/meta_oauth_graph.py`
- **Symbol / route:** seq 1164 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1164 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-057 — INFO

- **Inventory seq:** 1165
- **File:** `services/meta_oauth_return.py`
- **Symbol / route:** seq 1165 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1165 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-058 — MEDIUM

- **Inventory seq:** 1171
- **File:** `services/mobile_refresh_token_service.py`
- **Symbol / route:** seq 1171 surface (KEEP_FIX)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1171 [KEEP_FIX]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_FIX`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-059 — MEDIUM

- **Inventory seq:** 1227
- **File:** `services/owner_push_token_store.py`
- **Symbol / route:** seq 1227 surface (KEEP_FIX)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1227 [KEEP_FIX]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_FIX`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-060 — INFO

- **Inventory seq:** 1254
- **File:** `services/sensitive_request_logging.py`
- **Symbol / route:** seq 1254 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** redacts tokens/secrets in logs — must remain installed at startup
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1254 [KEEP_AS_IS]: redacts tokens/secrets in logs — must remain installed at startup
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-061 — INFO

- **Inventory seq:** 1276
- **File:** `services/store_iap_service.py`
- **Symbol / route:** seq 1276 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1276 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-062 — INFO

- **Inventory seq:** 1277
- **File:** `services/stripe_checkout_service.py`
- **Symbol / route:** seq 1277 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1277 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-063 — INFO

- **Inventory seq:** 1288
- **File:** `services/token_metering.py`
- **Symbol / route:** seq 1288 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1288 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-064 — INFO

- **Inventory seq:** 1289
- **File:** `services/token_package_catalog.py`
- **Symbol / route:** seq 1289 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1289 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-065 — MEDIUM

- **Inventory seq:** 1290
- **File:** `services/token_wallet_models.py`
- **Symbol / route:** seq 1290 surface (KEEP_FIX)
- **Exploit / failure scenario:** linas default tenant reference; secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1290 [KEEP_FIX]: linas default tenant reference; secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_FIX`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-066 — INFO

- **Inventory seq:** 1291
- **File:** `services/token_wallet_service.py`
- **Symbol / route:** seq 1291 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** InsufficientTokenBalance fail-closed; threaded RLock on wallet files
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1291 [KEEP_AS_IS]: InsufficientTokenBalance fail-closed; threaded RLock on wallet files
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Monitor: no new exposure; periodic review that mitigations remain.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-067 — MEDIUM

- **Inventory seq:** 1295
- **File:** `services/user_service.py`
- **Symbol / route:** seq 1295 surface (KEEP_FIX)
- **Exploit / failure scenario:** bcrypt hashing; query timeouts; tenant-scoped collection paths
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1295 [KEEP_FIX]: bcrypt hashing; query timeouts; tenant-scoped collection paths
- **Disposition:** `KEEP_FIX`
- **Required test:** Regression covering security note for services/user_service.py.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-068 — INFO

- **Inventory seq:** 1297
- **File:** `services/wallet_spend_analytics.py`
- **Symbol / route:** seq 1297 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1297 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

### SEC-069 — INFO

- **Inventory seq:** 1315
- **File:** `services/whatsapp_cloud/crypto.py`
- **Symbol / route:** seq 1315 surface (KEEP_AS_IS)
- **Exploit / failure scenario:** secrets/billing surface — server-side only; API authz required
- **Evidence:** ALL_PROBLEMS_FOUND.md § Other substantive security notes — Seq 1315 [KEEP_AS_IS]: secrets/billing surface — server-side only; API authz required
- **Disposition:** `KEEP_AS_IS`
- **Required test:** Endpoint auth matrix: unauthenticated and non-authorized callers rejected for billing/secrets routes.
- **Status:** OPEN
- **Source bucket:** Other substantive security notes

---

## Notes

- Official total includes all confirmed findings from the listed sources — not only the historical “15 KEEP_SECURITY_FIX” snapshot (inventory now has **16** including seq 801).
- Seq 801 corrects earlier unauthenticated allegations: middleware enforces auth+`liveChat`; residual issue is **insufficient elevation** (HIGH).
- Seq 870 remains an official finding with disposition `MOVE_TO_ARCHIVE` (protected ops / archive — do not delete casually; do not wire into CI).
- Cross-check known-concern reconciliation in `docs/audit/_phase0c_known_concerns.md`.

---


### SEC-070 — HIGH — seq 535 `mobile/linas-ai/src/auth/guestSession.ts`

- **Symbol/route:** `randomId` / `getOrCreateGuestSessionId`
- **Exploit/failure scenario:** Guest session IDs filled via `Math.random` into `Uint8Array` instead of `crypto.getRandomValues` — more guessable guest ids across devices/sessions.
- **Evidence:** ID entropy via Math.random filling Uint8Array — not crypto.getRandomValues; guest ids more guessable
- **Disposition:** `KEEP_SECURITY_FIX`
- **Required test:** Assert guest id generation uses CSPRNG (`getRandomValues`); collision/entropy smoke.
- **Status:** OPEN
- **Source bucket:** PHASE0C_FOLLOWUP (W0C-B1)


## Previously known security concerns (Phase 0C)

Each concern has **exactly one** status.

| # | Concern | Status | Evidence |
|---|---|---|---|
| 1 | Mobile login and refresh rate limiting | **ALREADY_FIXED** | `services/auth_rate_limits.py` `auth_rate_limit_rules` for `/api/auth/mobile/login` and `/api/auth/mobile/refresh` (IP + identifier buckets). Wired via `modules/api_security.py` → `check_rate_limit`. Tests: `tests/test_wave1_security.py` (mobile login/refresh rule assertions). Commit `778ab86`. |
| 2 | Trusted proxy / client-IP resolution | **ALREADY_FIXED** | `client_ip()` prefers `X-Real-IP` (nginx `$remote_addr`), does **not** trust leftmost `X-Forwarded-For`. `TRUSTED_PROXY_MODE=direct|x-real-ip`. Commit `778ab86`. |
| 3 | Wallet admin-credit authorization | **ALREADY_FIXED** | `modules/wallet_api.py` `_admin_credit_allowed` + `assert_admin_credit_target_allowed` — cross-tenant only `platform_owner`; allowlisted tenant admins same-tenant. Tests: `tests/test_saas_auth_token_wallet.py::test_admin_credit_cross_tenant_platform_owner_only`. Commit `caacdfe`. |
| 4 | Production CORS | **ALREADY_FIXED** | `modules/core.py` `cors_allow_origins()` — production drops `http://linasaibot.com` / `http://www…`; keeps HTTPS + localhost. Commit `caacdfe`. |
| 5 | Tenant assertions on shared handlers | **CONFIRMED_FIX_REQUIRED** | Middleware gate **exists**: non-`linas` sessions blocked from legacy `/api/live-chat` etc. (`modules/api_security.py`). Remaining gap: many services still silently default `tenant_id` to `linas` (e.g. `services/user_service.py`, `meta_messaging.py`, `social_contact_routing.py`, wallet models) — SaaS isolation debt. Inventory `KEEP_FIX` rows track defaults. |
| 6 | Role/permission elevation | **CONFIRMED_FIX_REQUIRED** | `dashboard/src/contexts/AuthContext.helpers.js` `buildUserData` defaults `role=admin` and `tenantId=linas`; `RoleManager` custom roles in `localStorage`; `ProtectedRoute` admin bypass; `App.jsx` `/mobile/live-chat` missing `requiredPermission=liveChat`. Dispositions `KEEP_SECURITY_FIX` on seq 95/126/152/197. |
| 7 | CSRF and constant-time secret comparison | **ALREADY_FIXED** | Cookie mutations require CSRF header+cookie; `hmac.compare_digest` in `modules/api_security.py`. Also webhook verify tokens use `compare_digest`. Commit `5365550`. Wave1 CSRF tests present (env fixture errors noted in BASELINE_TESTS_BUILDS — test existence still evidence of intent). |
| 8 | Filename/path sanitization | **ALREADY_FIXED** | `services/media_service.py` `sanitize_media_filename` + `resolve_media_file_path` (`relative_to` containment); `services/safe_path.py` for backup/restore. Covered by wave1 SSRF/path tests. |
| 9 | Distributed production rate limiting | **CONFIRMED_FIX_REQUIRED** | `services/rate_limit_service.py` is **file-backed per-process** only (`_DATA_ROOT/auth/rate_limits`). No Redis/distributed limiter implemented in-tree. Multi-instance deploy can under-enforce limits. `docs/audit/RESIDUAL_STATUS.md` notes Redis workers optional/unset. |

## False positives recorded this phase

| Item | Status | Evidence |
|---|---|---|
| `services/cm/shadow_eval.py` “eval() present” | **FALSE_POSITIVE** | Only symbol is `run_shadow_eval`; no Python `eval(` builtin. Lab/golden offline evaluator; must not be on live webhook path (documented in module docstring). |

## Blocked

None for the nine known concerns above.
