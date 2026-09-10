# Customer Brain implementation log

Contract: LINAS-Cursor-Customer-Brain-Final-Prompt.md (2026-09-10).
Branch: `cleanup/ai-setup-runtime`.

## Secrets

- `VOYAGE_API_KEY` and `CUSTOMER_BRAIN_ENABLED=false` are GitHub Actions secrets
  (repo + `meta-social-cutover` environment).
- Local `.env` is gitignored. Never commit the key.
- Flag stays **off**. Production apply of env files is a separate HA transaction;
  this session did not mutate production servers.

## Entry points

Flag-off facades still return `engine_removed`. Flag-on DM/comment/follow-up
delegate into `services/customer_ai`. Follow-up now sends `followup_goal` with
empty customer text (no fake inbound).

## Implemented this session (code-complete / locally tested)

- Contracts, gates, history-50, greeting, exact FAQ, Voyage client, hybrid retrieve
- Products adapter (`updated_at` revision), hours cards, heuristic + optional OpenAI planner
- Evidence composer, coverage, amount grounding
- Comment 7-mode pipeline (manual/ignore = no planner)
- Request rule scopes authorable in CM schema + mobile editor
- Request persist + revision-bound confirmation helpers
- `escalate_to_human` via existing `set_human_takeover_status`
- Publish hook schedules Voyage index job (best-effort)
- Knowledge heading chunks / contextual groups
- Eval fixtures for four business types
- Alembic `20260910_cust_ai_search`

## Still missing vs the contract (honest)

- pgvector write/query against a live DB (migration exists; no production apply)
- OpenAI live planner/generate (fails closed without calling if key unused in tests)
- FAQ many-language job UX beyond existing `faq_integration*`
- Visual `voyage-multimodal-3.5` reading path (resource-by-ID only)
- Full 800–1500 eval suite and measured p50/p95 cost
- Firestore history wiring is implemented but not live-verified
- Do not enable `CUSTOMER_BRAIN_ENABLED` for real customers yet

## Tests

`python3.11 -m pytest tests/test_customer_ai_*.py tests/test_customer_reply_engine_removed.py tests/test_cm_comments_policy.py tests/test_cm_request_rules.py tests/test_alembic_single_head.py -q`
