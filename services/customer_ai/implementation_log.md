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
delegate into `services/customer_ai`. Follow-up sends `followup_goal` with
empty customer text (no fake inbound). Follow-up worker rechecks takeover /
rule / window immediately before send.

## Implemented (code-complete / locally tested)

- Contracts, gates, history-50, greeting, exact FAQ, Voyage client, hybrid retrieve
- Products adapter (`updated_at` revision), hours cards, heuristic + optional OpenAI planner
- Evidence composer, coverage, amount grounding
- Comment 7-mode pipeline (manual/ignore = no planner)
- Public comment privacy + DM-claim wording depends on private-send receipt
- Request rule scopes authorable in CM schema + mobile editor
- Request persist + revision-bound confirmation; material field change invalidates yes
- Draft update/cancel actions; `send_resource` by authorized ID (no invented URLs)
- `escalate_to_human` via existing `set_human_takeover_status`
- Restricted-topic gate before FAQ/planner; live human-control from takeover map
- Publish hook schedules Voyage index job (best-effort)
- pgvector store write/query + pointer activate/rollback; missing extension = `index_not_ready`
- Product create/update/delete marks the products index stale without CM republish
- Knowledge heading chunks / contextual groups
- Visual `voyage-multimodal-3.5` stays typed `disabled` / `resource_by_id` for product photos
- Rerank-2.5 after hybrid fuse (skipped for exact lookups; failure keeps fused order)
- Outbound test adapter saves envelopes without channel send
- FAQ exact path refuses stale prices/hours unless current sources agree
- Eval fixtures for four business types
- Alembic `20260910_cust_ai_search`

## Still missing vs the contract (honest)

- Live pgvector write/query against a provisioned DB (migration exists; no production apply)
- OpenAI live planner/generate (fails closed without a key in tests)
- FAQ many-language job UX beyond existing `faq_integration*`
- Visual reading path (resource-by-ID only; multimodal stays disabled)
- Full 800–1500 eval suite and measured p50/p95 cost
- Firestore history / Live Chat takeover load is implemented for the in-memory flag,
  not live-verified against production Firestore
- Do not enable `CUSTOMER_BRAIN_ENABLED` for real customers yet

## Rollout / rollback

- Keep `CUSTOMER_BRAIN_ENABLED=false`. Flag-off path remains `engine_removed`.
- Rollback is disabled/manual/handoff — do not revive deleted Luna/Terra.
- Search pointer supports `rollback_version` when a ready index exists.
- Missing Voyage or pgvector is a typed readiness miss, not fake semantic success.

## Tests

`python3.11 -m pytest tests/test_customer_ai_*.py tests/test_customer_reply_engine_removed.py tests/test_cm_comments_policy.py tests/test_cm_request_rules.py tests/test_alembic_single_head.py -q`
