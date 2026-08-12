# Phase 0B — File Review Log

Audit-only. Application source is not modified.

## Progress

| Metric | Value |
|--------|-------|
| Tracked files (`git ls-files`) | 1539 |
| Inventory rows | 1539 |
| COMPLETE | 25 |
| UNREVIEWED | 1514 |
| IN_REVIEW | 0 |
| Last batch | Batch 1 (seq 1–25) |
| Last audit commit | _(pending first commit)_ |

---

## Batch 1 — seq 1–25 (2026-08-12)

### Files opened and fully read

1. `.dockerignore`
2. `.env.example`
3. `.github/workflows/cm-linas-content-audit.yml`
4. `.github/workflows/cm-production-cutover.yml`
5. `.github/workflows/copilot-v2-flags-apply.yml`
6. `.github/workflows/dashboard-auth-secret-apply.yml`
7. `.github/workflows/deploy.yml`
8. `.github/workflows/instagram-login-secrets-apply.yml`
9. `.github/workflows/meta-app-a-login-config-apply.yml`
10. `.github/workflows/meta-app-a-scope-audit.yml`
11. `.github/workflows/meta-app-webhooks-reconcile.yml`
12. `.github/workflows/meta-comment-runtime-probe.yml`
13. `.github/workflows/meta-comment-webhooks-reconcile.yml`
14. `.github/workflows/meta-multi-app-secrets-apply.yml`
15. `.github/workflows/meta-page-subscription-subscribe.yml`
16. `.github/workflows/meta-social-atomic-cutover.yml`
17. `.github/workflows/meta-social-rollback-restore.yml`
18. `.github/workflows/meta-social-rollback-snapshot.yml`
19. `.github/workflows/meta-social-secrets-apply.yml`
20. `.github/workflows/meta-social-token-validate.yml`
21. `.github/workflows/meta-webhook-nginx-setup.yml`
22. `.github/workflows/model-routing-policy-apply.yml`
23. `.github/workflows/openai-api-key-apply.yml`
24. `.github/workflows/prod-preflight-readonly.yml`
25. `.github/workflows/quality-gates.yml`

### Findings summary

**Security**

- Seq 6, 8, 21, 23: secret/token apply workflows lack typed confirmation strings (unlike siblings).
- Seq 7: deploy uses older `appleboy/ssh-action@v1.0.3`; `/tmp` data backup window during `git reset --hard`.
- Seq 2: public WhatsApp E.164 contact numbers documented (expected); Monty/BOC placeholders still first-class.

**Correctness**

- Seq 10, 12: hardcode checkout from `fix/ig-fb-comments-capability-gates` (brittle).
- Seq 22: model-routing apply does not always refresh script from `origin/main` when file already exists.

**Performance**

- Seq 13: full `requirements.txt` install for thin reconcile script.
- Seq 25: heavy CI (expected).

**Legacy / product**

- Seq 2: mixed Meta Cloud + Monty template.
- Seq 24: probes still know `linaslaserbot-2.7.22` layout.
- Seq 25: still builds dashboard SPA.

**Deeper dependency tracing needed**

- All `scripts/prod_*` / `scripts/reconcile_*` / `scripts/validate_meta_*` / `scripts/manage_meta_*` / `deploy.sh` (canonical review when those sequence numbers are reached).

### Cumulative

COMPLETE **25 / 1539**
