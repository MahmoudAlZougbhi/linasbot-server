"""Side-effect import: load .env / .env.local before config is imported."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
_env_local = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.local")
if os.path.isfile(_env_local):
    load_dotenv(_env_local)

ENV_LOADED = True
