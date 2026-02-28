# CLAUDE_MEMORY.md - Lina's Laser Bot v2.7.22

## Project Overview
- **Name**: Lina's Laser AI Bot - WhatsApp chatbot for a laser clinic
- **Version**: 2.7.22
- **Repo**: https://github.com/KobyKodes/Linas-Laser-Bot (private)
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
./venv/bin/python3 scripts/debug_firestore_chats.py

# Fix archived conversations
./venv/bin/python3 fix_archived_conversations.py

# Test live chat
./venv/bin/python3 test_live_chat_simple.py

# Check provider status
./venv/bin/python3 scripts/check_provider_status.py

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

### 2025-01-17 - Initial Memory Setup & GitHub Push
**Session Summary**: Created `CLAUDE_MEMORY.md` and pushed codebase to GitHub.

**Actions Completed**:
1. Created `CLAUDE_MEMORY.md` for session tracking
2. Initialized git repository
3. Updated `.gitignore` with Python/Node/sensitive file exclusions
4. Created GitHub repo: https://github.com/KobyKodes/Linas-Laser-Bot (private)
5. Pushed 175 files to main branch

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
- Created debug tools: `scripts/debug_firestore_chats.py`, `fix_archived_conversations.py`
- Created correct test script: `test_live_chat_simple.py`
- Documented 6-hour auto-archive behavior

**Files Created/Modified This Session**:
- Created: `CLAUDE_MEMORY.md`
- Modified: `.gitignore` (added Python/Node/sensitive file exclusions)

---

### 2025-01-17 - Timezone Fix for Live Chat Service
**Session Summary**: Fixed datetime timezone mismatch causing live chat errors.

**Issue**: `TypeError: can't subtract offset-naive and offset-aware datetimes` in `get_active_conversations()`

**Root Cause**: The `_parse_timestamp()` method returns UTC-aware datetimes, but `current_time` was created with `datetime.datetime.now()` (timezone-naive).

**Fix Applied** (`services/live_chat_service.py`):
- Line 46: Changed `datetime.datetime.now()` → `datetime.datetime.now(datetime.timezone.utc)`
- Line 63: Changed `datetime.datetime.now()` → `datetime.datetime.now(datetime.timezone.utc)`
- Line 278: Changed `datetime.datetime.now()` → `datetime.datetime.now(datetime.timezone.utc)`

**Files Modified**:
- `services/live_chat_service.py` - 3 lines changed to use timezone-aware datetimes

---

### 2025-01-17 - Live Chat Refresh & Real-Time Updates
**Session Summary**: Fixed timezone error, restored 6-hour filter, and implemented real-time updates for live chat.

**Issues Fixed**:

1. **Timezone Mismatch Error**
   - Error: `TypeError: can't subtract offset-naive and offset-aware datetimes`
   - Cause: `_parse_timestamp()` returns UTC-aware datetimes, but `current_time` was naive
   - Fix: Changed `datetime.datetime.now()` → `datetime.datetime.now(datetime.timezone.utc)` in 3 locations

2. **Active Conversations Showing Old Chats**
   - Cause: `ACTIVE_TIME_WINDOW` was set to 7 days instead of 6 hours
   - Fix: Changed from `7 * 24 * 60 * 60` → `6 * 60 * 60` (6 hours)

3. **Live Chat Not Real-Time**
   - Requirement: Active conversations refresh every 5s, messages real-time
   - Fixes:
     - Changed conversation list polling from 10s → 5s
     - Added message polling every 3s for selected conversation
     - Reduced backend cache TTL from 120s → 5s

**Files Modified**:

| File | Changes |
|------|---------|
| `services/live_chat_service.py` | - Lines 46, 63, 278: Use UTC-aware datetime<br>- Line 22: `ACTIVE_TIME_WINDOW` = 6 hours<br>- Line 25: `CACHE_TTL` = 5 seconds |
| `dashboard/src/pages/LiveChat.js` | - Line 411: Conversations refresh every 5s<br>- Lines 418-453: Added real-time message polling (3s interval) |

**Current Live Chat Behavior**:
- Conversations list: Refreshes every 5 seconds
- Selected conversation messages: Polls every 3 seconds
- Backend cache: 5 seconds
- Time window: Only shows conversations from last 6 hours

