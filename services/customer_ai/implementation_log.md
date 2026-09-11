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

- Live pgvector write/query against a provisioned DB (migration exists; no production apply)
- OpenAI live planner/generate (fails closed without a key in tests)
- FAQ many-language job UX beyond existing `faq_integration*`
- Visual reading path (resource-by-ID only; multimodal stays disabled)
- Full 800–1500 eval suite and measured p50/p95 cost
- Firestore history / Live Chat takeover load is implemented for the in-memory flag,
  not live-verified against production Firestore
- Isolated lab is an owner portal page plus API; still capture-only
- Admin force-reindex exists; it does not bypass processing budgets or Voyage/pgvector readiness
- Generate turns that used FAQ evidence classify as `mixed_faq_ai`; semantic FAQ-only stays 0 units
- Comment AI turns load history-50 and prepend the parent comment; post caption is retrieve context
- Brain comments use the live Meta comment gate (Lite denied even while billing flags stay off)
- Brain WhatsApp / web / TikTok DMs and TikTok comments use the same live channel plan gates as connect/send paths
- Brain follow-up turns use the catalog follow-up lock after billing or Free enforcement flags
- Offline eval runner reports billing/gate contract cases without live provider spend
- Planner OpenAI calls journal a pending expense when a tenant id is present
- Pending provider expenses are journaled at generate/index/query/rerank call sites without inventing USD
- Do not enable `CUSTOMER_BRAIN_ENABLED` for real customers yet — entry-point repairs
  landed, but live channel/index/eval gates have not passed
- Leftover-credit and message holds now go through pending-settlement + bounded reconcile;
  age alone does not refund. Activation readiness is a report only.
