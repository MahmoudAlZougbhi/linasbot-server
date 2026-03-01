# Live Chat FAQ Correction Workflow

When the bot answers using **Managed Data (FAQ)** and the operator presses 👎 (dislike) on that reply, a dedicated **FAQ Correction** modal opens. The operator can either update the same FAQ entry (global fix) or create a new FAQ entry from the user’s question and the edited answer.

## Overview

- **Trigger**: Dislike on a bot message that was sourced from Managed FAQ (local Q&A match).
- **Modal**: Shows FAQ match context (stored question, user question, similarity/tier) and an editable answer.
- **Actions**:
  - **Save Change**: Update the same FAQ entry’s answer (all languages in that group get the same Arabic answer).
  - **Save New**: Create a new FAQ entry (user’s question + edited answer); the original FAQ entry is unchanged.

## Backend

### 1. FAQ match metadata on bot replies

When the bot replies from Managed FAQ (`handlers/text_handlers_respond.py`), the message is saved with:

- `metadata.source = "qa_database"`
- `metadata.reply_source = "managed_faq"`
- `metadata.faq_match = { faq_id, stored_question, stored_language, user_question, user_language, similarity, tier }`

This metadata is:

- Stored in Firestore with the message
- Returned in `GET /api/live-chat/conversation/{user_id}/{conversation_id}` (each message may include `metadata.faq_match`, `reply_source`)
- Included in SSE `new_message` payloads (via `_message_to_dashboard_format` in `utils/utils.py`)

### 2. API endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/live-chat/faq-match-context?user_id=&conversation_id=&message_id=` | Return `faq_match` and current FAQ entry (question + answer) for a message. |
| POST | `/api/faq/update-answer` | Update existing FAQ entry’s answer. Body: `{ faq_id, new_answer_text, updated_by, source }`. Applies language rules (answer in Arabic; all rows in same `qa_group_id` updated). |
| POST | `/api/faq/create-from-livechat` | Create new FAQ entry. Body: `{ question_text, question_language, answer_text, created_by, source, related_faq_id?, match_similarity? }`. Question in original language; answer stored in Arabic; `answer_franco = answer_ar`. |

### 3. Language rules

- **Question**: Kept in its original language (Arabic or Franco).
- **Answer**: Always stored in Arabic for both Arabic and Franco sections; `answer_franco` is set equal to `answer_ar`.
- If the edited answer is not in Arabic script, it is translated to Arabic before saving.

### 4. Audit metadata

- **update-answer**: `updated_at`, `updated_by`, `source` on updated rows.
- **create-from-livechat**: `created_at`, `created_by`, `source` on created entries; optional `derived_from_faq_id`, `match_similarity`.

## Frontend

### 1. Dislike behavior

- **If** the message has `metadata.faq_match` or `reply_source === "managed_faq"`: open **FAQ Correction** modal.
- **Else**: open the existing **Edit Message** modal (update message in Firestore only).

### 2. FAQ Correction modal

- **Display**: Stored FAQ question, user’s actual question, match confidence (similarity and tier), editable answer (textarea).
- **Actions**: Cancel, **Save Change** (update same FAQ + optionally update chat message text), **Save New** (create new FAQ entry).
- Context is taken from the message when available, or fetched via `GET /api/live-chat/faq-match-context` when needed.

### 3. After Save Change

- Calls `POST /api/faq/update-answer`.
- Optionally updates the conversation message in Firestore and UI via `POST /api/live-chat/edit-message` so the bubble shows the new answer.

### 4. After Save New

- Calls `POST /api/faq/create-from-livechat` with user question, language, edited answer, and optional `related_faq_id` / `match_similarity`.
- Toast: “New FAQ added”.

## Files touched

- **Backend**: `handlers/text_handlers_respond.py`, `utils/utils.py`, `services/live_chat_service.py`, `services/local_qa_service.py`, `modules/live_chat_api.py`, `modules/local_qa_api.py`
- **Frontend**: `dashboard/src/utils/liveChatApi.js`, `dashboard/src/pages/LiveChat.js`
- **Docs**: `docs/LIVE_CHAT_FAQ_CORRECTION_WORKFLOW.md`

## Manual test plan

1. **FAQ match reply → dislike → modal → Save Change**
   - Send a question that matches an existing FAQ (e.g. ≥90% match).
   - In Live Chat, press 👎 on the bot reply.
   - Confirm the **FAQ Correction** modal opens with stored question, user question, similarity/tier, and editable answer.
   - Edit the answer and click **Save Change**.
   - Confirm the FAQ entry is updated in Managed Data and the chat bubble shows the new answer (and optionally reload FAQ list to confirm).

2. **Save New**
   - From the same modal (or another FAQ-sourced reply), edit the answer and click **Save New**.
   - Confirm a new FAQ entry is created (e.g. in Manage Data / local Q&A list).
   - Confirm the original FAQ entry is unchanged.

3. **Franco question → answer stored in Arabic**
   - Use a Franco question that matches an FAQ; trigger FAQ Correction and change the answer to Franco text, then Save Change or Save New.
   - Confirm the stored answer is in Arabic in both AR and Franco sections (e.g. by checking the JSONL or Manage Data UI).

4. **Non-FAQ bot reply → Edit Message**
   - Send a message that gets an AI (GPT) or non-FAQ reply.
   - Press 👎 on that reply.
   - Confirm the **Edit Message** modal opens (not FAQ Correction), and that saving updates only the message in the conversation, not the FAQ.
