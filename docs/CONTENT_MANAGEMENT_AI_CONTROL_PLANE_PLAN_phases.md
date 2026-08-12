# Content Management AI Control Plane — phases, acceptance, decisions (§14–§20)

> Part of [CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md](./CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md)

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
