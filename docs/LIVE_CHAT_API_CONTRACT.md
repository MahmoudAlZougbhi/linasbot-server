# Live Chat API Contract (Baseline)

This document defines the behavior-critical request/response fields that must remain
compatible during the Live Chat refactor.

## Scope

- Backend API: `modules/live_chat_api.py`
- Service shaping data: `services/live_chat_service.py`
- Frontend API client: `dashboard/src/hooks/useApi.js`
- Frontend consumer: `dashboard/src/pages/LiveChat.js`

## Endpoint Contracts

### `GET /api/live-chat/events` (SSE)

Event types expected by dashboard:

- `connected`
  - payload: `{ "status": "connected" }`
- `conversations`
  - payload:
    - `conversations`: array
    - `total`: number
- `new_message`
  - payload commonly includes:
    - `conversation_id`: string
    - `user_id`: string
    - `message`: object
- `new_conversation`
  - payload commonly includes:
    - `conversation_id`: string
    - `user_id`: string
- `heartbeat`
  - payload includes a timestamp-like numeric value

Behavior-critical:

- SSE stays available at same path.
- Existing event names remain unchanged.
- `new_message` and `new_conversation` continue to identify conversation/user.

### `GET /api/live-chat/unified-chats`

Query params:

- `search` (optional)
- `page` (default `1`)
- `page_size` (default `30`)

Response:

```json
{
  "success": true,
  "chats": [],
  "total": 0,
  "page": 1,
  "page_size": 30,
  "has_more": false
}
```

Each chat item must preserve:

- `user_id`
- `conversation_id`
- `user_name`
- `user_phone`
- `phone_clean`
- `language`
- `last_message`:
  - `content`
  - `is_user`
  - `timestamp`
- `last_activity`
- `status` (`bot` | `human` | `waiting_human`)
- `message_count`
- `duration_seconds`
- `is_live`
- `customer_info`

### `GET /api/live-chat/active-conversations`

Query params:

- `search` (optional)

Response:

```json
{
  "success": true,
  "conversations": [],
  "total": 0,
  "search": ""
}
```

Conversation entries preserve:

- `conversation_id`
- `user_id`
- `status`
- `message_count`
- `last_activity`
- `duration_seconds`
- `sentiment`
- `operator_id`
- `customer_info`
- `last_message` (content/is_user/timestamp)

### `GET /api/live-chat/waiting-queue`

Response:

```json
{
  "success": true,
  "queue": [],
  "total": 0
}
```

Queue item preserve:

- `conversation_id`
- `user_id`
- `user_name`
- `user_phone`
- `phone_clean`
- `language`
- `reason`
- `wait_time_seconds`
- `sentiment`
- `message_count`
- `priority`
- `last_message`

### `POST /api/live-chat/takeover`

Request body:

```json
{
  "conversation_id": "string",
  "user_id": "string",
  "operator_id": "operator_001"
}
```

Response (success):

```json
{
  "success": true,
  "message": "Conversation taken over successfully",
  "conversation_id": "string",
  "operator_id": "string"
}
```

### `POST /api/live-chat/release`

Request body:

```json
{
  "conversation_id": "string",
  "user_id": "string"
}
```

Response (success):

```json
{
  "success": true,
  "message": "Conversation released to bot successfully",
  "conversation_id": "string"
}
```

### `POST /api/live-chat/send-message`

Request body:

```json
{
  "conversation_id": "string",
  "user_id": "string",
  "message": "string",
  "operator_id": "string",
  "message_type": "text"
}
```

`message_type` supports: `text`, `voice`, `image`.

Behavior-critical:

- Endpoint accepts same request fields.
- Existing response shape (`success`, `error`/`message`) remains compatible.
- Voice/image continue to work with current payload expectations.

### `POST /api/live-chat/end-conversation`

Request body:

```json
{
  "conversation_id": "string",
  "user_id": "string",
  "operator_id": "string"
}
```

Response (success):

```json
{
  "success": true,
  "message": "Conversation ended successfully",
  "conversation_id": "string",
  "status": "resolved"
}
```

### `POST /api/live-chat/operator-status`

Request body:

```json
{
  "operator_id": "string",
  "status": "available"
}
```

Response:

```json
{
  "success": true,
  "operator_id": "string",
  "status": "available"
}
```

### `GET /api/live-chat/conversation/{user_id}/{conversation_id}`

Query params:

- `days` (default `0`)
- `before` (optional ISO timestamp)

Response:

```json
{
  "success": true,
  "conversation_id": "string",
  "messages": [],
  "total_messages": 0,
  "returned_messages": 0,
  "sentiment": "neutral",
  "status": "active"
}
```

Message object must preserve:

- `timestamp` (ISO string)
- `is_user` (boolean)
- `content`
- `text`
- `type` (`text` / `voice` / `image`)
- `handled_by` (`bot` / `operator` style value)
- `role`
- optional `audio_url`
- optional `image_url`

### `GET /api/live-chat/client/{user_id}/conversations`

Response:

```json
{
  "success": true,
  "conversations": [],
  "total": 0
}
```

Conversation item preserve:

- `conversation_id`
- `message_count`
- `last_activity`
- `status`
- `sentiment`
- `human_takeover_active`
- `operator_id`

### `GET /api/live-chat/metrics`

Response:

```json
{
  "success": true,
  "metrics": {
    "total_active_conversations": 0,
    "bot_handling": 0,
    "human_handling": 0,
    "waiting_for_human": 0,
    "sentiment_distribution": {},
    "average_wait_time_seconds": 0,
    "active_operators": 0,
    "time_window_hours": 6
  },
  "timestamp": "ISO8601"
}
```

## Compatibility Notes

- Keep paths and HTTP methods unchanged.
- Keep top-level `success` and `error` semantics.
- Keep conversation/message IDs as strings.
- Keep message timestamps ISO-formatted in responses.
- Preserve behavior where smart automated messages are hidden from live chat history.
