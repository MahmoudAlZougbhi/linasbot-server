# Content Management AI Control Plane — PLAN ONLY (Revised)

**Status:** PLANNING ARTIFACT — directionally approved; **build-ready only after this revision is accepted**  
**Do not implement** until owner + supervisor explicit build approval  
**Repository:** `/Users/alzoughbi/linasbot-server`  
**Revised:** 2026-08-02  
**Terminology:** Owner may say “Contact Management”; product surface is **Content Management / Content Managers** (`/content-managers`).

---

## 0. Revision delta (this update)

| # | Correction | Change in plan |
|---|------------|----------------|
| 1 | Target runtime order | Replaced earlier “handoff → FAQ → Interpreter” sketch with the **canonical post-cutover order** in §13 (Restricted before handoff; FAQ before Interpreter; FAQ hits skip Interpreter/generative calls). |
| 2 | Single source of truth | New §2.7 / §13.2: after cutover, all Linas business facts from **published CM version only**; locked platform rules in code; **final audit** proving zero active Linas facts in code/env defaults/legacy loaders; no silent legacy fallback. |
| 3 | Restricted precedence | Restricted runs **before** booking/handoff; restricted request never returns WA number; conflicts = **hard publish blockers**; initial defaults tattoo/CO2/pigmentation/facial. |
| 4 | Phase 2 Publish | Publish **visibly disabled** with truthful copy; **no fake/no-op Publish**. |
| 5 | Shadow mode | No per-live-message shadow AI; Lab / golden / sanitized replay / optional bounded async sample only with approval; zero customer latency/cost impact. |
| 6 | Tenant scope | Tenant IDs/indexes/caches/manifests **only inside CM subsystem**; do not relocate Meta/Live Chat/Analytics/Auth/CRM/conversations. |
| 7 | Concurrency & integrity | New §14.3: ETag/revision, atomic replace, locks, stale-draft UI, atomic content+index activation, cache key `tenant_id+version_id`, checksums, referential integrity. |
| 8 | Notes safety | Notes untrusted; **deterministic** validators mandatory; AI-assist warnings optional only. |
| 9 | Final-response validator | New deterministic pre-send validator in runtime order + §13.3. |
| 10 | Owner decisions | D1–D12 **resolved** in §21 (no longer open). |
| 11 | Acceptance tests | Expanded T21–T31 covering FAQ-skip-Interpreter, restricted+booking, concurrency, atomic rollback, zero-legacy scan, no shadow latency. |
| 12 | Plan only | Confirmed: artifact-only revision; no implementation. |

---

## 1. Executive owner summary (plain language)

Today, configuring Linas AI is split and technical: Content Managers edit knowledge/price/style files and a raw-ish System Prompt panel; FAQ 4-language training lives under Bot Training; Instagram/Facebook answers still use social WhatsApp handoff (before FAQ), string FAQ matching, a weak title-based file selector, and a large AI—with many clinic facts still in code.

**This plan** turns Content Management into a guided control plane: forms for exact facts, editors for narrative knowledge, Restricted Topics that block handoff, FAQ preserved with 4-language auto-translate, and a post-cutover runtime that loads one published CM version, answers FAQ without extra AI calls when possible, then uses a Query Interpreter + structured facts + semantic chunks + the existing large-AI pipeline, finished by a deterministic validator.

**No code, production, Meta, secrets, or customer messages are changed by this document.**

---

## 2. Fresh current-state evidence (Phase 0 baseline)

### 2.1 Repository / worktrees (preserved — do not touch)

| Item | Value (planning baseline) |
|------|---------------------------|
| Repo | `/Users/alzoughbi/linasbot-server` |
| Branch | `fix/testing-lab-chat-view` |
| HEAD | `b42ea4b75b847300801a3618f82e16f4e14f93d5` |
| `origin/main` / prod deploy evidence | `78d7c41` (deploy run `30750494714`) |
| Prod data root | `/opt/linasbot_data` |
| Local ≠ prod | **Do not claim equality** without proven hashes |
| Worktrees | pause-resume `17d67ee`; Meta `feat/meta-verified-social-app`; ops `/private/tmp/linasbot-*` |
| Stashes | `meta-wip-pre-main-f1c4c79`, `probe` |

