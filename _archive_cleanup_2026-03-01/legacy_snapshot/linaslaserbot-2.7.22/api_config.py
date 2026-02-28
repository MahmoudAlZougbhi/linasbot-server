# data/api_config.py
import os

# Base URL for the LinasLaser Agent API
# This is derived from the API Documentation PDF 
# Example: https://boc-lb.com/agent/
LINASLASER_API_BASE_URL = os.getenv("LINASLASER_API_BASE_URL", "https://boc-lb.com/agent/")

# API Token for accessing the LinasLaser Agent API
# This token determines which clinic's (tenant's) data is accessed [cite: 9]
# It must be provided by the system administration and stored as an environment variable for security.
LINASLASER_API_TOKEN = os.getenv("LINASLASER_API_TOKEN")

# Simple check to ensure the token is present during development/testing
if not LINASLASER_API_TOKEN:
    print("❌ Warning: LINASLASER_API_TOKEN environment variable is not set. The bot will not be able to access the LinasLaser API features.")