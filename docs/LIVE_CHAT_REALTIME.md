# Live Chat Real-Time (WhatsApp-like)

Live Chat uses **Server-Sent Events (SSE)** for real-time messaging. Messages appear instantly without page refresh—like WhatsApp.

## Architecture

- **REST APIs**: Initial chat history, conversation list, send message, etc.
- **SSE layer**: Real-time push for new incoming/outgoing messages.

## Flow

1. **Dashboard connects** to `GET /api/live-chat/events` (EventSource).
2. **On new user message**: Backend saves to Firestore → invalidates cache → broadcasts `new_message` with full message payload.
3. **Frontend receives** `new_message` → if viewing that conversation, appends message **instantly** (no API call).
4. **Conversation list** refreshes in background for last_message and badge updates.
5. **Admin sends message**: Saved to Firestore → same broadcast → other tabs/devices update instantly.

## Events

| Event             | Payload                          | Frontend action                          |
|-------------------|----------------------------------|------------------------------------------|
| `connected`       | status, connected_at             | Connection established                   |
| `conversations`   | conversations, total             | Initial conversation list                |
| `new_message`     | user_id, conversation_id, **message** | Instant append if match; else refetch |
| `new_conversation`| user_id, conversation_id, phone, name | Refresh list with new badge          |
| `heartbeat`       | timestamp, active_clients        | Keep-alive (no-op)                       |

## Key Files

- **Backend**
  - `modules/live_chat_api.py` – SSE endpoint, broadcast helper
  - `services/live_chat_sse_broadcaster.py` – SSE hub
  - `utils/utils.py` – `broadcast_sse_event`, `_message_to_dashboard_format`
- **Frontend**
  - `dashboard/src/hooks/useLiveChatSSE.js` – SSE connection, instant append
  - `dashboard/src/pages/LiveChat.js` – UI, message display

## Running Locally

1. **Backend** (from project root):
   ```bash
   python main.py
   ```
   Backend: http://localhost:8003

2. **Frontend** (optional for dev):
   ```bash
   cd dashboard && npm start
   ```
   Dashboard: http://localhost:3000

3. **Or use built dashboard**: Backend serves `/` from `dashboard/build` at http://localhost:8003

4. **SSE URL**: `http://localhost:8003/api/live-chat/events` (or same origin when proxied)

## Troubleshooting

- **Messages not appearing**: Check browser console for SSE connection/errors. Ensure EventSource URL is correct (use `getApiBaseUrl()`).
- **CORS**: Backend CORS allows `http://localhost:3000` and `http://localhost:8003`. Add your origin if needed in `modules/core.py`.
- **Buffering**: Headers `Cache-Control: no-cache`, `X-Accel-Buffering: no` disable buffering. If behind nginx, ensure `proxy_buffering off` for `/api/live-chat/events`.
