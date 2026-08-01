# -*- coding: utf-8 -*-
"""
Main entry point for Lina's Laser AI Bot
Loads all modular components and starts the FastAPI server.
"""

import os

# Run migration first: copy data from project/data/ to persistent dir if needed.
# Must run before any service reads data (e.g. config.load_bot_assets).
from storage.persistent_storage import migrate_from_legacy
migrate_from_legacy()

from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from modules.core import app
from utils.utils import initialize_firestore
import config

# Serve dashboard static files and SPA
DASHBOARD_BUILD_PATH = os.path.join(os.path.dirname(__file__), "dashboard", "build")
INDEX_HTML_PATH = os.path.join(DASHBOARD_BUILD_PATH, "index.html") if DASHBOARD_BUILD_PATH else None
LIVE_CHAT_ANDROID_APK_PATH = os.path.join(
    os.path.dirname(__file__),
    "mobile",
    "releases",
    "linas-live-chat-android.apk",
)

if os.path.exists(DASHBOARD_BUILD_PATH):
    # Mount static files (js, css, etc.)
    app.mount("/static", StaticFiles(directory=os.path.join(DASHBOARD_BUILD_PATH, "static")), name="static")

# Import all modules to register routes and events
import modules.event_handlers
import modules.webhook_handlers
import modules.meta_messaging_webhook
import modules.whatsapp_adapters
import modules.dashboard_api
import modules.qa_api
import modules.local_qa_api  # NEW: Local JSON-based Q&A
import modules.instructions_api  # NEW: Bot Instructions Management
import modules.training_files_api  # Training files (Knowledge Base, Style Guide, Price List)
import modules.feedback_api
import modules.live_chat_api
import modules.chat_history_api
import modules.analytics_api
import modules.smart_messaging_api
import modules.settings_api
import modules.media_api  # Audio proxy for voice message playback
import modules.auth_api  # Dashboard user authentication
import modules.content_files_api  # Content Files: Knowledge, Price, Style (CRUD + dynamic retrieval)
import modules.flow_api  # Activity Flow: User ↔ Bot ↔ AI transparency

@app.get("/downloads/live-chat-android.apk")
async def download_live_chat_android_apk(request: Request):
    from modules.api_security import user_has_permission
    from services.dashboard_session_service import SESSION_COOKIE_NAME, session_service

    session = session_service.get_valid_session(request.cookies.get(SESSION_COOKIE_NAME))
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user_has_permission(session, "liveChat"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not os.path.exists(LIVE_CHAT_ANDROID_APK_PATH):
        raise HTTPException(status_code=404, detail="APK not found")
    return FileResponse(
        LIVE_CHAT_ANDROID_APK_PATH,
        media_type="application/vnd.android.package-archive",
        filename="linas-live-chat-android.apk",
    )

# Serve dashboard SPA (index.html for / and all non-API routes) - must be after API routes
if os.path.exists(DASHBOARD_BUILD_PATH) and os.path.exists(INDEX_HTML_PATH):
    @app.get("/")
    async def serve_dashboard_root():
        return FileResponse(INDEX_HTML_PATH)

    @app.get("/{full_path:path}")
    async def serve_dashboard_spa(full_path: str):
        # Don't serve index.html for API or static paths
        if (
            full_path.startswith("api/")
            or full_path.startswith("static/")
            or full_path.startswith("downloads/")
            or full_path == "webhook"
            or full_path.startswith("webhook/")
        ):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(INDEX_HTML_PATH)

if __name__ == "__main__":
    try:
        # Initialize Firebase and load bot assets
        initialize_firestore()
        config.load_bot_assets()
        config.load_training_data()
        print("🤖 Lina's Laser AI Bot is ready!")
        if os.path.exists(INDEX_HTML_PATH):
            print("📊 Dashboard: http://localhost:8003/")
        else:
            print("📊 Dashboard: Run 'cd dashboard && npm run build' then refresh, or use 'npm start' for dev (port 3000)")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        import traceback
        traceback.print_exc()
        raise

    import uvicorn
    use_reload = getattr(config, "is_local_env", lambda: False)()
    if use_reload:
        print("🔄 Local mode: auto-reload enabled")
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=use_reload)
