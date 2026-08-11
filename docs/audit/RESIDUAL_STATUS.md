# Residual status (continuous run)

**Branch:** `chore/project-cleanup-reorg`  
**Rule:** Keep working until residual is empty, then Done. No auto merge/deploy to production.

## Progress so far (not Done)

- W00: full tracked inventory (row count matched `git ls-files`) + LOC gate
- W01: blocked hyphenated `/api/test-*` + HTTP provider switch
- W02/W03: trusted client IP (`X-Real-IP`) + mobile/auth rate limits
- Admin-credit: cross-tenant only `platform_owner`; prod CORS HTTPS-only
- CSRF / webhook verify: `hmac.compare_digest`
- Proven deletes: `live_chat_archive/`, `cleanup_reports/`, `third_provider_adapter.py`, unwired `CreativeStudioScreen`, local `logs/*.out` + `.tmp_8010_*`
- LOC splits: `conversation_router`, `language_resolver`, `token_wallet_service`, `datetime_utils`, `sentiment_escalation_service`, `cm/faq_integration`, `auth_api`, `live_chat_api`, `user_service`, `local_qa_api`
- PII: sensitive `data/*.jsonl` / `content_violations.jsonl` reported in `docs/audit/PII_EXPOSURE_REPORT.md` (still tracked until explicit decision)

## Residual (must clear before Done)

- Hand-written files still over 500 lines: **~61** (top: `chat_response_service.py`, `LiveChat.jsx`, `text_handlers_respond.py`, `utils.py`, `SmartMessaging.jsx`, `live_chat_service.py`, …)
- Inventory `review_status`: mostly still `UNREVIEWED` (shell only)
- Creative Python API stack: `BLOCKED` (still wired in main/tests)
- Operator web SPA still present; parity matrix not built yet
- Monty still default WhatsApp provider; Meta Cloud cutover not finished on branch
- Redis distributed limiter: not production-activated (by design until deploy decision)

## Next continuous work

1. More DELETE_PROVEN (disabled pages after proof; creative unregister carefully)
2. Parity matrix + mobile gaps + landing-only web
3. Meta Cloud on branch + staging checklist
4. Split remaining god-files file-by-file with tests
5. Residual loop until empty → Done