---

### 2025-01-17 - Appointment Booking Fix
**Session Summary**: Fixed appointment booking failing with "Customer not found" error.

**Root Cause**: GPT was calling `create_appointment` directly without first checking if the customer exists in the system. The appointment API requires the customer to already be registered.

**Fix Applied** (`utils/utils.py` - system instructions):
Added explicit booking flow instructions telling GPT to:
1. First call `get_customer_by_phone` to check if customer exists
2. If not found, call `create_customer` with name, phone, gender, branch_id
3. Then call `create_appointment`

**Files Modified**:
- `utils/utils.py` - Added "CRITICAL: Appointment Booking Flow" section to system prompt (lines 1334-1341)

---

### 2025-01-17 - Gender Persistence Fix & Phone Number Fix
**Session Summary**: Fixed gender not persisting across server restarts, and fixed phone_number being None when saving to Firestore.

**Issue 1: Gender Lost After Server Restart**
- **Symptom**: Bot asks for gender again after 30 minutes even though user already provided it
- **Root Cause**: Gender was only stored in volatile Python memory (`config.user_gender`), not persisted to Firestore
- **Investigation Found**:
  - `config.user_gender` is a `defaultdict(str)` - lost on server restart
  - `customer_info` in Firestore didn't include gender field
  - User documents in Firestore didn't include gender field