### 2.2 Current Content Management frontend

| Item | Evidence |
|------|----------|
| Route | `/content-managers` |
| Page | `dashboard/src/pages/ContentManagers.jsx` |
| Tabs today | Knowledge, Prices, Style, Dynamic Messages, System Prompt (Template + KB + Style) |
| FAQ UI today | `/training` — **not** in Content Managers |
| APIs | `/api/content-files/*`, training-files, dynamic-messages, `/api/local-qa/*` |

### 2.3 Current runtime (pre-cutover — evidence)

```text
IG/FB webhook → social WA router (before FAQ) → FAQ ≥90% SequenceMatcher
  → title-selector LLM → get_bot_chat_response → social post-process → Meta send
WhatsApp inbound AI: disabled
```

Prior audit (`AI_ANSWER_PATH_AUDIT.md`) remains valid for **today’s** path. **Target path is §13** (different order).

### 2.4 Frozen product contracts

| Contract | Rule |
|----------|------|
| Languages | AR, EN, FR, Franco |
| Response map | AR→AR, EN→EN, FR→FR, Franco→**Arabic** |
| FAQ authoring | Auto 4 linked variants; Franco answer = Arabic script |
| Channels | IG/FB inbound AI only; WA handoff-only; no comments; no social dashboard takeover |
| Testing Lab | No real Meta/WA send; no lab writes into production customer history |
| Meta | No app/token/webhook/App Review/publish work in this program |
| Exact FAQ match | Preserved forever; semantic FAQ is additive after exact |

### 2.5 Frozen-scope matrix

| Surface | Status |
|---------|--------|
| Meta webhooks/tokens/App Review | Frozen |
| WhatsApp inbound AI disabled | Frozen |
| Live Chat / Smart Messaging / Analytics / Auth / Booking CRM cores | Frozen (not relocated into CM) |
| Conversations / customer history stores | Frozen (not tenant-redesigned here) |
| Unrelated worktrees/stashes | Frozen |
| `/content-managers` UX + CM storage/index/publish | May change (phased) |
| Minimal answer-path integration reading **published** CM | May change (Phase 6–8 only) |
| Social handoff **data source** | Migrated into CM draft early; **runtime cutover Phase 8 only** |

### 2.6 Initial Restricted defaults (subject to final owner confirm before first publish)

Unless the owner changes them in an **approved published** version:

- Tattoo removal  
- CO2 laser  
- Pigmentation removal  
- Facial / skin-cleaning sessions  

### 2.7 Final single-source-of-truth contract (after verified cutover)

| Rule | Requirement |
|------|-------------|
| Business facts | All Linas-specific **services, availability, prices, branches, hours, public WhatsApp numbers, unsupported topics, style, and business behavior** come **only** from the immutable **published CM version** for the tenant. |
| Platform rules | Auth, tenant isolation (CM), Meta signature, channel policy, tool allowlists, timeouts, security boundaries remain in **locked code**. |
| No silent fallback | After cutover: **no** fallback to legacy foundation TXT, env business defaults, dead QA stores, hardcoded clinic facts, or old content-files loaders for answers. |
| Missing/invalid published data | Observable honest failure/clarification path — **never** fake success or silent legacy fill. |
| Final audit gate | Explicit Phase 8 audit proving **zero active Linas-specific business facts** remain in code, environment defaults, legacy FAQ stores, foundation TXT, or dead runtime loaders. |

---

## 3. Current vs target architecture

**Today:** split Training/CM/Settings; title selector; handoff before FAQ; facts in code.  
**Target:** CM Control Plane as SoT; order in §13; Query Interpreter only after FAQ miss; deterministic validators.

---

## 4. Screen / navigation map (resolved IA)

**Hub:** `/content-managers` landing cards → dedicated screens.  
**Permissions (resolved):**

