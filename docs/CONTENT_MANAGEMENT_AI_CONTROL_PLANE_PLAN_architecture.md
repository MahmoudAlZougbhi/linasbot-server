# Content Management AI Control Plane — architecture & IA (§3–§11)

> Part of [CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md](./CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md)

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
