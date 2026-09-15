# api_config.py — no clinic BOC defaults. BOC is not in SaaS.
import os

EXTERNAL_API_BASE_URL = (os.getenv("EXTERNAL_API_BASE_URL") or "").strip()
EXTERNAL_API_TOKEN = os.getenv("EXTERNAL_API_TOKEN")