- Durable Brain outbox stores the accepted envelope and recovers it after a crash without regenerating
- `apply_message_billing` now enqueues the accepted envelope; leftover/follow-up/omni send receipts mark sent or pending-settlement
- Outbox hydrates from disk and persists sent/pending state; reconciler reports accepted counts and does not auto-resend
- Safety-blocked inbound media is a policy stop; planner task text includes voice transcript and file extract
- Inbound STT journals pending transcription expense (no invented USD); TikTok confirmed send marks the Brain outbox
- Message units for DMs/comments now reserve at generate and settle only after confirmed send
- WhatsApp Cloud leftover capture moved to `finalize_ai_outbound_sent`; pre-send capture is gone
- Meta comments, Omni, TikTok, and Website Chat call `settle_after_send` after delivery
- Smart Follow-Up revalidate uses live customer-replied / opt-out / completed-sequence flags
- TikTok comment jobs call `settle_after_send` after publish, skip, or definitive fail (retryable in-flight does not release)
- Legacy WhatsApp voice journals pending inbound STT without inventing Whisper USD
- Meta public-only comment replies settle after confirmed Graph send; never-submitted and hard-fail paths release
- Delayed/Meta DM settle uses inbound mid + extra ids so a logical reply id cannot double-charge; never-submitted sends release the message hold
- Omni delivery and Website Chat completion settle the same Brain inbound id that generate reserved
- Website Chat fence/fail settles the reserved inbound hash after leftover release; it does not invent conversation or text
- TikTok DMs settle the bound Brain inbound id after send, skip, or never-submitted fail
- WhatsApp Cloud fail/empty/limit/suppressed paths settle the reserved inbound mid; queued and ambiguous sends keep the hold until finalize or reconcile
- Queued WhatsApp delivery releases never-submitted holds from the intent idempotency mid; confirmed-send capture failures stay pending-settlement
- Legacy photo analysis journals pending visual spend without inventing Vision USD
- Smart Follow-Up settles the canonical idempotency key plus the minted `sfu:{conversation}:{goal}` fallback; generate failures release
- Leftover recon discovers tenants already present on in-memory settlement/index rows without guessing ids
- Website Chat follow-up delivery settles the Brain follow-up hold after the visitor outbox is durable; leftover pending stays the only reconcile path
- Instagram/Facebook history-50 uses the conversation store when Firestore is empty; static and AI comments share one fallback thread
- Omnichannel generate skip/empty/takeover/exception and comment-no-public paths release the reserved Brain inbound id
- Generate-after-reserve failures release the turn hold; `manual` comment mode is no_reply / 0 units
- Isolated lab capture-only turns settle the reserved operation as unsent
- Meta social finalize_delivery releases the Brain hold on never-submitted fail; reconcile requeue of an unfinished generate does the same
- Empty generate and delayed/exception `on_ai_failed` now release the Brain inbound hold, not leftover credits only
- Smart Follow-Up claim-lost / missing-job after a confirmed send now settles the Brain hold, not leftover credits only
- Meta social processor is under the 500-line cap; never-submitted fail still goes through finalize_social_turn → finalize_delivery
- Account delete stays a privacy safety write so it still works after the daily-edit cap
- Comment webhook repair, Instagram Login webhook retry, Meta rollback, and Website Chat key rotate stay safety writes after the daily-edit cap
- Tenant workspace leftover-zero is leftover credits, not Messages; billing-on depletion does not sell leftover IAP as Add messages
- Leftover IAP sheet does not title leftover packs as Add messages after message billing is on
- Chat and Dashboard leftover IAP cannot open after message billing is on; Current Plan included/month stays pending when the API omits included messages
- Ambiguous WhatsApp send keeps the hold as unresolved without leftover capture; SFU/TikTok pending rows use leftover policy only when a leftover reservation exists
- Photo Brain turns use wrap_tracked_send so settle_after_outbound sees delivery evidence before capture
- Brain outbox persists accepted envelopes on `customer_ai_outbox` (same `20260910_msg_billing` revision) and recovers the same text after a memory clear
- mark_sent / enqueue load a missing memory row from SQL so a restart cannot mint a second envelope
- Disk envelopes are promoted into SQL only when the outbox id is absent; official Alembic head stays `20260910_req_web_chat`
- settle_after_send(accepted=False) marks the stored envelope failed; enqueue of the same id still returns the original text
- SQL outbox upsert does not overwrite envelope text on conflict
- leftover_policy_for / get_pending read pending-settlement SQL after restart so a leftover pin survives a memory clear
- leftover reserve now stores pin aliases on settlement `candidate_ids` so conversation/event aliases survive a memory clear
- Settlement upserts union candidate aliases; leftover WhatsApp reserve and capture-failure keep conversation pins
- Outbound settle without delivery evidence no longer captures leftover credits or message units
- Conversation store persists greeted/pending/history on SQL when the billing tables exist; disk rows promote only when that store key is missing
- Message catalog drafts load from SQL after a memory clear; unpublished overlays do not become live checkout
- Leftover-credit index open/close survives another worker via SQL; `credit_ledger_service.reserve()` is still not the index hook
- Index/FAQ processing attempt and concurrency budgets persist on SQL; crashed jobs older than one hour stop counting toward the tenant cap
- Leftover IAP sheet uses leftover-credit no-expire copy; purchased-message no-expire stays for unpublished message packs
- Leftover-credit SQL scan uses the same leftover-op matcher as the jsonl scan; captured leftover rows are not re-seeded as open holds
- Conversation store reads SQL on each persist-enabled load; save keeps SQL history when this process's memory is stale
- Known conversation tenants union memory and SQL; leftover-credit scan still does not invent tenants from conversations
- Leftover `policy_for_operation` uses SQL when persist is on and does not keep a released hold as leftover from stale memory
- `leftover_policy_for` unpins process-local leftover pins after SQL reports no reserved/pending-settlement hold
- Outbox `_get` prefers SQL so `mark_failed` cannot overwrite a sent envelope from stale accepted memory
- Leftover-credit index `_get` prefers SQL; known leftover-index tenants union memory and SQL without inventing ids
- Daily-edit reserve/commit/release/status skip SQL when `customer_ai_daily_edits` or policy tables are missing
- Known processing and settlement tenants union memory + SQL for cost dashboards
- `reserve_generative` records a message hold with conversation/event aliases and consults leftover pins on conversation id
- Failed generate releases both the ledger reservation and the pending-settlement hold
- Leftover-credit known tenants include Postgres reserve-row tenants without inventing conversation ids
- Cost dashboards union memory + SQL ledger tenants/reservations and expense events
- WhatsApp Cloud settle/release uses intent mid + conversation extras when the provider inbound mid is missing
- TikTok/Meta comment settle extras include the comment thread id so send can find the generate hold
- Ledger snapshot remaining includes memory-only lots after SQL is up
- Message `settle()` falls back to the memory reservation when SQL raises KeyError, so send-settle does not mint a second unit
- Reconcile `list_pending`, `list_stale_reserved`, and leftover `list_stale_open` union memory + SQL without inventing tenant ids
- Pending, leftover-open, outbox, and processing-budget dashboard counts add memory-only rows after SQL counts
- Daily-edit status/reserve add memory-only slots after SQL is up; release/commit still clear the process-local id
- Message reserve falls back to a memory lot on SQL insufficient; included expiry and purchased refunds also zero process-local lots
- Outbox recover and known tenants union memory + SQL; `reverse()` falls back to the memory hold on SQL KeyError
- Delayed/legacy send-settle extras include the Brain conversation id so generate aliases match
- Leftover-credit seed does not reopen a jsonl reserve after the Postgres ledger reports no open hold
- Leftover-index close upserts a closed SQL row; open counts skip memory copies of SQL-known ids
- Leftover scan closes a reserve when capture/release uses the original request id
- `get_pending` matches reservation, operation, and candidate aliases including conversation id
- Delayed/legacy leftover capture finishes through `complete_leftover_capture` so leftover policy cannot linger after a successful capture
- Leftover-index `record_open` reopens settled/released rows when seed still sees a reserved leftover; it does not reopen pending-settlement
- Website Chat leftover reserve/capture/release share leftover hold + pin finish helpers; no second leftover reserve
- Leftover reconcile retry unpins leftover policy after a successful capture
- Conversation store does not revive process-local greeted/pending/history when SQL is ready and has no row
- Outbox recover_unsent / recover_pending_settlement and pending list_pending exclude SQL-known ids from memory extras
- Leftover-index `_get` does not revive a reserved memory row when SQL is ready and has no row; record_open persists that process-local hold
- Leftover-index hydrate does not load a disk reserved row when SQL already has that reservation id
- Outbox and pending-settlement hydrate skip disk accepted/reserved files when SQL already has that id
- Website Chat leftover reserve pins the conversation id; send-settle extras include that conversation id
- Processing end_job does not call pg_end_latest_job when this process has no local job id
- settle_after_send does not mint a message unit when leftover policy already owns the turn
- Smart Follow-Up leftover reserve pins conversation and minted Brain ids; cutover keeps an existing leftover hold
- Live DM turn path executes `resource_request` via authorized `send_resource` receipts; photo/link asks no longer fake booking confirmation
- Product expand hydrates winners from the Products repository when CM sections have no products row
- Hybrid semantic query uses the WhatsApp/Postgres session (pgvector) when available, then falls back to memory
- Published cards skip archived/draft/withdrawn knowledge and inactive catalog rows
- Follow-up compose injects GOAL_PROMPTS instruction prose (not only the goal key)
- Adapter `detected_language` / `response_language` land on the turn and steer generate
- Knowledge semantic winners expand the indexed chunk text when shorter than the full article
- Knowledge/care cards include attachment caption/excerpt blocks at index time
- Post-retrieve validate drops empty or non-visible section winners
- Testing readiness: `testing_ready` on activation report; lab turns skip message reserve but keep pending expenses; semantic FAQ stamps tenant_id; Owner Costs shows pending/tenant tables; Owner Lab surfaces brain_disabled; shell shows readiness banner


## Rollout / rollback

- Keep `CUSTOMER_BRAIN_ENABLED=false`. Flag-off path remains `engine_removed`.
- Rollback is disabled/manual/handoff — do not revive deleted Luna/Terra.
- Search pointer supports `rollback_version` when a ready index exists.
- Missing Voyage or pgvector is a typed readiness miss, not fake semantic success.

## Tests

`python3.11 -m pytest tests/test_customer_ai_*.py tests/test_customer_reply_engine_removed.py tests/test_cm_comments_policy.py tests/test_cm_request_rules.py tests/test_alembic_single_head.py -q`