- `contentManagers` (or equivalent **draft-edit**) — edit drafts including FAQ  
- `contentPublish` — validate/publish/rollback (Admin / Content Publisher)  
- FAQ: **CM permission is canonical**; temporary Training write compat only during migration  

| Card | Route | Notes |
|------|-------|-------|
| Overview | `/content-managers` | Draft dirty, last publish, validation |
| AI Basics | `…/ai-basics` | |
| Languages | `…/languages` | Canonical language-policy editor |
| Style & Tone | `…/style` | |
| **Dynamic Messages** | `…/dynamic-messages` | **Separate card (D2)** |
| Services | `…/services` | |
| Branches & Hours | `…/branches` | |
| Prices | `…/prices` | |
| Preparation & Aftercare | `…/care` | |
| Knowledge | `…/knowledge` | |
| FAQ | `…/faq` | 4-lang auto-translate preserved |
| Booking & Human Handoff | `…/handoff` | Matrix authoring; runtime cutover Phase 8 |
| Restricted / Unsupported | `…/restricted` | Hard conflicts |
| Preview / Validate / Publish | `…/publish` | Publish disabled until phases allow |

**Training FAQ after cutover (D5):** read-only + direct users to CM FAQ; **one writer only**.  
**Settings Languages (D12):** unchanged early; after cutover approval → read-only mirror/link to CM Languages.  
**Advanced AI Instructions (D6):** Admin / Content Publisher only.

---

## 5. Text wireframes (summary)

Landing shows all cards including **Dynamic Messages** and **Restricted**.  
Each section: breadcrumb, Save Draft, Validate; Publish only on Publish screen when enabled.  
**Phase 2 Publish control:**

```
[ Publish — unavailable ]
Publishing is not enabled yet. This phase saves drafts only.
No customer-facing AI behavior will change until a later approved phase.
```

No fake success. No no-op Publish button that pretends to publish.

(Full section wireframe sketches remain as in prior revision for AI Basics, Languages, Style, Services, Branches, Prices, Care, Knowledge, FAQ, Handoff, Restricted, Publish — with Restricted conflict banners as **hard blockers**, and Handoff rows for restricted services disabled/blocked.)

---

## 6. Schemas & validation (high level)

Storage: `{DATA_ROOT}/tenants/{tenant_id}/cm/{draft|published|versions|indexes|snapshots}/`  
Tenant scope **applies only to this CM subtree** (and its indexes/caches/manifests)—not a redesign of conversations/Meta/Live Chat/Analytics/Auth/CRM.

Common draft envelope includes `revision` / `etag`, `tenant_id`, `updated_at`, `updated_by`.

### Notes (D3 + safety)

- Author Notes in **one natural language**.  
- At publish/index time, Notes may be **indexed multilingually** for retrieval.  
- **Do not** auto-create four stored FAQ-style translations for Notes.  
- Four-language automatic translation remains **FAQ-only**.

### Restricted (D4, D8)

- Hard publish blockers if Restricted conflicts with Services (available), Prices, FAQ answers, Knowledge claims, or Handoff matrix rows that would route that topic.  
- Runtime: restricted intent **never** proceeds to booking/WA handoff.

### Handoff (D9)

- Import current WA numbers into CM **draft** during migration.  
- Runtime continues using existing env/code path until **Phase 8** validated cutover.

### Embeddings (D11)

- Configurable provider compatible with current OpenAI stack.  
- Pin `provider`, `model`, `version`, `dimensions` in every index/version manifest.  
- Measure cost before cutover.

---

## 7. Notes safety (strengthened)

| Rule | Enforcement |
|------|-------------|
| Structured fields authoritative | Always |
| Notes untrusted explanatory | Never change price, currency, availability, hours, branch, public contact, restricted status, platform/channel behavior |
| Deterministic validation | **Required** on save/validate/publish (patterns for amounts, E.164, availability verbs vs structured rows, etc.) |
| AI-assisted conflict detection | Optional **warnings only**; cannot be the sole validator |
| Precedence | Structured > Notes > narrative chunks > model general knowledge |

