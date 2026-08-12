# OWNER STATUS COMPLETE — وضع المالك الكامل

**تاريخ التحديث / Updated:** 2026-08-12 (Phase 13 prep report)  
**جمهور / Audience:** Mahmoud (owner) — ملف واحد للصورة الكبيرة  
**Repo:** `/Users/alzoughbi/linasbot-server`

> اقرأ هيدا الملف أوّل شي. التفاصيل العميقة موجودة بروابط تحت — ما بدك تقرأ كل الملفات إلا إذا بدك dig deeper.

---

## 1. القرار الحالي / Current verdict

### **NOT_READY**

**ليش؟ / Why:** التطبيق (Phases 0–12) خلص ومجمّد مع CI أخضر على freeze. Phase 13 **تحضير جاهز** (`PHASE13_PRODUCTION_PREP_REPORT.md`) — بس لسا مسكّر على أكشن منك: **شراء Redis**، **موافقة migration**، **موافقة merge**. ما في merge/deploy/migration prod بدون موافقتك.

| ممنوع الآن / Do NOT | السبب |
|---------------------|--------|
| Merge PR #240 | يطلّع Quality Gates → Production Deploy على `main` |
| Deploy لـ production | Phase 13 مش جاهز |
| Apply `20260812_customer_requests` على prod | بدك backup + موافقة صريحة |
| Enable `LINASLASER_BOC_BOOKING_ENABLED` | BOC معزول OFF عمداً |

**Verdict Phase 21 (ledger):** `NOT_READY` — بسبب Phase 13 `BLOCKED_OWNER_ACTION` فقط، مش بسبب كود مكسور على الـ PR.

---

## 2. وين صرنا / Where we are

