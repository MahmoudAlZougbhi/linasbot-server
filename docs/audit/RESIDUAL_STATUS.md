# Residual status (continuous run)

**Branch:** `chore/project-cleanup-reorg`  
**HEAD:** `747bd31`  
**Tracked files:** 1281

## Done so far
- W00 inventory (1283→now fewer after deletes)
- W01 lab API hyphen block + provider switch refuse
- W02/W03 trusted IP + auth rate limits
- W05 admin-credit platform_owner + prod CORS HTTPS
- CSRF/compare_digest
- W09 delete live_chat_archive + cleanup_reports
- Delete third_provider_adapter + unwired CreativeStudioScreen (creative Python stack BLOCKED)
- First LOC split: conversation_router

## Residual (not Done yet)
- Hand-written files still >500: ~64+ (gate still FAIL)
- Inventory rows still mostly UNREVIEWED (shell provisional)
- Creative API stack still present (BLOCKED)
- Operator web SPA still present (parity matrix not built yet)
- Monty still default WA provider (Cloud cutover not done on branch)
- Redis prod limiter not activated (branch may add later; prod flag off)
- Baseline wave1/webhook_dedupe env failures from W00 still to clear in-context

## Next continuous work
- Keep deleting DELETE_PROVEN candidates
- Continue security items (uploads, webhook idempotency, Redis on branch)
- Build parity matrix then landing-only web
- Split remaining >500 file-by-file with tests
- Residual loop until empty → then Done (no auto prod deploy)
