"""
Core module: FastAPI app setup, imports, and configuration
This module handles the core initialization of the FastAPI application
and all essential imports required by the bot.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FFMPEG_PATH, WHATSAPP_PHONE_NUMBER_ID
from modules.env_bootstrap import ENV_LOADED as _ENV_LOADED  # load .env before config
from services.sensitive_request_logging import install_sensitive_query_log_filter

if not _ENV_LOADED:
    raise RuntimeError("env bootstrap did not run")

# Uvicorn access logging is disabled at startup because its default request-line
# formatter includes raw query strings. This filter additionally protects
# application logs if code ever logs a request URL explicitly.
install_sensitive_query_log_filter()

# Try to import pydub, handle gracefully if it fails
try:
    from pydub import AudioSegment

    PYDUB_AVAILABLE = True
except ImportError as e:
    print("Warning: pydub not available - " + str(e))
    print("Voice message processing will be disabled")
    PYDUB_AVAILABLE = False
    AudioSegment = None

# Import Firebase utilities
# Import handlers

# Import services

# Ensure FFMPEG is configured for pydub
if PYDUB_AVAILABLE and AudioSegment and FFMPEG_PATH:
    AudioSegment.converter = FFMPEG_PATH

# Initialize FastAPI app (hide OpenAPI surfaces in production)
_env_name = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
_disable_docs = _env_name in {"prod", "production"} or os.getenv("DISABLE_API_DOCS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
app = FastAPI(
    docs_url=None if _disable_docs else "/docs",
    redoc_url=None if _disable_docs else "/redoc",
    openapi_url=None if _disable_docs else "/openapi.json",
)

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
        "https://www.linasaibot.com",
        "http://www.linasaibot.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
)

# Deny-by-default dashboard API auth (must be after CORS so preflight works)
from modules.api_security import DashboardAuthMiddleware  # noqa: E402

app.add_middleware(DashboardAuthMiddleware)

# Initialize HTTP client for WhatsApp API calls (Meta provider only)
# Avoids URL with "None" when Meta credentials are missing
_phone_id = (str(WHATSAPP_PHONE_NUMBER_ID).strip() if WHATSAPP_PHONE_NUMBER_ID else "") or "0"
WHATSAPP_API_BASE_URL = f"https://graph.facebook.com/v19.0/{_phone_id}"
whatsapp_api_client = httpx.AsyncClient(base_url=WHATSAPP_API_BASE_URL)

# Dashboard statistics tracking
dashboard_stats: dict[str, Any] = {
    "total_messages": 0,
    "active_users": set(),
    "response_times": [],
    "conversations": [],
}

# Global variable to capture bot responses for dashboard
dashboard_bot_responses: dict[str, Any] = {}
