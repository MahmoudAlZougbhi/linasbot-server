# Persistent Storage Refactor – Implementation Summary

## Problem

Dashboard-managed data was stored inside the project directory (`data/`), so Git pull or rebuild reverted it to repository state. Affected: FAQ, knowledge files, style files, price list, smart messaging config, system settings.

## Solution

All runtime-managed data now lives under **`LINASBOT_DATA_ROOT`** (default: `/opt/linasbot_data/`), outside the project.

---

## New Directory Structure

```
/opt/linasbot_data/           # or LINASBOT_DATA_ROOT env var
├── qa/
│   ├── qa_pairs.jsonl
│   └── qa_database.json
├── content/
│   ├── knowledge_base.txt
│   ├── style_guide.txt
│   ├── price_list.txt
│   ├── knowledge_files/
│   ├── style_files/
│   └── price_files/
├── settings/
│   └── app_settings.json
└── smart_messaging/
    ├── message_templates.json
    ├── .message_templates.lock
    ├── sent_smart_messages.json
    ├── service_template_mapping.json
    ├── message_preview_queue.json
    ├── daily_template_dispatch_state.json
    ├── message_queue.json
    ├── appointment_fingerprints.json
    ├── template_activation_status.json
    ├── scheduled_messages_to_be_sent.json
    └── dry_run_messages.jsonl
```

---

## Files Changed

| File | Change |
|------|--------|
| **storage/persistent_storage.py** | **NEW** – Central paths + `migrate_from_legacy()` |
| **storage/__init__.py** | **NEW** – Exports |
| **main.py** | Call `migrate_from_legacy()` before other imports |
| **config.py** | Use `KNOWLEDGE_BASE_FILE`, `STYLE_GUIDE_FILE`, `PRICE_LIST_FILE` |
| **services/local_qa_service.py** | Use `QA_PAIRS_FILE` |
| **services/qa_manager_service.py** | Use `QA_DATABASE_FILE` |
| **modules/local_qa_api.py** | Use `QA_PAIRS_FILE` |
| **services/content_files_service.py** | Use `KNOWLEDGE_FILES_DIR`, etc. |
| **modules/content_files_api.py** | Use persistent paths in migrate-legacy |
| **modules/instructions_api.py** | Use `STYLE_GUIDE_FILE`, `CONTENT_DIR` |
| **modules/training_files_api.py** | Use `KNOWLEDGE_BASE_FILE`, `STYLE_GUIDE_FILE`, `PRICE_LIST_FILE`, `CONTENT_DIR` |
| **services/settings_service.py** | Use `APP_SETTINGS_FILE` |
| **services/smart_messaging.py** | Use persistent paths for templates, settings, mapping, sent messages |
| **services/message_preview_service.py** | Use `MESSAGE_PREVIEW_QUEUE_FILE`, `APP_SETTINGS_FILE`, `MESSAGE_TEMPLATES_FILE` |
| **services/template_schedule_service.py** | Use `APP_SETTINGS_FILE` |
| **services/daily_template_dispatcher.py** | Use `DAILY_TEMPLATE_DISPATCH_STATE_FILE`, `APP_SETTINGS_FILE` |
| **services/message_queue_service.py** | Use persistent paths for queue, fingerprints, settings, mapping |
| **services/scheduled_messages_collector.py** | Use `SCHEDULED_MESSAGES_FILE` |
| **modules/smart_messaging_api.py** | Use `MESSAGE_TEMPLATES_FILE`, `MESSAGE_TEMPLATES_LOCK_FILE` |
| **services/service_template_mapping_service.py** | Use `SERVICE_TEMPLATE_MAPPING_FILE`, `MESSAGE_TEMPLATES_FILE` |
| **modules/event_handlers.py** | Use `APP_SETTINGS_FILE` |
| **services/chat_response_service.py** | Use `APP_SETTINGS_FILE` |
| **services/bot_data_service.py** | Use `KNOWLEDGE_BASE_FILE`, `STYLE_GUIDE_FILE`, `PRICE_LIST_FILE` |
| **services/whatsapp_adapters/safe_send_adapter.py** | Use `DRY_RUN_MESSAGES_FILE` |
| **.env.example** | Document `LINASBOT_DATA_ROOT` |
| **.gitignore** | Ignore `linasbot_data/` (dev fallback) |

---

## Migration Logic

On first run, `migrate_from_legacy()`:

1. Creates `/opt/linasbot_data/qa/`, `content/`, `settings/`, `smart_messaging/`
2. For each file in `data/`: if it exists and the persistent path does **not** exist → copy
3. **Does not overwrite** existing production data
4. Runs at app startup (before `config.load_bot_assets()`)

---

## Deployment

1. **Production**
   - Ensure `/opt/linasbot_data/` exists and the app user has `rwx`
   - Optional: `LINASBOT_DATA_ROOT=/opt/linasbot_data` (default)
   - First deploy: migration copies from `data/` if present

2. **Development**
   - Set `LINASBOT_DATA_ROOT=./linasbot_data` to use project-local persistent data
   - `linasbot_data/` is gitignored

---

## API Contracts

All existing API endpoints and payloads are unchanged. Only storage paths changed.
