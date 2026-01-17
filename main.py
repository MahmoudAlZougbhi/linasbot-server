# -*- coding: utf-8 -*-
"""
Main entry point for Lina's Laser AI Bot
Loads all modular components and starts the FastAPI server.
"""

from modules.core import app
from utils.utils import initialize_firestore
import config

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

if __name__ == "__main__":
    # Initialize Firebase and load bot assets
    initialize_firestore()
    config.load_bot_assets()
    config.load_training_data()
    print("🤖 Lina's Laser AI Bot is ready!")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
