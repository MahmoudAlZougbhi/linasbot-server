# -*- coding: utf-8 -*-
"""
Core module: FastAPI app setup, imports, and configuration
This module handles the core initialization of the FastAPI application
and all essential imports required by the bot.
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import datetime

# Try to import pydub, handle gracefully if it fails
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError as e:
    print("Warning: pydub not available - " + str(e))
    print("Voice message processing will be disabled")
    PYDUB_AVAILABLE = False
    AudioSegment = None

# Load environment variables from .env file
load_dotenv()

# Import configuration
import config
from config import FFMPEG_PATH, WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID

# Import Firebase utilities
from utils.utils import initialize_firestore, get_firestore_db, set_human_takeover_status

# Import handlers
from handlers.text_handlers import handle_message, start_command
from handlers.photo_handlers import handle_photo_message
from handlers.voice_handlers import handle_voice_message
from handlers.training_handlers import start_training_mode, exit_training_mode

# Import services
from services.api_integrations import generate_daily_report_command, log_report_event
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

# Ensure FFMPEG is configured for pydub
if PYDUB_AVAILABLE and AudioSegment and FFMPEG_PATH:
    AudioSegment.converter = FFMPEG_PATH

# Initialize FastAPI app
app = FastAPI()

# Configure CORS middleware to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React development server
        "http://127.0.0.1:3000",
        "http://localhost:8003",  # Backend (for dashboard serving)
        "http://127.0.0.1:8003",
        "https://linasaibot.com",  # Production domain
        "http://linasaibot.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Initialize HTTP client for WhatsApp API calls (Meta provider only)
# Avoids URL with "None" when Meta credentials are missing
_phone_id = (str(WHATSAPP_PHONE_NUMBER_ID).strip() if WHATSAPP_PHONE_NUMBER_ID else "") or "0"
WHATSAPP_API_BASE_URL = "https://graph.facebook.com/v19.0/{}".format(_phone_id)
whatsapp_api_client = httpx.AsyncClient(base_url=WHATSAPP_API_BASE_URL)

# Dashboard statistics tracking
dashboard_stats = {
    "total_messages": 0,
    "active_users": set(),
    "response_times": [],
    "conversations": []
}

# Global variable to capture bot responses for dashboard
dashboard_bot_responses = {}
