"""
Main entry point for Lina's Laser AI Bot
Loads all modular components and starts the FastAPI server.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
from modules.core import app

# Must import before config/modules.core so legacy data is migrated first.
from storage.migrate_bootstrap import MIGRATED as _DATA_MIGRATED
from utils.utils import initialize_firestore

if not _DATA_MIGRATED:
    raise RuntimeError("storage migrate bootstrap did not run")

# Serve dashboard static files and SPA
DASHBOARD_BUILD_PATH = os.path.join(os.path.dirname(__file__), "dashboard", "build")
INDEX_HTML_PATH = os.path.join(DASHBOARD_BUILD_PATH, "index.html")
LIVE_CHAT_ANDROID_APK_PATH = os.path.join(
    os.path.dirname(__file__),
    "mobile",
    "releases",
    "linas-live-chat-android.apk",
)

if os.path.exists(DASHBOARD_BUILD_PATH):
    # Mount static files (js, css, etc.)
    app.mount("/static", StaticFiles(directory=os.path.join(DASHBOARD_BUILD_PATH, "static")), name="static")

# Import all modules to register routes and events (must run before SPA catch-all).
import modules.analytics_api  # noqa: E402, F401
import modules.auth_api  # noqa: E402, F401
import modules.chat_history_api  # noqa: E402, F401
import modules.cm_api  # noqa: E402, F401
import modules.cm_faq_api  # noqa: E402, F401
import modules.cm_setup_api  # noqa: E402, F401
import modules.content_files_api  # noqa: E402, F401
import modules.creative_api  # noqa: E402, F401
import modules.dashboard_api  # noqa: E402, F401
import modules.entitlements_api  # noqa: E402, F401
import modules.event_handlers  # noqa: E402, F401
import modules.feedback_api  # noqa: E402, F401
import modules.flow_api  # noqa: E402, F401
import modules.instructions_api  # noqa: E402, F401
import modules.live_chat_api  # noqa: E402, F401
import modules.local_qa_api  # noqa: E402, F401
import modules.media_api  # noqa: E402, F401
import modules.meta_compliance  # noqa: E402, F401
import modules.meta_connections_api  # noqa: E402, F401
import modules.meta_instagram_login_webhook  # noqa: E402, F401
import modules.meta_messaging_webhook  # noqa: E402, F401
import modules.meta_social_posts_api  # noqa: E402, F401
import modules.mobile_auth_api  # noqa: E402, F401
import modules.mobile_integrations_api  # noqa: E402, F401
import modules.owner_ai_api  # noqa: E402, F401
import modules.platform_api  # noqa: E402, F401
import modules.qa_api  # noqa: E402, F401
import modules.queue_api  # noqa: E402, F401
import modules.schedule_api  # noqa: E402, F401
import modules.settings_api  # noqa: E402, F401
import modules.smart_messaging_api  # noqa: E402, F401
import modules.store_iap_api  # noqa: E402, F401
import modules.training_files_api  # noqa: E402, F401
import modules.wallet_api  # noqa: E402, F401
import modules.webhook_handlers  # noqa: E402, F401
import modules.whatsapp_adapters  # noqa: E402, F401


@app.get("/downloads/live-chat-android.apk")
async def download_live_chat_android_apk(request: Request) -> FileResponse:
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
    async def serve_dashboard_root() -> FileResponse:
        return FileResponse(INDEX_HTML_PATH)

    @app.get("/{full_path:path}")
    async def serve_dashboard_spa(full_path: str) -> FileResponse:
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
            print(
                "📊 Dashboard: Run 'cd dashboard && npm run build' then refresh, or use 'npm start' for dev (port 3000)"
            )
    except Exception as e:
        print(f"❌ Startup error: {e}")
        import traceback

        traceback.print_exc()
        raise

    import uvicorn

    use_reload = getattr(config, "is_local_env", lambda: False)()
    if use_reload:
        print("🔄 Local mode: auto-reload enabled")
    # Uvicorn's default access log includes the raw query string. Nginx provides
    # path-only request telemetry, so backend access logging stays disabled to
    # ensure webhook verification tokens and other query secrets are never stored.
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=use_reload, access_log=False)