---

## 8. Language / FAQ preservation

1. Keep `qa_group_id` + 4 variants; Franco answer = Arabic.  
2. CM FAQ is canonical writer after migration window; Training write temporarily compatible then read-only.  
3. Match order: **exact → semantic FAQ**; response mapping frozen.  
4. FAQ hit: return approved answer **without** Query Interpreter and **without** generative answer call.

---

## 9. Structured vs semantic matrix

| Class | Mechanism |
|-------|-----------|
| AI Basics, language, style, dynamic-message catalog (as designed) | Always from published version |
| Services, branches, hours, prices, handoff, restricted | Structured resolver |
| FAQ | Exact then semantic FAQ index |
| Knowledge / prep / aftercare / educational Notes | Bounded semantic chunks |
| Platform/security/channel | Locked code |
| Legacy files after cutover | Archived only — **not** runtime |

---

## 10. Migration map (no data loss)

Unchanged copy-first strategy; plus:

1. **D10:** Approved production snapshot window **before any migration write**.  
2. Prefill Restricted defaults; flag FAQ/knowledge that affirm restricted topics as hard conflicts until fixed.  
3. Prefill Handoff matrix from current WA defaults into draft only.  
4. Archive dead `qa_database.json` / remote-QA train paths.  
5. After cutover: remove/disable legacy loaders; run SoT final audit.

---

## 11. System Prompt split

| Layer | Editable? |
|-------|-----------|
| Locked platform base | No (code) |
| AI Basics / language / style | Yes (published CM) |
| Structured business rules | Yes (forms) |
| Retrieved chunks | Yes (articles) |
| Runtime history | System |
| Output contract + final validator | Code |
| Advanced AI Instructions | Admin/Publisher only; cannot override platform/structured/restricted/channel |

---

## 12. Canonical target runtime flow (post-cutover) — CORRECTED

```text
1. Existing webhook security, identity, dedupe, channel controls
2. Load ONE immutable published CM version for tenant_id
      (missing/corrupt → honest failure/clarify; NO legacy fallback)
3. Detect language via existing language resolver
4. Apply locked platform/safety rules (code)
5. Resolve Restricted / Unsupported Topics
      if restricted service/topic → refuse path; STOP (never handoff)
6. If explicit booking/human-agent intent AND service supported
      → published structured handoff matrix → WA reply path; STOP
7. Exact FAQ match
8. Else semantic FAQ match
9. If FAQ hit → return approved answer with response mapping
      (AR→AR, EN→EN, FR→FR, Franco→Arabic)
      NO Query Interpreter, NO generative answer call
10. Only on FAQ miss → Query Interpreter
       (intent, service, branch, audience, langs, missing slots,
        negation, follow-ups, Franco variants)
11. Resolve structured facts from published version
12. Retrieve bounded semantic narrative chunks (+ source IDs)
13. Assemble grounded answer packet
       (identity/style/language | facts | chunks | platform rules | history)
14. Call existing canonical large-AI pipeline (get_bot_chat_response)
15. Deterministic final-response validator (§13.3)
       invalid → do not send as success; regenerate-once policy TBD in build
       or honest fallback message — never fake success
16. Existing social post-processing
17. Send via unchanged Meta adapter
```

### 12.1 Call-count rules

| Path | Query Interpreter | Generative answer |
|------|-------------------|-------------------|
| Restricted refuse | No | No (template refuse) |
| Supported handoff | No | No (matrix template) |
| FAQ hit | **No** | **No** |
| FAQ miss | Yes (≤1 small call or deterministic+embed design) | Yes (existing pipeline) |

### 12.2 Final-response validator (deterministic)

Before send, claim-check against answer packet:

- Service is supported (not restricted; available in structured services)  
- Price/currency match structured price rows when a price is stated  
- Branch/hours match structured records when stated  
- WhatsApp number/link matches handoff matrix when stated  
- Restricted services are not offered  
- Response language follows language policy (incl. Franco→Arabic)  
- No unsupported business fact introduced  
- Required provenance/source IDs present for business claims  

