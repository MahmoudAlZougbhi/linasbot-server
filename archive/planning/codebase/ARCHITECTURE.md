# Architecture

**Analysis Date:** 2026-01-19

## Pattern Overview

**Overall:** Modular Monolith with REST API + React Dashboard

**Key Characteristics:**
- Single FastAPI server handling webhooks, API, and bot logic
- Adapter pattern for multiple WhatsApp providers
- React SPA dashboard for management
- File-based and Firestore persistence
- Event-driven message processing

## Layers

**API Layer (modules/):**
- Purpose: HTTP endpoints for webhooks and dashboard
- Contains: FastAPI route handlers, request/response models
- Location: `modules/*_api.py` (e.g., `dashboard_api.py`, `live_chat_api.py`)
- Depends on: Service layer, config
- Used by: External clients (WhatsApp webhooks, dashboard)

**Handler Layer (handlers/):**
- Purpose: Message processing logic by type
- Contains: Text, voice, photo, training handlers
- Location: `handlers/text_handlers*.py`, `handlers/voice_handlers.py`, `handlers/photo_handlers.py`
- Depends on: Services, config, utilities
- Used by: Webhook handlers in modules

**Service Layer (services/):**
- Purpose: Core business logic and external integrations
- Contains: Chat response, analytics, live chat, API integrations
- Location: `services/*.py` (e.g., `chat_response_service.py`, `live_chat_service.py`)
- Depends on: Config, utilities, external APIs
- Used by: Handlers, API modules

**Adapter Layer (services/whatsapp_adapters/):**
- Purpose: Abstract WhatsApp provider differences
- Contains: Provider-specific implementations
- Location: `services/whatsapp_adapters/*.py`
- Pattern: Factory + Strategy (WhatsAppFactory creates appropriate adapter)
- Depends on: httpx, provider SDKs
- Used by: Handlers for sending messages

**Utility Layer (utils/):**
- Purpose: Shared helpers and Firebase initialization
- Contains: `utils.py` with Firestore operations, helper functions
- Location: `utils/utils.py`
- Depends on: firebase-admin, config
- Used by: All other layers

**Dashboard (dashboard/src/):**
- Purpose: Admin web interface
- Contains: React components, pages, contexts
- Location: `dashboard/src/`
- Depends on: Backend API via axios
- Used by: Administrators

## Data Flow

**WhatsApp Message Lifecycle:**

1. WhatsApp provider sends webhook to `/webhook/whatsapp` (`modules/webhook_handlers.py`)
2. Webhook handler validates signature, parses provider-specific format
3. Event handler routes to appropriate handler (`modules/event_handlers.py`)
4. Handler processes message:
   - Text: `handlers/text_handlers*.py` -> chat_response_service
   - Voice: `handlers/voice_handlers.py` -> audio transcription -> chat_response_service
   - Photo: `handlers/photo_handlers.py` -> OpenAI vision analysis
5. Chat response service generates AI response (`services/chat_response_service.py`)
6. Response sent via WhatsApp adapter (`services/whatsapp_adapters/`)
7. Conversation logged to Firestore and local files

**Dashboard API Flow:**

1. Dashboard makes HTTP request to backend API
2. API module handles request (`modules/*_api.py`)
3. Service layer performs business logic
4. Response returned as JSON
5. Dashboard updates UI

**State Management:**
- User state: In-memory defaultdicts in `config.py` (conversation history, gender, booking state)
- Persistence: Firestore for conversations, local JSONL for logs
- No session tokens between requests (stateless API with state in memory/DB)

## Key Abstractions

**WhatsAppAdapter (services/whatsapp_adapters/base_adapter.py):**
- Purpose: Common interface for WhatsApp messaging
- Examples: `MetaAdapter`, `MontyMobileAdapter`, `Dialog360Adapter`, `QiscusAdapter`
- Pattern: Abstract base class with factory creation

**API Modules (modules/):**
- Purpose: Group related API endpoints
- Examples: `dashboard_api.py`, `live_chat_api.py`, `qa_api.py`, `analytics_api.py`
- Pattern: FastAPI router modules imported into main app

**Handlers (handlers/):**
- Purpose: Message type-specific processing
- Examples: `text_handlers_respond.py`, `voice_handlers.py`, `photo_handlers.py`
- Pattern: Function-based handlers with shared state via config

**Services (services/):**
- Purpose: Reusable business logic
- Examples: `chat_response_service.py`, `live_chat_service.py`, `analytics_events.py`
- Pattern: Module-level functions (not classes)

## Entry Points

**Main Entry (`main.py`):**
- Location: `main.py`
- Triggers: `python main.py` or `uvicorn main:app`
- Responsibilities: Import all modules, initialize Firebase, start uvicorn server

**FastAPI App (`modules/core.py`):**
- Location: `modules/core.py`
- Triggers: FastAPI app creation, CORS setup
- Responsibilities: App configuration, middleware setup, client initialization

**Dashboard (`dashboard/src/index.js`):**
- Location: `dashboard/src/index.js`
- Triggers: Browser loads React app
- Responsibilities: Mount React app, setup routing

## Error Handling

**Strategy:** Try/catch at handler level, log errors, return graceful responses

**Patterns:**
- Webhook handlers catch exceptions, return 200 to avoid retries
- Services throw exceptions with descriptive messages
- Dashboard displays toast notifications for API errors

## Cross-Cutting Concerns

**Logging:**
- Python print statements for debugging
- Local file logging (`backend.log`, `logs/` directory)
- Analytics events to `data/analytics_events.jsonl`

**Validation:**
- Pydantic models for API request/response (`modules/models.py`)
- Manual validation in handlers
- Environment variable validation at startup

**Configuration:**
- Centralized in `config.py`
- Environment variables loaded via python-dotenv
- Bot assets loaded from `data/` files at startup

**User State:**
- In-memory defaultdicts for session data
- Firestore for persistent conversation history
- No distributed state (single-server deployment)

---

*Architecture analysis: 2026-01-19*
*Update when major patterns change*
