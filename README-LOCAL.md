# Local development environment (production-like)

This guide sets up a **local environment that behaves like production**: same external APIs (calendar/CRM/customer), no mocks. Outbound WhatsApp is controlled so you can test safely.

---

## 1. Configure environment

1. **Copy the example file**
   ```bash
   cp .env.local.example .env.local
   ```

2. **Edit `.env.local`**
   - Set **External API** (same as production):
     - `EXTERNAL_API_BASE_URL` – e.g. `https://boc-lb.com/agent/`
     - `EXTERNAL_API_TOKEN` – your API token  
     You can use `LINASLASER_API_BASE_URL` / `LINASLASER_API_TOKEN` instead; both are supported.
   - Set **local mode**: `APP_MODE=local` (or `ENV=development`).
   - **Sending safety** (pick one):
     - **Option 1 (recommended):** `ENABLE_SENDING=true` and set `LOCAL_ALLOWED_WHATSAPP_NUMBERS` to a comma-separated list of test/sandbox numbers. Only those numbers receive real messages.
     - **Option 2:** `ENABLE_SENDING=false` – no real sends; every outbound message is logged as “would send” to `data/dry_run_messages.jsonl` and shown in the dashboard as “Would send”.
   - Fill in your **WhatsApp provider** vars (e.g. MontyMobile) so the app can run; with `ENABLE_SENDING=false` or non-allowed numbers, messages are dry-run only.

---

## 2. Run the backend (with auto-reload)

From the project root:

```bash
python main.py
```

- With `APP_MODE=local` or `ENV=development`, the server runs with **auto-reload** (code changes restart the server).
- Backend listens on **http://localhost:8003**.
- You should see: `🔄 Local mode: auto-reload enabled` and `🤖 Lina's Laser AI Bot is ready!`.

---

## 3. Run the frontend (hot reload)

In a **second terminal**, from the project root:

```bash
cd dashboard
npm install
npm start
```

- Dev server runs at **http://localhost:3000** with hot reload.
- The dashboard is configured to call the backend at `http://localhost:8003` when the browser is on `localhost`.

---

## 4. Use the full dashboard

- Open **http://localhost:3000** in your browser.
- Log in if auth is enabled.
- **Smart Messaging**: counts and customer lists come from the real API (reminder_24h, post_session_feedback, missed_yesterday, 20-day follow-up, etc.). All categories and filters use live API data.
- Chat and test flows as usual; the backend calls the same external APIs as production.

---

## 5. Verify API calls (logs)

- **Backend terminal**: Watch for lines like `API Call: get_branches`, `get_customer_appointments`, etc. These show real requests to `EXTERNAL_API_BASE_URL`.
- **Optional**: Add temporary `print` or logging in `services/api_integrations.py` or `services/smart_messaging_customers_service.py` to confirm request/response payloads.

---

## 6. Verify sending safety

- **Dry-run (`ENABLE_SENDING=false`)**  
  - Send a test (e.g. trigger a smart message or use a test endpoint).  
  - You should see in the backend log: `📋 [DRY-RUN] Would send ...` and entries in `data/dry_run_messages.jsonl`.  
  - In the dashboard, messages appear with status **“Would send”** (amber) instead of “Sent”.

- **Sandbox list (`ENABLE_SENDING=true` + `LOCAL_ALLOWED_WHATSAPP_NUMBERS`)**  
  - Messages to numbers **in** the list are sent for real.  
  - Messages to numbers **not** in the list are treated as dry-run (logged, not sent, “Would send” in dashboard).

---

## Quick reference

| Task              | Command / location |
|-------------------|--------------------|
| Backend (reload)  | `python main.py` (from project root) |
| Frontend (hot)    | `cd dashboard && npm start` |
| Env overrides     | `.env.local` (after `.env`) |
| External API URL  | `EXTERNAL_API_BASE_URL` or `LINASLASER_API_BASE_URL` |
| External API auth | `EXTERNAL_API_TOKEN` or `LINASLASER_API_TOKEN` |
| Local mode        | `APP_MODE=local` or `ENV=development` |
| Dry-run log       | `data/dry_run_messages.jsonl` |
| Sent/would_send   | Dashboard Smart Messaging → Messages list |

---

## Production vs local

| Aspect            | Production        | Local (this setup)        |
|-------------------|-------------------|---------------------------|
| External APIs     | Same              | Same (via .env.local)    |
| Backend reload    | No                | Yes (when APP_MODE=local) |
| Frontend          | Built static      | Dev server (npm start)     |
| Outbound WhatsApp | All sends         | Sandbox list or dry-run   |

You can run the full flow locally against real APIs and only send real messages to allowed test numbers (or none when using dry-run).
