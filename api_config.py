# data/api_config.py
import os

# Base URL for the LinasLaser Agent API (calendar/CRM/customer APIs)
# Use EXTERNAL_API_BASE_URL in .env.local for local; production uses LINASLASER_API_BASE_URL.
# Example: https://boc-lb.com/agent/
LINASLASER_API_BASE_URL = os.getenv("EXTERNAL_API_BASE_URL") or os.getenv("LINASLASER_API_BASE_URL", "https://boc-lb.com/agent/")

# API Token for the external API (tenant/clinic access)
# Use EXTERNAL_API_TOKEN in .env.local for local; production uses LINASLASER_API_TOKEN.
LINASLASER_API_TOKEN = os.getenv("EXTERNAL_API_TOKEN") or os.getenv("LINASLASER_API_TOKEN")

# Simple check to ensure the token is present during development/testing
if not LINASLASER_API_TOKEN:
    print("❌ Warning: LINASLASER_API_TOKEN environment variable is not set. The bot will not be able to access the LinasLaser API features.")