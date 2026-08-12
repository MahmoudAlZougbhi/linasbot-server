# Codebase Concerns

**Analysis Date:** 2026-01-19

## Tech Debt

**Large monolithic files:**
- Issue: Several files are very large and handle too many responsibilities
- Files:
  - `services/chat_response_service.py` (62KB) - AI response logic
  - `modules/webhook_handlers.py` (45KB) - Webhook processing
  - `modules/smart_messaging_api.py` (40KB) - Bulk messaging
  - `modules/dashboard_api.py` (36KB) - Dashboard endpoints
  - `dashboard/src/pages/LiveChat.js` (73KB) - Live chat UI
  - `dashboard/src/pages/SmartMessaging.js` (64KB) - Messaging UI
  - `utils/utils.py` (71KB) - Utility functions
- Why: Rapid development without refactoring
- Impact: Hard to navigate, test, and maintain
- Fix approach: Extract into smaller, focused modules

**Backup files in codebase:**
- Issue: Multiple *_backup.py and *_TEMP.py files committed
- Files:
  - `handlers/text_handlers_backup.py`
  - `handlers/text_handlers_respond_TEMP.py`
  - `services/chat_response_service_backup.py` (if exists)
  - `services/analytics_service_old_backup.py`
  - `modules/analytics_api_old_backup.py`
- Why: Manual version control during development
- Impact: Confusion about which file is active, increased repo size
- Fix approach: Remove backup files, use git history instead

**In-memory state management:**
- Issue: User state stored in Python defaultdicts, lost on restart
- Files: `config.py` (user_context, user_gender, user_booking_state, etc.)
- Why: Quick implementation, works for single-server deployment
- Impact: State lost on server restart, can't scale horizontally
- Fix approach: Move state to Redis or Firestore with TTL

**Third-party adapter TODOs:**
- Issue: Template adapter has many unimplemented TODOs
- File: `services/whatsapp_adapters/third_provider_adapter.py`
- TODOs found:
  - `TODO: Implement based on your provider's API documentation`
  - `TODO: Adjust payload structure based on provider requirements`
  - Multiple similar TODOs for different methods
- Why: Template file for adding new providers
- Impact: None if not used, but confusing if copied without completion
- Fix approach: Document as template-only or complete implementations

## Known Bugs

**None explicitly documented:**
- No bug tracking in code comments detected
- Recommend: Add issue tracking system or BUGS.md

## Security Considerations

**Credentials in .env.example:**
- Risk: `.env.example` contains what appear to be real API keys
- File: `.env.example` (MONTYMOBILE_API_KEY value visible)
- Current mitigation: File marked as example
- Recommendations: Replace with placeholder values like `your-api-key-here`

**No webhook signature validation visible:**
- Risk: Webhook endpoints may not verify request authenticity
- Files: `modules/webhook_handlers.py`
- Current mitigation: Provider-specific handling may exist
- Recommendations: Add explicit signature validation for each provider

**Admin role check location unknown:**
- Risk: Dashboard permissions implemented client-side only
- Files: `dashboard/src/contexts/PermissionsContext.js`, `dashboard/src/components/Auth/ProtectedRoute.js`
- Current mitigation: Basic auth context
- Recommendations: Add server-side permission verification for sensitive endpoints

## Performance Bottlenecks

**Large file sizes slow imports:**
- Problem: Importing large modules takes time at startup
- Files: `services/chat_response_service.py` (62KB), `utils/utils.py` (71KB)
- Measurement: Not measured, but noticeable on cold start
- Cause: Everything in single files
- Improvement path: Split into smaller modules, lazy loading

**In-memory conversation history growth:**
- Problem: User context stored in memory grows unbounded
- File: `config.py` (`user_context = defaultdict(deque)`)
- Measurement: Memory grows with each conversation
- Cause: No automatic cleanup, MAX_CONTEXT_MESSAGES only limits per-user
- Improvement path: Add TTL-based cleanup, move to persistent store

## Fragile Areas

**WhatsApp adapter switching:**
- File: `services/whatsapp_adapters/whatsapp_factory.py`
- Why fragile: Singleton pattern with runtime provider switching
- Common failures: State inconsistency when switching providers
- Safe modification: Don't modify during active conversations
- Test coverage: Manual testing only

**Event routing in webhook handlers:**
- Files: `modules/webhook_handlers.py`, `modules/event_handlers.py`
- Why fragile: Large switch/if-else chains for message type routing
- Common failures: New message types not handled
- Safe modification: Add new handlers carefully, test all paths
- Test coverage: No automated tests

## Scaling Limits

**Single-server in-memory state:**
- Current capacity: Single server instance
- Limit: Cannot scale horizontally
- Symptoms at limit: State lost if distributed
- Scaling path: Move state to Redis/Firestore, use stateless design

**Firestore usage:**
- Current capacity: Firebase free tier or paid plan
- Limit: Depends on plan, free tier has read/write limits
- Symptoms at limit: 429 errors, writes fail
- Scaling path: Monitor usage, upgrade plan as needed

## Dependencies at Risk

**react-hot-toast:**
- Risk: Noted in template as potentially unmaintained
- Impact: Toast notifications
- Migration plan: Switch to sonner if issues arise

**pydub for audio:**
- Risk: Requires FFMPEG system dependency
- Impact: Voice message processing fails without FFMPEG
- Mitigation: Graceful degradation when pydub unavailable (`modules/core.py`)

## Missing Critical Features

**No automated testing:**
- Problem: No pytest or Jest test suites
- Current workaround: Manual testing via scripts and dashboard
- Blocks: Safe refactoring, CI/CD pipeline
- Implementation complexity: Medium (add pytest + fixtures)

**No CI/CD pipeline:**
- Problem: No automated deployment or testing
- Current workaround: Manual deployment via `deploy.sh`
- Blocks: Reliable deployments, test automation
- Implementation complexity: Low (add GitHub Actions)

**No error tracking service:**
- Problem: Errors only logged to console/files
- Current workaround: Manual log review
- Blocks: Proactive error detection
- Implementation complexity: Low (add Sentry)

## Test Coverage Gaps

**No Python unit tests:**
- What's not tested: All backend Python code
- Risk: Regressions in chat logic, handlers, services
- Priority: High
- Difficulty: Medium (need to add pytest, create fixtures)

**No React component tests:**
- What's not tested: Dashboard React components
- Risk: UI regressions
- Priority: Medium
- Difficulty: Low (Jest already available via CRA)

**No integration tests:**
- What's not tested: Full webhook to response flow
- Risk: Breaking changes not caught
- Priority: High
- Difficulty: Medium (need test harness for webhooks)

---

*Concerns audit: 2026-01-19*
*Update as issues are fixed or new ones discovered*