**Invalid output must not be sent as if successful.**

### 12.3 Shadow evaluation constraints (Phase 5)

**Forbidden:** additional shadow AI call on **every live customer message**.

**Allowed start set:**

- Testing Lab simulations  
- Synthetic golden dialogues  
- Sanitized/replayed historical questions (offline/batch)  
- Optionally a **bounded asynchronous sample** only after **explicit approval**

Shadow failures must **not** affect customer replies, latency, cost, or production history.

---

## 13. API / storage / index / concurrency

### 13.1 Storage layout (CM subsystem only)

```
{DATA_ROOT}/tenants/{tenant_id}/cm/
  draft/ … (+ section revision/etag)
  published/pointer.json  → version_id + index_id + content_checksum
  versions/{version_id}/manifest.json + payload
  indexes/{index_id}/ …   (pinned embedding provider/model/version/dimensions)
  snapshots/…
  archive/legacy_…
```

### 13.2 APIs (future)

Draft CRUD with `If-Match` / revision; validate; publish; versions; rollback; preview-packet for Lab.  
Legacy `/api/content-files` and Training FAQ writes: compat window then read-only/archive.

### 13.3 Concurrency & integrity contracts

| Contract | Requirement |
|----------|-------------|
| Optimistic concurrency | Every draft section has `revision`/`ETag`; writes require `If-Match`; conflict → 409 |
| Stale-draft UI | Show conflict; reload vs overwrite-with-confirm (never silent) |
| Atomic file replace | Write temp + fsync + rename, or repo canonical transactional store |
| Server-side locking | Publish/reindex/rollback critical sections locked per tenant |
| Atomic activation | Single pointer update binds `content_version_id` + `index_version_id` together |
| Cache | Keyed by `tenant_id + version_id`; invalidate on pointer change |
| Rollback | One operation restores content pointer **and** index pointer |
| Checksums | Manifest stores payload + index checksums; load verifies |
| Referential integrity | Publish validates service/branch/price/handoff/FAQ/restricted refs |
| Corrupt/missing index | Observable error/metrics; **no** silent legacy knowledge |

### 13.4 RBAC (resolved)

| Permission | Capability |
|------------|------------|
| Draft-edit (`contentManagers`) | Edit all CM drafts including FAQ |
| Publish (`contentPublish`) | Validate, publish, rollback; see Advanced Instructions |
| Training (legacy) | Temporary FAQ write during migration only → then read-only redirect |

---

## 14. Phased implementation plan (updated exit criteria)

**Mandatory loop each phase:** implement → all gates → focused audit → fix every finding → re-gate → re-audit → next phase. No severity-based deferral.

### Phase 0 — Baseline, backups, inventory, freeze

| | |
|--|--|
| Objective | Snapshots/hashes; contracts; D10 snapshot window scheduled |
| Exit | Snapshot manifest; owner ACK frozen contracts + restricted defaults intent |
| Audit | Local≠prod disclaimer recorded |

### Phase 1 — Schemas/contracts + UI IA

| | |
|--|--|
| Objective | Schemas with revision/ETag; nav including Dynamic Messages + Restricted; RBAC keys draft vs publish |
| Exit | Schema review approved; Notes/Restricted/SoT rules encoded in schema docs |
| Audit | No runtime wiring |

### Phase 2 — CM screens + draft storage (**no runtime change**)

| | |
|--|--|
| Objective | All section screens; draft save with concurrency; **Publish visibly disabled** with truthful explanation |
| Exit | Draft CRUD works; Publish control cannot be clicked/activated; API publish endpoint absent or hard-403 with same message; zero customer impact |
| Audit | No answer path reads drafts; no fake/no-op publish |

### Phase 3 — FAQ in CM + structured records

