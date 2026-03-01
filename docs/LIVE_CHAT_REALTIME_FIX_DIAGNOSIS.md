# Live Chat Realtime + Consistency Fix – Diagnosis & Validation

## Root Causes (with references)

### 1. **utils.py: `conversations_collection_for_user` used before definition**

**Location:** `utils/utils.py` – `save_conversation_message_to_firestore()`

**Issue:** In the `if not phone_number` block (lines 307–351), `conversations_collection_for_user` and `user_doc_ref` were used before being defined (they were set at lines 355–357). This caused `NameError` when resolving phone from an existing conversation.

**Fix:** Resolve `canonical_user_id`, `user_doc_ref`, and `conversations_collection_for_user` first (using `phone_number=None` when needed), then run the phone-resolution logic, and re-resolve canonical if phone was resolved.

---

### 2. **No stable `message_id` – frontend relied on timestamp + content**

**Locations:**
- `utils/utils.py` – `_build_message_data()`, `_message_to_dashboard_format()`
- `services/live_chat_service.py` – `get_conversation_details()`
- `services/live_chat_contracts.py` – `normalize_message()`, `dedupe_messages()`
- `dashboard/src/hooks/useLiveChatSSE.js` – new_message dedupe
- `dashboard/src/pages/LiveChat.js` – React `key`

**Issue:** Messages lacked a stable unique `message_id`. Deduplication and React keys used `timestamp` and `content`, which can collide for rapid messages ("hi", "kifak", "sho", "3amel") and cause duplicates or lost messages.

**Fix:** Backend assigns `message_id` for every message (webhook `source_message_id` when available, else `msg_{timestamp}_{uuid}`). SSE and API responses include `message_id`. Frontend dedupes and keys by `message_id`.

---

### 3. **SSE robustness – headers and reconnect**

**Locations:**
- `modules/live_chat_api.py` – SSE endpoint headers
- `dashboard/src/hooks/useLiveChatSSE.js` – reconnect logic

**Issue:** Missing `Pragma: no-cache`; reconnect delay was `5000 * attempt`, which could grow too large. Limited instrumentation.

**Fix:** Added `Pragma: no-cache`, better reconnect schedule (min 1s, cap ~10s), and logging in dev for connect/error/reconnect.

---

### 4. **Load more – merge by `message_id`, correct ordering**

**Locations:**
- `dashboard/src/pages/LiveChat.js` – `loadMoreMessages()`

**Issue:** Load-more merge did not dedupe by `message_id`, and used `history[0]` without ensuring correct ordering for the “before” cursor.

**Fix:** Sort by timestamp before picking `beforeTs`; merge older messages and dedupe by `message_id`; keep deterministic sort by timestamp.

---

### 5. **Broadcast and save instrumentation**

**Locations:**
- `utils/utils.py` – save + broadcast
- `modules/live_chat_api.py` – broadcast, client connect

**Issue:** Little visibility into webhook → save → broadcast → SSE client count.

**Fix:** Added `_log.info` for save+broadcast and SSE broadcast; SSE client connect and broadcast events are logged.

---

## Validation Plan

### a) Send 10 rapid messages – all appear in correct order

1. From WhatsApp, send in quick succession: `hi`, `kifak`, `sho`, `3amel`, `marhaba`, `test1`, `test2`, `test3`, `test4`, `test5`.
2. Open Live Chat and select that conversation.
3. **Expected:** All 10 messages appear in the correct order.
4. Refresh the page.
5. **Expected:** Same 10 messages, same order; none disappear.

### b) Refresh does not change or remove messages

1. View a conversation with multiple messages.
2. Note the message count and order.
3. Hard refresh (Cmd+Shift+R / Ctrl+Shift+R).
4. **Expected:** Same messages, same count, same order.

### c) Load more – no reordering or removal

1. Open a conversation with 60+ messages.
2. Load more (older) messages.
3. **Expected:** Older messages appear above existing ones; no duplicates; order preserved.
4. Load more again.
5. **Expected:** Same behavior; no messages disappear.

### d) SSE disconnect and reconnect

1. Open Live Chat with SSE connected.
2. In DevTools → Network, throttle or block the SSE request to simulate disconnect.
3. **Expected:** Console shows `[SSE] error, reconnect in Xms`.
4. Restore network.
5. **Expected:** SSE reconnects; new messages still appear in real time.

### e) AI reply appears right after generation

1. From WhatsApp, send a message that triggers an AI reply.
2. Keep Live Chat open on that conversation.
3. **Expected:** User message appears immediately; AI reply appears when the bot responds, without refresh.

---

## Checklist (quick validation)

- [ ] Rapid messages (10) all appear in correct order
- [ ] Refresh does not change message list or remove messages
- [ ] Load more does not reorder or remove messages
- [ ] SSE reconnect works after simulated disconnect
- [ ] AI reply appears in real time in dashboard
- [ ] Backend logs show `live_chat save_message broadcast` and `SSE broadcast`
- [ ] Frontend dev console shows `[SSE] connected` and `[SSE] new_message merged` when applicable
