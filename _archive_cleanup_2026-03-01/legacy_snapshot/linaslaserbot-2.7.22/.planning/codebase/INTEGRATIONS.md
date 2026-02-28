# External Integrations

**Analysis Date:** 2026-01-19

## APIs & External Services

**AI/Chat:**
- OpenAI API - AI-powered chat responses
  - SDK/Client: openai 1.3.0 (`requirements.txt`)
  - Auth: API key in `OPENAI_API_KEY` env var
  - Usage: Chat completions, vision for photo analysis

**WhatsApp Messaging (Multi-Provider):**
- MontyMobile (Primary) - WhatsApp Business messaging
  - Integration: Custom adapter `services/whatsapp_adapters/montymobile_adapter.py`
  - Auth: `MONTYMOBILE_API_KEY`, `MONTYMOBILE_TENANT_ID`, `MONTYMOBILE_API_ID`, `MONTYMOBILE_SOURCE_NUMBER`
  - Base URL: `https://omni-apis.montymobile.com`

- Meta Cloud API (Alternative)
  - Integration: Custom adapter `services/whatsapp_adapters/meta_adapter.py`
  - Auth: `WHATSAPP_API_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`
  - Base URL: `https://graph.facebook.com/v19.0/`

- 360Dialog (Alternative)
  - Integration: Custom adapter `services/whatsapp_adapters/dialog360_adapter.py`
  - Auth: `DIALOG360_API_KEY`, `DIALOG360_SANDBOX`

- Qiscus (Deprecated)
  - Integration: Custom adapter `services/whatsapp_adapters/qiscus_adapter.py`
  - Auth: `QISCUS_SDK_SECRET`, `QISCUS_APP_CODE`, `QISCUS_SENDER_EMAIL`

**Business API:**
- Lina's Laser Clinic API - Appointment scheduling, service info
  - Integration: REST API via httpx (`services/api_integrations.py`)
  - Auth: Bearer token in `LINASLASER_API_TOKEN`
  - Base URL: `LINASLASER_API_BASE_URL` env var

## Data Storage

**Databases:**
- Firebase Firestore - Primary data store for conversations, metrics
  - Connection: Service account JSON at `data/firebase_data.json`
  - Client: firebase-admin 6.1.0 + google-cloud-firestore 2.11.1
  - Collections: `conversations`, `dashboardMetrics`

**File Storage:**
- Local JSON/JSONL files - Bot knowledge, analytics, logs
  - `data/knowledge_base.txt` - Core bot knowledge
  - `data/style_guide.txt` - Response style guide
  - `data/qa_database.json` - Q&A pairs
  - `data/conversation_log.jsonl` - Conversation history
  - `data/analytics_events.jsonl` - Analytics events
  - `data/reports_log.jsonl` - Daily reports

**Caching:**
- In-memory caching via Python defaultdict (`config.py`)
  - User context, gender, names, booking state
  - No external cache service (Redis/Memcached)

## Authentication & Identity

**Dashboard Auth:**
- Custom authentication - Login/Register in dashboard
  - Implementation: `dashboard/src/contexts/AuthContext.js`
  - Token storage: React context (client-side)
  - Protected routes: `dashboard/src/components/Auth/ProtectedRoute.js`

**Bot Verification:**
- WhatsApp webhook verification token - `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- No OAuth integrations

## Monitoring & Observability

**Error Tracking:**
- Console logging - No external error tracking service
- Local logs directory: `logs/`

**Analytics:**
- Custom analytics service - `services/analytics_events.py`
  - Events stored in `data/analytics_events.jsonl`
  - Dashboard visualization: `dashboard/src/pages/Analytics.js`
- Prometheus metrics available (optional) - prometheus-client 0.19.0

**Logs:**
- Python stdout/stderr via uvicorn
- Local file: `backend.log`

## CI/CD & Deployment

**Hosting:**
- Manual deployment - No automated CI/CD detected
- Deploy script: `deploy.sh`
- Docker available: `docker-compose.yml`

**CI Pipeline:**
- Not detected (no `.github/workflows/` or similar)

## Environment Configuration

**Development:**
- Required env vars: See `.env.example` for full list
- Core: `OPENAI_API_KEY`, `MONTYMOBILE_*`, Firebase credentials
- Secrets location: `.env` (gitignored)
- Testing mode: `TESTING_MODE=true` disables Firebase saves

**Production:**
- Same env vars as development
- `gunicorn 21.2.0` available for production server
- Dashboard builds to static files via `npm run build`

## Webhooks & Callbacks

**Incoming:**
- WhatsApp webhooks - `/webhook/whatsapp` (multiple providers)
  - Verification: Provider-specific (signature validation)
  - Events: Text messages, voice messages, photos, status updates
  - Handler: `modules/webhook_handlers.py`

**Outgoing:**
- Daily reports to trainer - Scheduled via APScheduler
  - Destination: `TRAINER_WHATSAPP_NUMBER`
  - Events: Daily analytics summary

---

*Integration audit: 2026-01-19*
*Update when adding/removing external services*
