# Content Management AI Control Plane — runtime, API, storage (§12–§13)

> Part of [CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md](./CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md)

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
