# Codebase Structure

**Analysis Date:** 2026-01-19

## Directory Layout

```
linaslaserbot-2.7.22/
├── handlers/              # Message type handlers (text, voice, photo)
├── modules/               # FastAPI route modules and API endpoints
├── routes/                # Additional route definitions
├── services/              # Business logic and external integrations
│   └── whatsapp_adapters/ # WhatsApp provider adapters
├── utils/                 # Shared utilities and helpers
├── data/                  # Data files, configs, logs
├── dashboard/             # React admin dashboard
│   ├── src/
│   │   ├── components/    # Reusable React components
│   │   ├── pages/         # Page-level components
│   │   ├── contexts/      # React context providers
│   │   ├── hooks/         # Custom React hooks
│   │   └── utils/         # Frontend utilities
│   └── public/            # Static assets
├── frontend/              # Alternative/legacy frontend (minimal)
├── tests/                 # Test directory (minimal)
├── config/                # Configuration directory
├── logs/                  # Runtime logs
├── venv/                  # Python virtual environment
├── main.py                # Application entry point
├── config.py              # Global configuration
├── requirements.txt       # Python dependencies
└── .env                   # Environment variables
```

## Directory Purposes

**handlers/**
- Purpose: Process incoming messages by type
- Contains: Python modules for text, voice, photo, training
- Key files:
  - `text_handlers_respond.py` - Main text message response logic
  - `text_handlers_message.py` - Message building utilities
  - `voice_handlers.py` - Voice message transcription and response
  - `photo_handlers.py` - Photo analysis via OpenAI vision
  - `training_handlers.py` - Bot training mode
- Subdirectories: None (flat structure)

**modules/**
- Purpose: FastAPI API endpoint modules
- Contains: Route handlers for dashboard, webhooks, various features
- Key files:
  - `core.py` - FastAPI app initialization
  - `webhook_handlers.py` - WhatsApp webhook processing
  - `event_handlers.py` - Event routing to handlers
  - `dashboard_api.py` - Dashboard data endpoints
  - `live_chat_api.py` - Live chat takeover endpoints
  - `qa_api.py` - Q&A management endpoints
  - `settings_api.py` - Bot settings endpoints
- Subdirectories: None

**services/**
- Purpose: Core business logic and integrations
- Contains: Service modules, WhatsApp adapters
- Key files:
  - `chat_response_service.py` - AI response generation (largest file)
  - `live_chat_service.py` - Human takeover logic
  - `api_integrations.py` - External API calls (Lina's Laser API)
  - `analytics_events.py` - Analytics event tracking
  - `local_qa_service.py` - Q&A database management
- Subdirectories:
  - `whatsapp_adapters/` - Provider-specific adapters

**services/whatsapp_adapters/**
- Purpose: Abstract WhatsApp provider APIs
- Contains: Adapter implementations, factory
- Key files:
  - `base_adapter.py` - Abstract base class
  - `whatsapp_factory.py` - Adapter factory
  - `montymobile_adapter.py` - MontyMobile (primary)
  - `meta_adapter.py` - Meta Cloud API
  - `dialog360_adapter.py` - 360Dialog
  - `qiscus_adapter.py` - Qiscus (deprecated)

**utils/**
- Purpose: Shared utility functions
- Contains: `utils.py` with Firebase init, helpers
- Key files: `utils.py` (71KB - contains many helpers)

**data/**
- Purpose: Data files, knowledge base, logs
- Contains: JSON, JSONL, TXT files
- Key files:
  - `knowledge_base.txt` - Bot knowledge
  - `style_guide.txt` - Response style
  - `qa_database.json` - Q&A pairs
  - `firebase_data.json` - Firebase credentials
  - `conversation_log.jsonl` - Chat history
  - `analytics_events.jsonl` - Analytics data
  - `reports_log.jsonl` - Daily reports

**dashboard/src/components/**
- Purpose: Reusable React components
- Contains: Auth, Layout, Common components
- Key files:
  - `Auth/ProtectedRoute.js` - Route protection
  - `Auth/PermissionGate.js` - Permission checking
  - `Layout/Sidebar.js` - Navigation sidebar
  - `Layout/Header.js` - App header
  - `Common/LoadingScreen.js` - Loading state
  - `BotInstructionsTab.js` - Bot instructions editor
  - `TrainingFileEditor.js` - Training file editor

**dashboard/src/pages/**
- Purpose: Page-level React components
- Contains: Main dashboard views
- Key files:
  - `Dashboard.js` - Overview dashboard
  - `LiveChat.js` - Live chat interface (73KB)
  - `ChatHistory.js` - Conversation history
  - `SmartMessaging.js` - Bulk messaging (64KB)
  - `Settings.js` - App settings
  - `Training.js` - Bot training
  - `Analytics.js` - Analytics charts
  - `Testing.js` - API testing

**dashboard/src/contexts/**
- Purpose: React context providers
- Contains: Auth and permissions contexts
- Key files:
  - `AuthContext.js` - Authentication state
  - `PermissionsContext.js` - User permissions

## Key File Locations

**Entry Points:**
- `main.py` - Backend application entry
- `dashboard/src/index.js` - Dashboard React entry
- `dashboard/src/App.js` - React app router

**Configuration:**
- `config.py` - Python configuration and state
- `requirements.txt` - Python dependencies
- `dashboard/package.json` - Dashboard dependencies
- `.env` / `.env.example` - Environment variables
- `data/firebase_data.json` - Firebase credentials

**Core Logic:**
- `services/chat_response_service.py` - AI response generation
- `modules/webhook_handlers.py` - Webhook processing
- `modules/event_handlers.py` - Event routing
- `handlers/text_handlers_respond.py` - Text response logic

**Testing:**
- `test_montymobile.py` - MontyMobile API tests
- `test_live_chat_simple.py` - Live chat tests
- `routes/testing_routes.py` - Test API endpoints
- `dashboard/src/pages/Testing.js` - Dashboard test UI

**Documentation:**
- `CLAUDE_MEMORY.md` - Development notes
- `bot-chat.md` - Bot conversation examples
- `.env.example` - Environment setup guide

## Naming Conventions

**Files:**
- snake_case.py: Python modules (e.g., `chat_response_service.py`)
- PascalCase.js: React components (e.g., `LiveChat.js`)
- lowercase.json: Data files (e.g., `qa_database.json`)
- lowercase.txt: Text content files (e.g., `knowledge_base.txt`)

**Directories:**
- lowercase: All directories (handlers, services, modules)
- Plural for collections: handlers/, services/, utils/

**Special Patterns:**
- `*_api.py`: API endpoint modules
- `*_service.py`: Service layer modules
- `*_handlers.py`: Message handler modules
- `*_adapter.py`: WhatsApp adapter implementations

## Where to Add New Code

**New API Endpoint:**
- Primary code: `modules/{feature}_api.py`
- Register in: `main.py` (import the module)
- Tests: `routes/testing_routes.py` or new test file

**New Message Handler:**
- Implementation: `handlers/{type}_handlers.py`
- Registration: Add import in `main.py`, route in `modules/event_handlers.py`
- Tests: Manual test scripts in root

**New Service:**
- Implementation: `services/{name}_service.py`
- Usage: Import in handlers or API modules

**New WhatsApp Provider:**
- Adapter: `services/whatsapp_adapters/{provider}_adapter.py`
- Factory: Update `services/whatsapp_adapters/whatsapp_factory.py`

**New Dashboard Page:**
- Component: `dashboard/src/pages/{Name}.js`
- Route: Add in `dashboard/src/App.js`
- Navigation: Update `dashboard/src/components/Layout/Sidebar.js`

**New Dashboard Component:**
- Implementation: `dashboard/src/components/{Category}/{Name}.js`
- Usage: Import in pages

## Special Directories

**venv/**
- Purpose: Python virtual environment
- Source: Created via `python -m venv venv`
- Committed: No (in .gitignore)

**__pycache__/**
- Purpose: Python bytecode cache
- Source: Auto-generated by Python
- Committed: No (in .gitignore)

**dashboard/node_modules/**
- Purpose: Node.js dependencies
- Source: Generated by `npm install`
- Committed: No (in .gitignore)

**dashboard/build/**
- Purpose: Production React build
- Source: Generated by `npm run build`
- Committed: No (typically in .gitignore)

---

*Structure analysis: 2026-01-19*
*Update when directory structure changes*