| | |
|--|--|
| Objective | CM FAQ uses same 4-lang engine; Services/Branches/Prices/Handoff/Restricted forms; deterministic Notes validators; hard Restricted conflict checks on validate |
| Exit | FAQ parity tests green; Training still writable only via compat flag; restricted defaults present in draft |
| Audit | Franco→Arabic; qa_group_id intact; Notes cannot override structured fields in validation tests |

### Phase 4 — Migration drafts + owner review

| | |
|--|--|
| Objective | After **approved prod snapshot window**, copy-migrate; WA numbers into handoff draft; conflict queues |
| Exit | Owner approves migration draft; all hard conflicts resolved or explicitly waived in writing (waivers not for Restricted↔Services/Prices/FAQ/Knowledge/Handoff — those must be fixed) |
| Audit | Mapping 100% classified; checksums |

### Phase 5 — Semantic index + Interpreter (**constrained shadow**)

| | |
|--|--|
| Objective | Build versioned indexes; evaluate Interpreter/FAQ semantic on Lab/golden/replay only |
| Exit | Shadow reports complete; **proof of zero added live-customer latency/cost**; no production history writes from shadow |
| Audit | No per-message live shadow AI |

### Phase 6 — Gated prompt assembly + validator (Lab/flag)

| | |
|--|--|
| Objective | Feature-flagged packet assembly + final-response validator on Lab / non-prod paths |
| Exit | Flag default off for customers; Lab can exercise full §12 order |
| Audit | FAQ hit skips Interpreter/generative; Restricted blocks handoff |

### Phase 7 — Full verification

| | |
|--|--|
| Objective | Full acceptance matrix §15; measured perf/cost; security; a11y; QG |
| Exit | All tests green including T21–T31; embedding cost report; no deferred findings |
| Audit | Fresh focused audit clean |

### Phase 8 — Atomic cutover, SoT cleanup, final audit

| | |
|--|--|
| Objective | Activate published CM+index pointers; handoff runtime reads CM matrix; disable legacy business loaders; Training FAQ read-only redirect; Settings languages mirror when approved |
| Exit | Soak OK; rollback drill OK; **final SoT audit: zero active Linas business facts outside published CM**; legacy paths removed/disabled |
| Evidence | version_id, index_id, checksums, audit ledger |

---

## 15. Acceptance / regression-test matrix

| ID | Case | Expect |
|----|------|--------|
| T1–T3 | AR/EN/FR/(Franco) language map | Correct response language |
| T4 | FAQ exact hit | Approved FAQ answer; bypass generative |
| T5 | FAQ 4-lang create | 4 rows + qa_group_id |
| T6 | Structured price | Exact amount used |
| T7 | Restricted topic | Refuse; not offered |
| T8 | Restricted vs Service/Price/FAQ/Knowledge/Handoff | **Publish blocked** |
| T9 | Supported booking intent | WA from published matrix (post-cutover) |
| T10 | WA inbound | Still ignored |
| T11 | Lab Meta | No Graph send; no prod history write |
| T12 | Cross-tenant | No retrieval leak |
| T13 | Rollback | Content+index atomic restore |
| T14 | Migration completeness | All hashes classified |
| T15 | Notes injection/override | Deterministic reject |
| T16 | Missing published CM/index | Observable honest path; no legacy silence |
| T17 | Draft-edit without publish perm | Cannot publish |
| T18 | Unsaved navigation | Warn |
| T19 | Publish validation UI | Lists hard blockers |
| T20 | Perf budget | Measured p95 |
| **T21** | FAQ hit | **No Query Interpreter call; no generative answer call** |
| **T22** | Franco FAQ hit | Arabic script answer |
| **T23** | Restricted + booking request | **Never returns handoff number** |
| **T24** | Notes vs structured price/availability | Notes cannot win |
| **T25** | Two concurrent editors | No silent overwrite; 409/stale UI |
| **T26** | Version + index activate/rollback | Atomic together |
| **T27** | Missing/corrupt index | Observable; no silent legacy knowledge |
| **T28** | Final validator | Blocks altered price, unsupported service, wrong branch, wrong phone, wrong language |
| **T29** | Post-cutover SoT scan | Zero active Linas business facts outside published CM |
| **T30** | Shadow mode | No additional customer latency/cost |
| **T31** | FAQ miss path | Interpreter then structured+chunks then large AI then validator |