**Fix Applied**:
1. **Save gender to Firestore** (`utils/utils.py`):
   - Added `gender` and `greeting_stage` to `customer_info` (lines 248-258)
   - Added `gender` and `greeting_stage` to user document creation (lines 217-227)
   - Only updates these fields if they have values (won't overwrite with empty)

2. **New function to retrieve user state** (`utils/utils.py` lines 750-807):
   - Created `get_user_state_from_firestore(user_id)`
   - Retrieves gender, greeting_stage, name, phone from Firestore
   - Falls back to checking most recent conversation's `customer_info`

3. **Restore state on message received** (`modules/webhook_handlers.py` lines 240-270):
   - Added code to restore user state from Firestore if not in memory
   - Happens after API check but before "is_new_user" check
   - Restores `gender`, `greeting_stage`, and `name` to config variables

**Issue 2: phone_number Being None in Firestore Saves**
- **Symptom**: Log showed `phone_number param=None` when saving AI messages
- **Root Cause**: Dashboard test endpoints didn't store `phone_number` in `user_data_whatsapp`
- **Fix**: Added `'phone_number': request.phone` to all `user_data_whatsapp` initializations in `modules/dashboard_api.py`

**Files Modified**:

| File | Changes |
|------|---------|
| `utils/utils.py` | - Lines 212-242: Save gender to user document<br>- Lines 248-258: Save gender to customer_info<br>- Lines 750-807: New `get_user_state_from_firestore()` function |
| `modules/webhook_handlers.py` | - Lines 240-270: Restore user state from Firestore on message received |
| `modules/dashboard_api.py` | - Lines 112, 126, 255, 365, 379, 498, 588, 717: Added phone_number to all user_data_whatsapp initializations |

**Data Flow After Fix**:
1. User tells bot their gender → saved to `config.user_gender` (memory)
2. Any message saved → gender persisted to Firestore (`customer_info` + user document)
3. Server restarts → memory cleared
4. User sends new message → Firestore queried → gender restored to memory
5. Bot remembers gender, skips asking again

---

## Git Status - Unpushed Changes

### Last Push
- **Date**: 2025-01-17 (Initial commit)
- **Commit**: `3dc35c9` - Initial commit - Lina's Laser AI Bot v2.7.22

### Pending Changes (Not Yet Pushed)

| File | Status | Description |
|------|--------|-------------|
| `CLAUDE_MEMORY.md` | Modified | Session logs and this tracking section |
| `dashboard/src/pages/LiveChat.js` | Modified | Real-time polling (5s conversations, 3s messages) |
| `modules/dashboard_api.py` | Modified | Phone number fix for all test endpoints |
| `modules/webhook_handlers.py` | Modified | Restore user state from Firestore |
| `services/live_chat_service.py` | Modified | Timezone fix, 6-hour window, 5s cache TTL |
| `services/chat_response_service.py` | Modified | (check specific changes) |
| `utils/utils.py` | Modified | Gender persistence, booking flow instructions |
| `data/analytics_events.jsonl` | Modified | Runtime data (consider .gitignore) |
| `data/app_settings.json` | Modified | Runtime data (consider .gitignore) |
| `data/conversation_log.jsonl` | Modified | Runtime data (consider .gitignore) |
| `data/reports_log.jsonl` | Modified | Runtime data (consider .gitignore) |

### To Push Changes
```bash
git add -A
git commit -m "Fix gender persistence, phone_number, live chat real-time updates, timezone issues"
git push origin main
```

### Files to Consider Adding to .gitignore
- `data/analytics_events.jsonl` - Runtime analytics data
- `data/conversation_log.jsonl` - Runtime conversation logs
- `data/reports_log.jsonl` - Runtime report logs
- `data/app_settings.json` - Runtime app settings (if contains sensitive data)

---

### 2025-01-17 - Live Chat Performance & Async Firestore Fixes
**Session Summary**: Fixed multiple issues causing live chat to crash/timeout and improved UX for loading chats.

**Issues Fixed**:

1. **Chats Not Loading Immediately (Lazy Loading)**
   - **Symptom**: Console showed fetch → API response → then loading, causing delays
   - **Fix**: Display chat list immediately, load messages asynchronously
   - Files: `LiveChat.js`, `ChatHistory.js`

2. **Takeover Button Timing Out (30s)**
   - **Symptom**: `AxiosError: timeout of 30000ms exceeded` when clicking Take Over
   - **Root Cause**: Synchronous Firestore calls blocking asyncio event loop
   - **Fix**:
     - Increased frontend timeout to 60s for takeover/release/send-message
     - Wrapped `set_human_takeover_status` Firestore call in `asyncio.to_thread()`

3. **Backend Crashing on Large Conversations**
   - **Symptom**: Loading a chat with many messages caused backend to go offline, `/api/test` stopped working
   - **Root Cause**: ALL Firestore calls in `live_chat_service.py` were synchronous, blocking the event loop
   - **Fix**:
     - Wrapped ALL Firestore operations in `asyncio.to_thread()` to prevent blocking
     - Added `max_messages=100` limit to `get_conversation_details()` to prevent timeout on huge conversations
     - Added 60-second timeout with AbortController on frontend fetch calls

**Files Modified**:

| File | Changes |
|------|---------|
| `services/live_chat_service.py` | - `get_active_conversations`: Wrapped `stream()` calls in `asyncio.to_thread()`<br>- `get_waiting_queue`: Wrapped `stream()` calls in `asyncio.to_thread()`<br>- `get_client_conversations`: Wrapped `stream()` in `asyncio.to_thread()`<br>- `get_conversation_details`: Added `asyncio.to_thread()` + `max_messages=100` limit<br>- `end_conversation`: Wrapped `update()` and `get()` in `asyncio.to_thread()`<br>- `reopen_conversation`: Wrapped `update()` in `asyncio.to_thread()`<br>- `_auto_archive_conversation`: Wrapped `update()` in `asyncio.to_thread()` |
| `utils/utils.py` | - `set_human_takeover_status`: Wrapped `conv_doc_ref.update()` in `asyncio.to_thread()` |
| `dashboard/src/hooks/useApi.js` | - `takeoverConversation`: Increased timeout to 60s, added timeout error handling<br>- `releaseConversation`: Increased timeout to 60s<br>- `sendOperatorMessage`: Increased timeout to 60s |
| `dashboard/src/pages/LiveChat.js` | - Added `messagesLoading` state for lazy loading UX<br>- Initial load shows chats immediately, loads messages async<br>- Click on chat shows loading spinner while messages load<br>- Added 60s timeout with AbortController to `fetchConversationMessages` |
| `dashboard/src/pages/ChatHistory.js` | - `loadConversations`: Removed `await` blocking, loads messages async<br>- `loadConversationMessages`: Added 60s timeout with AbortController |

**Key Technical Details**:
- Python Firestore SDK is synchronous - blocks asyncio event loop
- `asyncio.to_thread()` runs sync code in thread pool, doesn't block event loop
- Large conversations (100+ messages) were causing server to hang completely
- Now limits to last 100 messages and returns `total_messages` count in response

---

### 2025-01-17 - Service ID Mappings for All Services
**Session Summary**: Fixed appointment booking failing for services other than laser hair removal (e.g., tattoo removal).

**Issue**: Booking tattoo removal and other services failed with "Customer not found" error because GPT didn't know the correct service_id for each service. Only "1 for Laser Hair Removal" was documented.

**Root Cause**: The GPT system prompt only mentioned service_id=1 for laser hair removal. GPT was guessing or using wrong service_ids for other services like tattoo removal.

**Fix Applied** (`utils/utils.py`):
Added complete service_id, machine_id, and branch_id mappings to system prompt:

<!--**Service IDs:**-->
<!--| service_id | Service Name |-->
<!--|------------|--------------|-->
<!--| 1 | Laser Hair Removal (Men) |-->
<!--| 2 | CO2 Laser (Scar Removal, Acne Scars, Stretch Marks) |-->
<!--| 3 | Laser Hair Removal (Women) |-->
<!--| 4 | Laser Tattoo Removal |-->
<!--| 5 | Whitening (Dark Area Lightening) |-->
<!---->
<!--**Machine IDs:**-->
<!--| machine_id | Machine Name | Used For |-->
<!--|------------|--------------|----------|-->
<!--| 1 | Cynosure Elite+ | Hair Removal |-->
<!--| 2 | Neo | Hair Removal (light skin) |-->
<!--| 3 | Quadro | Hair Removal |-->
<!--| 4 | Trio | Hair Removal |-->
<!--| 5 | Pico Laser | Tattoo Removal ONLY |-->
<!--| 6 | CO2 Laser | Scar Removal |-->
<!--| 7 | DPL | Whitening |-->
<!---->
<!--**Branch IDs:**-->
<!--| branch_id | Branch Location |-->
<!--|-----------|-----------------|-->
<!--| 1 | Beirut - Manara (Main) |-->
<!--| 2 | Antelias - Center Haj |-->
<!---->
<!--**Service-Machine Matching Rules Added:**-->
<!--- Tattoo Removal (service_id=4) → MUST use Pico Laser (machine_id=5)-->
<!--- Hair Removal → Use Neo (2), Quadro (3), or Trio (4)-->
<!--- CO2 treatments (service_id=2) → MUST use CO2 Laser (6)-->
<!--- Whitening (service_id=5) → MUST use DPL (7)-->

**Files Modified**:
- `utils/utils.py`:
  - Lines ~1372-1400: Added complete service/machine/branch ID mappings to system prompt
  - Lines ~1006-1008: Updated `create_appointment` tool parameter descriptions with ID mappings
  - Lines ~1156-1159: Updated `get_pricing_details` tool parameter descriptions with ID mappings

---

### 2025-01-17 - User State Persistence & Gender Display Fix
**Session Summary**: Fixed user state (gender, name) not being retrieved after server restart, and added gender display to dashboard.

**Issue**: After server restart, the bot would ask for gender again even though it was previously saved to Firestore.

**Root Causes**:
1. **Synchronous Firestore Calls Blocking Event Loop**: All Firestore operations in `get_user_state_from_firestore`, `save_user_gender`, and `save_conversation_message_to_firestore` were using synchronous SDK calls that blocked the asyncio event loop, causing timeouts/failures.
2. **Gender Not Displayed in Dashboard**: Live Chat and Chat History pages didn't show the user's gender.

**Fixes Applied**:

1. **`utils/utils.py` - `get_user_state_from_firestore()`**:
   - Wrapped `user_doc_ref.get()` in `asyncio.to_thread()`
   - Wrapped conversation query in `asyncio.to_thread()`

2. **`utils/utils.py` - `save_conversation_message_to_firestore()`**:
   - Wrapped ALL Firestore operations in `asyncio.to_thread()`:
     - `existing_conv_ref.get()`
     - `user_doc_ref.get()`
     - `user_doc_ref.set()`
     - `user_doc_ref.update()`
     - `doc_ref.get()`
     - `doc_ref.update()`
     - `conversations_collection.add()`

3. **`services/user_persistence_service.py` - `save_user_gender()`**:
   - Wrapped `user_doc_ref.get()`, `user_doc_ref.update()`, `user_doc_ref.set()` in `asyncio.to_thread()`
   - Wrapped conversation query and update in `asyncio.to_thread()`

4. **`services/live_chat_service.py` - `get_active_conversations()`**:
   - Added `gender` field to client_entry returned to frontend

5. **`routes/chat_history_routes.py` - `get_chat_history_customers()`**:
   - Added `gender` field to customer_data returned to frontend

6. **`dashboard/src/pages/LiveChat.js`**:
   - Added Gender display in User Information section

7. **`dashboard/src/pages/ChatHistory.js`**:
   - Added Gender display in customer header info

**Data Flow After Fix**:
1. User tells bot their gender → saved to memory + Firestore (user document + conversation customer_info)
2. Server restarts → memory cleared
3. User sends new message → `get_user_state_from_firestore()` retrieves gender from Firestore
4. Gender restored to memory → bot remembers, skips asking again
5. Dashboard shows gender in User Information section

---

### 2025-01-18 - Appointment Booking Analytics Error Fix
**Session Summary**: Fixed error causing appointment booking to fail with "'str' object has no attribute 'get'".

**Issue**: Tattoo removal appointment was created successfully, but then GPT triggered human handover because it received an error message.

**Root Cause**: The analytics tracking code in `chat_response_service.py` expected `machine` field in API response to be a dictionary like `{'name': 'candela'}`, but the API returns it as a simple string `'candela'`. When the code tried `machine_info.get("name")`, it threw `'str' object has no attribute 'get'`.

**Fixes Applied** (`services/chat_response_service.py`):
1. **Line 678**: Added `isinstance(tool_output, dict)` check before `.get("success")`
2. **Line 684**: Added `isinstance(service_info, dict)` check - uses `str(service_info)` if it's a string
3. **Lines 685-687**: Changed `machine_info` handling to detect if it's a string or dict:
   ```python
   machine_info = appointment_data.get("machine")
   machine_name = machine_info.get("name", "unassigned") if isinstance(machine_info, dict) else (str(machine_info) if machine_info else "unassigned")
   ```
4. **Line 701**: Added `isinstance(tool_output, dict)` check for `update_appointment_date` analytics

**Files Modified**:
- `services/chat_response_service.py` - Fixed analytics code to handle string/dict variations in API response

---

### 2025-01-18 - Dashboard Test Endpoints State Restoration
**Session Summary**: Completed fix for dashboard test endpoints bypassing Firestore state restoration.

**Issue**: Dashboard showed gender correctly (Firestore had data), but backend logs showed `current_gender: 'unknown'` when processing messages from dashboard test endpoints.

**Root Cause**: Dashboard test endpoints (`/api/test-message`, `/api/test-image`, etc.) in `modules/dashboard_api.py` bypassed `webhook_handlers.py` where the Firestore state restoration code was located. These endpoints directly called message handlers without restoring user state.

**Fix Applied**:

1. **Created helper function** (`modules/dashboard_api.py`):
   ```python
   async def restore_user_state_from_firestore(user_id: str) -> str:
       """Restore user state (gender, name, greeting_stage) from Firestore."""
       # Restores gender, greeting_stage, name to config variables
       # Returns restored_name if found
   ```

2. **Added restore call to ALL dashboard test endpoints**:
   - `/api/test-message` - Added after user_data_whatsapp initialization
   - `/api/test-image` - Added after user_data_whatsapp initialization
   - `/api/test-voice` - Added after user_data_whatsapp initialization
   - `/api/test-voice-text` - Added after user_data_whatsapp initialization
   - `/api/test-voice-upload` - Added after user_data_whatsapp initialization
   - `/api/test-image-upload` - Added after user_data_whatsapp initialization

**Files Modified**:
- `modules/dashboard_api.py`:
  - Added `restore_user_state_from_firestore()` helper function
  - Added restore call to all 6 test endpoints

**Data Flow After Fix**:
1. Dashboard test endpoint receives message
2. Initializes user_data_whatsapp
3. **NEW**: Calls `restore_user_state_from_firestore(user_id)` to restore gender, name, greeting_stage from Firestore
4. If name found in Firestore, updates `user_name` variable
5. Proceeds with message processing with correct user state

---
