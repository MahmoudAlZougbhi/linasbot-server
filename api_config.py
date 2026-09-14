# api_config.py — no clinic BOC defaults. BOC is not in SaaS.
import os

LINASLASER_API_BASE_URL = (os.getenv("EXTERNAL_API_BASE_URL") or os.getenv("LINASLASER_API_BASE_URL") or "").strip()
LINASLASER_API_TOKEN = os.getenv("EXTERNAL_API_TOKEN") or os.getenv("LINASLASER_API_TOKEN")
