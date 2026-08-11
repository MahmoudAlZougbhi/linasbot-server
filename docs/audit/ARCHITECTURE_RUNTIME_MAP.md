# Architecture / runtime map (W00)

**Baseline SHA:** `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26`

## Entrypoints
- **API server:** `main.py` (FastAPI) — mounts routers, static `dashboard/build`, SPA fallback
- **Startup/shutdown:** `modules/event_handlers.py`
- **Mobile app:** `mobile/linas-ai` (Expo)
- **Landing/public web:** `dashboard/src` public routes + compliance HTML modules

## Major runtime surfaces
| Surface | Primary paths |
|---------|----------------|
| Auth (dashboard cookies) | `modules/auth_api.py`, `modules/api_security.py` |
| Auth (mobile bearer) | `modules/mobile_auth_api.py` |
| Live Chat API | `modules/live_chat_api.py`, `services/live_chat_service.py` |
| Meta social webhooks | `modules/meta_messaging_webhook.py`, `services/meta_messaging.py` |
| WhatsApp legacy webhook | `modules/webhook_handlers.py` |
| WhatsApp Cloud | `modules/whatsapp_cloud_webhook.py`, `services/whatsapp_cloud/*` |
| CM | `modules/cm_*`, `services/cm/*` |
| Booking | `services/booking/*`, `services/appointment_scheduler.py` |
| Wallet/billing | `modules/wallet_api.py`, Stripe/IAP services |
| Workers/schedulers | APScheduler jobs in `event_handlers` / dispatcher services |

## CI / deploy
- `.github/workflows/*` quality, security, mobile, WhatsApp apply workflows
- Docker uses root `requirements.txt` (stale `backend/requirements.txt` flagged for review)

## Data
- Runtime durable root: `LINASBOT_DATA_ROOT` / `storage/persistent_storage.py`
- Tracked `data/*` includes seeds and some dumps (review in later waves)
