# CLAUDE_MEMORY.md - Lina's Laser Bot v2.7.22

## Project Overview
- **Name**: Lina's Laser AI Bot - WhatsApp chatbot for a laser clinic
- **Version**: 2.7.22
- **Stack**: Python/FastAPI backend + React dashboard frontend
- **Database**: Firebase/Firestore
- **WhatsApp Providers**: Meta Cloud API, Dialog360, Qiscus, MontyMobile
- **AI**: OpenAI GPT for chat responses, photo analysis, voice transcription
- **Purpose**: Automated customer support, appointment booking, Q&A, live chat handoff

## Current State (What Works / What Doesn't)

### Working
- WhatsApp webhook receiving messages
- AI chat responses via OpenAI
- Voice message transcription and responses
- Photo analysis service
- Live chat with human takeover
- Q&A database management (API-based, moved from JSONL)
- Dashboard: Live Chat, Chat History, Analytics, Settings
- Smart messaging queue system
- Sentiment escalation detection
- Gender detection for personalized responses
- Booking state tracking

### Known Issues / Limitations
- Conversations auto-archive after 6 hours (configurable in `services/live_chat_service.py:21`)
- Q&A loaded from `data/conversation_log.jsonl` is DEPRECATED - now API-based
- Some legacy test files use wrong webhook endpoint (`/webhook/whatsapp` instead of `/webhook`)

## Architecture Notes
- **Entry point**: `main.py` - loads all modules and starts FastAPI on port 8003
- **Modular design**: handlers/, services/, modules/, routes/
- **WhatsApp adapters**: Factory pattern in `services/whatsapp_adapters/`
- **State management**: DefaultDicts in `config.py` for user context, gender, booking state
- **Message flow**: Webhook -> handlers/text_handlers_start.py -> text_handlers_message.py -> text_handlers_respond.py -> WhatsApp adapter

## Key Files & Paths

| Category | File | Purpose |
|----------|------|---------|
| Entry | `main.py` | App entry point, loads modules |
| Config | `config.py` | All settings, API keys, user state dicts |
| Core | `modules/core.py` | FastAPI app instance |
| Webhook | `modules/webhook_handlers.py` | Receives WhatsApp messages |
| Chat Response | `services/chat_response_service.py` | Main AI response logic |
| Live Chat | `services/live_chat_service.py` | Human takeover logic |
| Q&A | `services/qa_database_service.py` | API-based Q&A management |
| Smart Msg | `services/smart_messaging.py` | Message queue/batching |
| Text Handler | `handlers/text_handlers_respond.py` | Processes and sends responses |
| Voice | `handlers/voice_handlers.py` | Voice message handling |
| Dashboard | `dashboard/` | React frontend |
| Data | `data/knowledge_base.txt` | Core bot knowledge |
| Data | `data/style_guide.txt` | Bot personality/style |
| Data | `data/price_list.txt` | Service pricing |
| Data | `data/qa_database.json` | Local Q&A backup |

## Commands & Debug Tips

```bash
# Start backend
./venv/bin/python3 main.py

# Start dashboard (in dashboard/ folder)
npm start

# Debug Firestore conversations
./venv/bin/python3 debug_firestore_chats.py

# Fix archived conversations
./venv/bin/python3 fix_archived_conversations.py

# Test live chat
./venv/bin/python3 test_live_chat_simple.py

# Check provider status
./venv/bin/python3 check_provider_status.py

# Restart on server
sudo systemctl restart bot-api.service

# Build dashboard for production
npm run build
```

## Open Issues
1. 6-hour auto-archive window may be too short for some use cases
2. Need to verify all webhook tests use correct endpoint `/webhook`
3. Training mode (`conversation_log.jsonl`) deprecated but file still exists

## Next Steps (Checklist)
- [ ] Review and test smart messaging queue functionality
- [ ] Verify voice handler improvements are working
- [ ] Test MontyMobile template service integration
- [ ] Review message preview service functionality

---

## Session Log

### 2025-01-17 - Initial Memory Setup
**Session Summary**: Created `CLAUDE_MEMORY.md` to track project state across sessions.

**Key Findings from Codebase Analysis**:
- Project is a mature WhatsApp chatbot with comprehensive features
- Recent work (Jan 14-16) focused on:
  - `chat_response_service.py` - Major updates (59KB)
  - `text_handlers_respond.py` - Response handling updates
  - `webhook_handlers.py` - Webhook processing
  - `smart_messaging.py` & `smart_messaging_api.py` - Message queue system
  - `voice_handlers.py` - Voice message handling
  - `live_chat_service.py` - Human takeover logic
  - `service_template_mapping_service.py` - New service (Jan 16)
  - `message_preview_service.py` - New service (Jan 16)

**Previous Session Work (from LIVE_CHAT_FIX_SUMMARY.md)**:
- Fixed 11 archived conversations (set to active)
- Identified wrong webhook endpoint in tests
- Created debug tools: `debug_firestore_chats.py`, `fix_archived_conversations.py`
- Created correct test script: `test_live_chat_simple.py`
- Documented 6-hour auto-archive behavior

**Files Created/Modified This Session**:
- Created: `CLAUDE_MEMORY.md`

**No Code Changes Made** - This session was for documentation and memory setup.
