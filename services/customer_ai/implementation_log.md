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

## Wiring this continuation

- Hours evidence hydrates from branch weekly schedules and timezone
- Semantic FAQ after exact miss; visual path recorded, multimodal stays disabled
- Comment/DM senders consume `public_comment_text` / `private_dm_text`; TikTok/omni skip unsent DM claims
- WhatsApp Cloud conversations fall back to PG message history when Firestore is empty
- Lab classify + offline fixture runner; activation flags stay off
- Session greetings prepend on generated DMs as well as FAQ; comments and follow-up stay ungreatable
- Greeting language follows the inbound message; a session does not greet twice after history already contains the greeting
- Restricted topics send the published refuse template (or the default language template)
- Pipeline exceptions release any held message reservation; follow-up abort paths settle pending send holds
- ConversationState and pending request proposals persist per conversation; the next inbound yes confirms the stored revision
- Website Chat conversations fall back to the visitor message store when Firestore is empty
- Live human-control rechecks Redis takeover every turn and clears a stale stored handoff after release
- A stored yes persists the request when the requests DB is up; missing request setup is not a retry loop
- Request receipts use serialized `request_id` (not a missing `id` field)
- TikTok DMs pass conversation/message ids into the Brain; TikTok PG history-50 loads when Firestore is empty
- Meta / omnichannel / TikTok comments pass comment id, post id, caption, and parent text into the Brain
- Conversation store keeps a rolling latest-50 when Firestore / channel stores miss; comment threads never persist private DMs
- Instagram/Facebook DMs pass the inbound mid so request confirm can bind a revision
- WhatsApp Cloud and Website Chat pass the inbound mid so yes-to-submit binds on those channels too
- Static comment replies stay on the shared post history without private DM text
- Omnichannel WhatsApp/Instagram generate passes the same conversation id so pending confirm and history stay attached
- Live-control state is persisted even when the turn stops at a gate
- Offline contract cases include revision-bound confirmation
- Website Chat yes-to-submit persists `web_chat`; TikTok DMs are not remapped to Instagram
- Website Chat follow-up delivery uses the message ledger when billing is on instead of failing `reservation_required`
- WhatsApp Cloud credit reserve is skipped when message billing owns the generative gate
- Instagram/Facebook and Website Chat live turns skip leftover-credit reserve the same way
- Owner follow-up preview does not hold a customer message reservation
- Confirmed requests store the published CM version, not the pending draft revision
- Omnichannel WhatsApp/web generate no longer forwards a credit reservation when the message ledger owns the turn
- Isolated lab accepts channel, inbound id, and history so confirmation/source checks can be exercised
- Request proposals attach published graph field keys when the requests DB is up; values stay empty
- Request-rule save is one AI Setup edit: draft + graph publish share a daily-edit slot
- Yes-to-submit re-attaches published graph field keys before Requests create
- Instagram/Facebook delayed/combine turns reuse conversation_id_from_user_data (existing thread or social user id)
- Comment Brain turns bind conversation_id_for_brain, then the existing comment/post id
- Lab capture JSON echoes conversation, channel, inbound id, receipts, and pending actions
- Leftover-credit and message reservations pin their billing policy; a flag flip mid-job cannot debit both systems
- Successful-send capture failures stay reserved and enter pending-settlement; unused pre-send holds still release
- Comment classify uses mode + delivery extras: ignore/static/FAQ-only = 0, AI comment/DM/both and mixed FAQ+AI = 1

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

- Live pgvector write/query against a provisioned DB (migration exists; production apply + force-reindex + tenant pointer ready still required — see runbook)
- P0 cutover honesty: Brain OFF never restores Luna/Terra; emergency legacy is fail-closed (`emergency_legacy_unavailable`); tenant allowlist + testing_ready gate; published retrieve fails closed on missing Voyage/pgvector/pointer; handler must not mask empty Brain stops as validation-failed success
- OpenAI live planner/generate (fails closed without a key in tests)
- FAQ many-language job UX beyond existing `faq_integration*`
- Visual reading path (resource-by-id only; multimodal stays disabled — honest UX, no fake vision)
- Full 800–1500 eval suite and measured p50/p95 cost
- Firestore history / Live Chat takeover load is implemented for the in-memory flag,
  not live-verified against production Firestore
