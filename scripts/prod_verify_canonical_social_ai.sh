#!/usr/bin/env bash
# Server-side canonical Linas AI check for Instagram/Messenger path (no Meta send).
# Never prints OpenAI secrets or full model response text.
set -euo pipefail

cd /opt/linasbot
APP_DIR="/opt/linasbot"
if [ -f /opt/linasbot/linaslaserbot-2.7.22/main.py ]; then
  APP_DIR="/opt/linasbot/linaslaserbot-2.7.22"
fi
cd "$APP_DIR"
# shellcheck disable=SC1091
source venv/bin/activate

export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

python3 - <<'PY'
import asyncio
import hashlib
import os
import re
from pathlib import Path

# Load EnvironmentFile the same way the service does.
for env_path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env"), Path(".env")):
    if not env_path.exists():
        continue
    for line in env_path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import config
from openai import AsyncOpenAI
from services.chat_response_service import ORCHESTRATION_MODEL, FINAL_RESPONSE_MODEL
from services.social_contact_routing import route_social_contact_request

key = (config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY") or "").strip()
if not key:
    raise SystemExit("[canonical-ai-verify] OPENAI_API_KEY missing in process config")

fp = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
print(f"[canonical-ai-verify] model_orchestration={ORCHESTRATION_MODEL}")
print(f"[canonical-ai-verify] model_final={FINAL_RESPONSE_MODEL}")
print(f"[canonical-ai-verify] api=chat.completions.create")
print(f"[canonical-ai-verify] key_fp={fp}")

# 1) Direct OpenAI auth + model access on the exact orchestration model/path.
async def probe_openai():
    client = AsyncOpenAI(api_key=key)
    response = await client.chat.completions.create(
        model=ORCHESTRATION_MODEL,
        messages=[
            {"role": "system", "content": "Reply with a tiny JSON object only."},
            {"role": "user", "content": '{"ping":true}'},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    if not response.choices:
        raise RuntimeError("openai_empty_choices")
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("openai_empty_content")
    print(f"[canonical-ai-verify] openai_probe_ok=true content_len={len(content)}")

asyncio.run(probe_openai())

# 2) Deterministic social router must NOT ask branch for Hello.
ud = {
    "channel": "instagram",
    "meta_account_id": os.getenv("META_INSTAGRAM_ACCOUNT_ID") or "17841413184256533",
}
route = route_social_contact_request("Hello", ud, None, "en")
if route is not None:
    raise SystemExit("[canonical-ai-verify] social router incorrectly answered Hello")
print("[canonical-ai-verify] social_router_hello=none")

# 3) Canonical handle_message path with Instagram channel (capture only; no Graph send).
import config as cfg
from handlers.text_handlers import handle_message
from handlers.text_handlers_firestore import _delayed_processing_tasks

user_id = "instagram:internal_openai_key_verify"
cfg.user_data_whatsapp[user_id] = {
    "user_preferred_lang": "en",
    "initial_user_query_to_process": None,
    "awaiting_human_handover_confirmation": False,
    "current_conversation_id": None,
    "channel": "instagram",
    "social_sender_id": "internal_openai_key_verify",
    "meta_account_id": ud["meta_account_id"],
    "phone_number": f"room:{user_id}",
    "_dashboard_test_simulation": True,
}
cfg.user_names[user_id] = "Internal Verify"
captured = []

async def send_message(_uid, message_text=None, image_url=None, audio_url=None):
    if message_text:
        captured.append(str(message_text))
    return {"success": True}

async def send_action(_uid):
    return {"success": True}

async def run_canonical():
    await handle_message(
        user_id=user_id,
        user_name=cfg.user_names[user_id],
        user_input_text="Hello",
        user_data=cfg.user_data_whatsapp[user_id],
        send_message_func=send_message,
        send_action_func=send_action,
        skip_firestore_save=True,
        message_combine_delay=0.0,
    )
    task = _delayed_processing_tasks.get(user_id)
    if task:
        try:
            await task
        finally:
            _delayed_processing_tasks.pop(user_id, None)

asyncio.run(run_canonical())

# Cleanup in-memory test session state.
cfg.user_data_whatsapp.pop(user_id, None)
cfg.user_names.pop(user_id, None)
cfg.user_gender.pop(user_id, None)

if not captured:
    raise SystemExit("[canonical-ai-verify] canonical_ai_empty_response")

joined = "\n".join(captured)
branch_markers = (
    "Which branch do you prefer",
    "أي فرع بدك",
    "Quelle agence préférez-vous",
)
if any(m in joined for m in branch_markers):
    raise SystemExit("[canonical-ai-verify] branch_question_for_hello")

# Do not print response body; only non-secret metrics.
print(f"[canonical-ai-verify] canonical_ai_ok=true replies={len(captured)} chars={len(joined)}")
print("[canonical-ai-verify] SUCCESS")
PY
