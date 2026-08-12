> Part of [CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md](./CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md)

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
