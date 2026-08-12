# Firestore Indexes for Live Chat

Live Chat requires composite indexes. If you see errors like:
```
400 The query requires an index. You can create it here: https://console.firebase.google.com/...
```

## Quick fix: click the link

The error message includes a direct link. **Click it** – it opens Firebase Console with the index pre-filled. Click "Create index" and wait a few minutes.

## Indexes needed

1. **live_chat_index** (unified chats):
   - `last_message_at` DESC
   - `conversation_id` ASC

2. **live_chat_index** (with conversation_state filter):
   - `conversation_state` ASC
   - `last_message_at` DESC
   - `conversation_id` ASC

3. **conversations** (waiting queue – collection group):
   - `human_takeover_active` ASC

## Deploy via Firebase CLI (optional)

If you use Firebase CLI:

```bash
firebase deploy --only firestore:indexes
```

The `firestore.indexes.json` in the project root defines these indexes.

**LIVE deploy is owner-activated** — see `docs/FIRESTORE_INDEXES_DEPLOY.md`.
There is no automatic GHA deploy of indexes on every push.