- Isolated lab is an owner portal page plus API; still capture-only
- Admin force-reindex exists; it does not bypass processing budgets or Voyage/pgvector readiness
- Do not enable `CUSTOMER_BRAIN_ENABLED` for real customers yet — entry-point repairs
  landed, but live channel/index/eval gates have not passed

## P1 remaining (5–15) — this pass

- Grounding: `grounding/facts.py` + `grounding/extract.py` check amounts, hours/times, phones, URLs, stock, booking vs evidence/receipts; export `ungrounded_claims` / `evidence_supports_text`
- Generate: strong ONLY-EVIDENCE system prompt; empty evidence → clarify; `repair_attempts=1` one repair then fail closed; accurate `used_evidence_ids`
- Lexical: Okapi BM25 over cards (`retrieve/lexical.py`); hybrid RRF unchanged
- Voyage-context-4: ENTITY-ONLY prod path; `KNOWLEDGE_*` reserved constants; removed from `spaces_snapshot` active keys
- Coverage: `coverage_ok(..., reply_text=, decision=)` fails answered-without-quality
- Visual disabled + image → localized `brain_template("visual_disabled")` clarify (never silent)
- Handoff/confirm localized via `templates.brain_template` + `response_language`
- Evals: `evals/golden_pack_linas.py`; runner latency/cost metric stubs; Owner Lab verification exercises (confirmation / readiness / retrieval) without live billing
- Semantic FAQ ambiguity → clarify (`faq_ambiguous`), no auto-answer

### How to run offline evals

```bash
python3.11 -c "from services.customer_ai.evals.runner import run_fixture_corpus; import json; print(json.dumps(run_fixture_corpus(), indent=2)[:2000])"
python3.11 -c "from services.customer_ai.evals.golden_pack_linas import run_golden_pack_linas; print(run_golden_pack_linas())"
python3.11 -m pytest tests/test_customer_ai_p1_grounding.py tests/test_customer_ai_lexical.py tests/test_customer_ai_retrieve.py -q
```

Owner Portal → Brain lab → **Run fixture evals** / **Run verification exercises** (lab tenant only).

## P2 cleanup (16–21) — done this pass

- Legacy `smart_retrieval_service` is DEAD (callables raise); Brain retrieve must not import it
- `customer_reply_v2.flags` stubs use Brain naming; search_metadata `luna_titles` is a dead-name shim over `title_fields`
- `TurnBudgets.repair_attempts=1` kept (honest). `generate/reply.py` must use it for one grounding repair — P1 owns that wiring; do not drop the budget to 0.
- CM publish returns `brain_index_status` (best-effort Voyage index); Owner force-reindex is the retry path
- Product questions fail closed with `product_index_stale` via `get_source_pointer_ready` + product_freshness
- Runbook + this log synced: rollback tag `rollback/pre-brain-2026-09-11` → `0f23bcf1`; not customer-ready

## Rollout / rollback

- Keep `CUSTOMER_BRAIN_ENABLED=false`. Flag-off path remains `engine_removed`.
- Rollback is redeploy tag `rollback/pre-brain-2026-09-11` (`0f23bcf1`) — do not revive deleted Luna/Terra on this branch.
- Search pointer supports `rollback_version` when a ready index exists.
- Missing Voyage or pgvector or tenant pointer is a typed readiness miss, not fake semantic success.
- `EMERGENCY_LEGACY_REPLY_ENABLED` default false; when true still fail-closed (`emergency_legacy_unavailable`).
- Use `assert_safe_brain_cutover()` before leaving Brain off in production.
- Stale products index is typed `product_index_stale`, not a silent wrong catalog answer.

## Tests

`python3.11 -m pytest tests/test_customer_ai_*.py tests/test_customer_reply_engine_removed.py tests/test_cm_comments_policy.py tests/test_cm_request_rules.py tests/test_alembic_single_head.py tests/test_model_routing_policy.py tests/test_customer_ai_p2_dead_paths.py -q`
