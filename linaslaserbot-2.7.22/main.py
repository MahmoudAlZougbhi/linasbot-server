# -*- coding: utf-8 -*-
"""
Main entry point for Lina's Laser AI Bot
Loads all modular components and starts the FastAPI server.
"""

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from modules.core import app
from utils.utils import initialize_firestore
import config

# Serve dashboard static files
DASHBOARD_BUILD_PATH = os.path.join(os.path.dirname(__file__), "dashboard", "build")
if os.path.exists(DASHBOARD_BUILD_PATH):
    # Mount static files (js, css, etc.)
    app.mount("/static", StaticFiles(directory=os.path.join(DASHBOARD_BUILD_PATH, "static")), name="static")

# Import all modules to register routes and events
import modules.event_handlers
import modules.webhook_handlers
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

if __name__ == "__main__":
    try:
        # Initialize Firebase and load bot assets
        initialize_firestore()
        config.load_bot_assets()
        config.load_training_data()
        print("🤖 Lina's Laser AI Bot is ready!")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        import traceback
        traceback.print_exc()
        raise

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