| Item | Value |
|------|--------|
| **Branch** | `chore/project-cleanup-reorg` |
| **HEAD tip (عند كتابة هيدا الملف)** | انظر `git rev-parse HEAD` (docs-only بعد Phase 13 report) |
| **Freeze SHA (Phase 12)** | `9757d014dbaca0bfc0b84e9a48133356fdc14958` |
| **Production SHA (live)** | `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26` (#238) |
| **Last green app baseline (قبل Requests)** | `72d1d439b589f4d111b0a4cc7cd61030ceaca677` |
| **PR** | [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240) → `main` |
| **PR state** | **OPEN**, mergeable |
| **CI على PR #240** | **أخضر / GREEN** على tip `768ebe7` — backend, frontend, mobile, secret-scan, deploy-readiness |
| **Freeze CI workflow** | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31602974014 |
| **Application freeze** | **DONE** عند `9757d01` |
| **Phase 13 prep report** | [`PHASE13_PRODUCTION_PREP_REPORT.md`](./PHASE13_PRODUCTION_PREP_REPORT.md) |
| **Redis** | **BLOCKED_PURCHASE** — لا يوجد Valkey لـ Linas؛ اقترح `linas-redis-prod` lon1 1GB ~$15/mo |
| **Meta** | **VERIFIED** على production (VERIFY_AND_PRESERVE) |
| **Production migration** | **READY_TO_APPLY** / **مش مطبّقة** (`20260812_customer_requests`) |
| **BOC booking** | **OFF** (default false) |

**ملاحظة tip vs freeze:** الـ tip ممكن يتقدّم بـ docs-only (مثل هيدا الملف + ledger). الـ freeze الرسمي للتطبيق هو `9757d01`. قبل الـ merge: أكّد إن CI لسا أخضر على الـ tip.

---

## 3. شو اتعمل بالزبط / What was done (Phases 0–12)

### Phase 0 — PR #240 CI
- Quality Gates + Security Checks ناجحة على رأس الـ PR.
- **ما في merge.**

### Phase 1 — Requests architecture + data model
- تصميم + state machine + security model تحت `docs/requests/`.
- Alembic additive: `alembic/versions/20260812_customer_requests.py` + models.
- **ما اتنفّذت على production.**

### Phase 2 — Backend domain + APIs
- `services/requests/*` + `modules/requests_api.py` من `main.py`.
- RBAC + path gate `/api/requests*` → permission `requests`.

### Phase 3 — AI Setup Requests & Appointments
- قسم CM `requests_appointments` (افتراضي: module OFF).
- Draft → preview → approve → publish عبر آلية CM الموجودة.
- Mobile AI Setup editor + hub registration.
- Capture ما بيشتغل إلا إذا الـ config منشور ومفعّل.

### Phase 4 — Customer AI request flow
- أداة AI آمنة `create_customer_request` (tenant/channel binding، confirmation، idempotency).
- Capture loop مربوط بالـ chat؛ تخطّي wa.me booking handoff لما capture فعّال.
- تعليق عام → دعوة DM فقط (بدون جمع PII).

### Phase 5 — Mobile Requests module
- Expo `features/requests/*` مقابل `/api/requests*`.
- Drawer **Requests / طلبات العملاء** + فلاتر + pagination + تفاصيل + final actions.
- i18n EN/AR/FR؛ typecheck + 103 اختبارات موبايل ناجحة وقت التسليم.

### Phase 6 — Chat with customer / manual mode (foundations)
- Pause AI عند أول رسالة operator مصرّح فيها؛ Resume AI يرجّع.
- Live Chat + routes Requests للـ manual chat/send/resume.
- ما في automatic human-queue escalation كامل بعد.

### Phase 7 — Channel delivery (outbox foundations)
- إرسال على القناة الأصلية فقط (IG/FB/WA Cloud).
- Outbox process + notify-retry؛ **ما في worker/cron مستمر بعد** (callable فقط).

### Phase 8 — BOC isolation
- `LINASLASER_BOC_BOOKING_ENABLED` default **false**؛ صفر HTTP لـ BOC لما OFF.
- جاهزية `/api/ready` بتعرض حالة الـ gate.
- **Production: مش مفعّل.**

### Phase 9 — Security / correctness tests
- `tests/test_requests_phase9_security.py` + حزم Requests/BOC/CM — عقود: tenant isolation، version conflict، transitions، PII، RBAC، outbox idempotency.

### Phase 10 — Independent review + PR closeout
- `docs/release/FINAL_INDEPENDENT_PR_REVIEW.md`.
- CI أخضر؛ **ما في merge.**

### Phase 11 — Full file-by-file reinspection
- Inventory 1397 ملف hand-written `fully_read=YES` / `COMPLETE`؛ 0 PENDING.
- 0 open CRITICAL/HIGH/MEDIUM في `FINAL_PROBLEMS_AND_FIXES.md`.
- ما في app source >500 LOC مخالف للقاعدة بعد الإصلاحات.
- إصلاحات عميقة: auth/BOC، live-chat، CM-AI، requests، mobile (SHAs تحت).

### Phase 12 — Final freeze
- Freeze candidate: **`9757d01`** (بعد ruff format على ملفات Phase 11).
- كل بوابات CI على الـ freeze: **pass**.
- قيود محفوظة: BOC OFF، لا SPA operator، لا Monty silent fallback، لا force-push، لا migration prod، لا merge.

---

## 4. شو لساته / What’s left

### Phase 13 — Production preparation — **prep DONE / owner gates remain**

تقرير كامل: [`PHASE13_PRODUCTION_PREP_REPORT.md`](./PHASE13_PRODUCTION_PREP_REPORT.md) · checklist: [`PHASE13_PRODUCTION_PREP_CHECKLIST.md`](./PHASE13_PRODUCTION_PREP_CHECKLIST.md)

1. **Redis — BLOCKED_PURCHASE:** ما في Valkey لـ Linas. وافق على شراء Managed Valkey `linas-redis-prod`، منطقة **lon1**، حجم **`db-s-1vcpu-1gb`**, ~**$15/mo**. (لا تستخدم `sportbook-redis-prod`.) بعد الإنشاء: ربط TLS/auth + smoke — بدون تفعيل يغيّر prod بدون موافقة.
2. **Meta — VERIFIED:** اتصال production مؤكّد بدون OTP للفحصات المنفّذة. **لا تفصل ولا تعيد بناء.** (اختياري: تصليح GHA secret للـ Token Validate فقط.)
3. **Migration — READY_TO_APPLY:** وافق على backup ثم تطبيق `20260812_customer_requests` على Postgres production.
4. **Merge approval** — بس بعد 1–3 والـ freeze أخضر → merge #240.

Rollback SHA الحالي: `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26`.

### بعد Phase 13 (لسا ما بلّشنا)

| Phase | Name | Status |
|------:|------|--------|
| 14 | Merge PR #240 + deploy | BLOCKED (يستنى Phase 13) |
| 15 | Live post-deploy smoke | PENDING |
| 16 | Mobile distribution (EAS) | PENDING (غالباً Apple/Google 2FA) |
| 17 | Final live revalidation | PENDING |
| 20 | Final deliverables `docs/release/*` | IN_PROGRESS (هيدا الملف جزء منه) |
| 21 | Verdict | **NOT_READY** لحد ما Phase 13 يتحلّ |

---

## 5. SHAs المهمة / Important SHAs

| Label | SHA (short) | Full / notes |
|-------|-------------|--------------|
| Baseline (آخر app أخضر قبل Requests) | `72d1d43` | `72d1d439b589f4d111b0a4cc7cd61030ceaca677` |
| Phase 11 deep-fix batch | `9c300ed` … `067c6fc` | auth → live-chat → cm-ai → requests → mobile |
| Phase 11 docs artifacts | `dfb5aea` | reinspection reports |
| **Freeze (Phase 12)** | **`9757d01`** | `9757d014dbaca0bfc0b84e9a48133356fdc14958` — ruff format + CI green |
| Ledger stop (Phase 12 DONE) | `768ebe7` | `768ebe7b93c1e4e770e50fab6faf1f9dcc1f63b0` — docs |
| Tip عند كتابة الملف | انظر `git rev-parse HEAD` | قد يتقدّم بـ docs-only بعد هيدا الـ commit |

**آخر 15 commit (مرجع سريع):**

```text
768ebe7 docs(release): mark Phase 12 freeze DONE; stop on Phase 13 owner
9757d01 style: ruff format Phase 11 freeze candidates
dfb5aea docs(release): complete Phase 11 file-by-file reinspection artifacts
067c6fc fix(mobile): Phase 11 Requests reinspection
adb0a5c fix(requests): Phase 11 reinspection findings
5ad2e5a fix(cm-ai): Phase 11 capture/handoff reinspection
10e4912 fix(live-chat): Phase 11 manual-mode reinspection
9c300ed fix(security): Phase 11 auth/BOC/ready reinspection
b2333e0 docs(release): Phase 10 independent review and honest NOT_READY stop
be8d82d fix(ci): correct protected route inventory count after Requests APIs
fb81b55 fix(ci): update CM progress and route inventory for Requests
1244612 fix(ci): clear mypy on manual resume and ruff-format Requests tests
c3aba0c fix(ci): sort BOC gate imports for Ruff I001
39cc83d docs(release): pin Phase 9 ending SHA after security tests
e8d6e65 test(requests): expand security and correctness coverage
```

---

## 6. روابط / Links (deep docs)

| وثيقة / Doc | رابط / Path |
|-------------|-------------|
| **هيدا الملف (الصورة الكبيرة)** | `docs/release/OWNER_STATUS_COMPLETE.md` |
| Execution ledger (كل الـ phases) | [`docs/release/FULL_COMPLETION_EXECUTION_LEDGER.md`](./FULL_COMPLETION_EXECUTION_LEDGER.md) |
| Phase 13 prep report | [`docs/release/PHASE13_PRODUCTION_PREP_REPORT.md`](./PHASE13_PRODUCTION_PREP_REPORT.md) |
| Phase 13 checklist (owner block) | [`docs/release/PHASE13_PRODUCTION_PREP_CHECKLIST.md`](./PHASE13_PRODUCTION_PREP_CHECKLIST.md) |
| Phase 12 freeze verification | [`docs/release/FINAL_FREEZE_VERIFICATION.md`](./FINAL_FREEZE_VERIFICATION.md) |
| Independent PR review | [`docs/release/FINAL_INDEPENDENT_PR_REVIEW.md`](./FINAL_INDEPENDENT_PR_REVIEW.md) |
| Problems & fixes (0 open C/H/M) | [`docs/release/FINAL_PROBLEMS_AND_FIXES.md`](./FINAL_PROBLEMS_AND_FIXES.md) |
| File-by-file review log | [`docs/release/FINAL_FILE_BY_FILE_REVIEW_LOG.md`](./FINAL_FILE_BY_FILE_REVIEW_LOG.md) |
| File inventory CSV | [`docs/release/FINAL_FILE_BY_FILE_INVENTORY.csv`](./FINAL_FILE_BY_FILE_INVENTORY.csv) |
| **PR #240** | https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240 |
| Freeze CI run | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31602974014 |
| Requests design | `docs/requests/REQUESTS_SYSTEM_DESIGN.md` |
| BOC future note | `docs/requests/BOC_FUTURE_INTEGRATION.md` |
| Redis rate-limit notes | `docs/RATE_LIMIT_REDIS.md` |
| Predeploy env checklist | `docs/PREDEPLOY_ENV_CHECKLIST.md` |

---

## 7. شو بدك تعمل هلق / What you should do now (Mahmoud only)

1. **اقرأ** [`PHASE13_PRODUCTION_PREP_REPORT.md`](./PHASE13_PRODUCTION_PREP_REPORT.md).
2. **وافق على شراء Redis:** DO Managed Valkey `linas-redis-prod` / **lon1** / `db-s-1vcpu-1gb` / ~**$15/mo** (Databases → Create → Valkey).
3. **Meta:** ما في OTP مطلوب للفحصات المنفّذة — محفوظ VERIFY_AND_PRESERVE.
4. **Backup + موافقة migration** ثم تطبيق `20260812_customer_requests`.
5. **بعد 2–4:** موافقة **merge PR #240**.
6. **لا تعمل:** merge قبل Redis+migration؛ ولا تفعّل BOC؛ ولا force-push.

---

**آخر سطر:** Phase 13 prep مكتمل تقنياً — **الإنتاج مش جاهز** لحد ما Mahmoud يوافق على شراء Redis + migration + merge.