Plus existing QG, FE/BE, FAQ translation, Meta social suites.

---

## 16. Performance plan

- No scan-all-files per message  
- Publish-time indexing; delta reindex  
- Bounded K; atomic activation  
- FAQ hit cheapest path (no Interpreter/generative)  
- Measure baselines in Phase 7; no invented numbers  
- Shadow never on hot live path  

---

## 17. Risk & rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Data loss | Snapshot window + copy-first | Restore snapshot |
| Restricted leak to WA | Runtime order step 5 before 6; T23 | Version rollback |
| Silent legacy after cutover | Disable loaders; T16/T29 | Halt + rollback pointer |
| Concurrent overwrite | ETag + UI | — |
| Index/content skew | Atomic dual pointer | Dual rollback |
| Shadow cost/latency | Constrained shadow | Disable sample |
| Dual FAQ writers | Compat flag then read-only Training | — |

---

## 18. Files likely touched vs frozen (future build)

**Likely:** CM dashboard pages, `modules/cm_*`, `services/cm_*`, FAQ API wrappers, minimal respond/chat packet + validator hooks, migration scripts, CM indexes.  

**Frozen:** Meta adapter/webhook secrets, WA inbound disable, Live Chat/Smart Messaging/Analytics/Auth/CRM redesigns, unrelated worktrees.

---

## 19. Resolved owner decision table

| ID | Resolution |
|----|------------|
| **D1** | Content Management permission is **canonical for FAQ**. Temporary legacy Training write compatibility only during migration. |
| **D2** | Keep **Dynamic Messages** as a **separate** Content Management card. |
| **D3** | Notes authored in one language; indexed multilingually. **No** auto four stored Note translations. FAQ keeps 4-lang auto-translate. |
| **D4** | Restricted conflicts are **hard publish blockers**. |
| **D5** | After full parity + cutover: legacy Training FAQ UI **read-only** + directs to CM FAQ. **No two writers**. |
| **D6** | Advanced AI Instructions visible only to **Admin / Content Publisher**. |
| **D7** | Separate **draft-edit** and **publish** permissions. |
| **D8** | Initial restricted defaults: tattoo removal, CO2, pigmentation removal, facial/skin-cleaning — **final owner confirmation before first publish**. |
| **D9** | Import WA handoff numbers into CM **draft** during migration; **runtime cutover only Phase 8** after validation. |
| **D10** | **Approved production snapshot window required** before any migration write. |
| **D11** | Configurable embedding provider compatible with current OpenAI stack; pin provider/model/version/dimensions in every index/version manifest; measure cost before cutover. |
| **D12** | CM is **canonical language-policy editor**. Settings unchanged early; after cutover approval → read-only mirror/link only. |

---

## 20. Confirmation — plan only (this revision)

- Only `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md` was updated.  
- No application code, tests, config, production, Meta, secrets, customer data, branches, stashes, or unrelated worktrees modified.  
- No commit, push, merge, or deploy.  
- No implementation started.

**Artifact path:** `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md`

---

## Appendix A — Architecture one-liner

Tenant-scoped, versioned Content Management is the sole business-fact source after cutover; runtime loads one published version, enforces Restricted before handoff, serves FAQ exact-then-semantic without Interpreter on hits, then Interpreter + structured facts + semantic chunks + existing large AI + deterministic validator, with constrained non-live shadow evaluation and atomic content/index rollback.

## Appendix B — Phase list

0 Snapshot → 1 Schemas/IA → 2 Draft UI (**Publish disabled**) → 3 FAQ+structured → 4 Migration → 5 Constrained shadow index → 6 Gated packet+validator → 7 Full gates → 8 Atomic cutover + SoT final audit.

---

*Revised plan. Stopped for owner/supervisor review. Do not build until explicit approval.*
