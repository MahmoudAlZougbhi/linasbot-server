"""Isolate Customer AI V10 live-cert. Call configure() before any app imports."""

from __future__ import annotations

import json
import os
from pathlib import Path

WT = Path("/Users/alzoughbi/linasbot-v10-resources-wt")
CERT = WT / "_live_cert"
DATA = CERT / "data"
OUT = CERT / "out"
ASSETS = CERT / "assets"
TENANT_ID = "v10_live_cert_store"
FAQ_AR_Q = "شو أوقات الدوام؟"
FAQ_EN_Q = "What are your opening hours?"
FAQ_AR_A = "بيروت من 10:00 إلى 20:00. أنطلياس من 11:00 إلى 19:00."
FAQ_EN_A = "Beirut 10:00–20:00. Antelias 11:00–19:00."

_KEY_CANDIDATES = (
    Path("/Users/alzoughbi/linasbot-v10-live-cert-wt/.secrets/openai_api_key"),
    WT / ".secrets" / "openai_api_key",
    Path("/Users/alzoughbi/linasbot-server/.secrets/openai_api_key"),
)


def looks_real_openai_key(value: str) -> bool:
    key = (value or "").strip()
    if not key.startswith("sk-") or len(key) < 40:
        return False
    lowered = key.lower()
    return "sk-test" not in lowered and "ci-not-real" not in lowered and "placeholder" not in lowered


def load_openai_key() -> str:
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if looks_real_openai_key(env):
        return env
    for path in _KEY_CANDIDATES:
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8").strip()
        if looks_real_openai_key(raw):
            return raw
    return ""


def configure() -> dict[str, Path]:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    qa_dir = DATA / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_file = qa_dir / "qa_pairs.jsonl"
    rows = [
        {
            "question": FAQ_AR_Q,
            "answer": FAQ_AR_A,
            "language": "ar",
            "category": "hours",
            "qa_group_id": "faq_hours",
            "revision": "7",
            "is_active": True,
        },
        {
            "question": FAQ_EN_Q,
            "answer": FAQ_EN_A,
            "language": "en",
            "category": "hours",
            "qa_group_id": "faq_hours",
            "revision": "7",
            "is_active": True,
        },
    ]
    qa_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    key = load_openai_key()
    if not key:
        raise SystemExit("openai_key_missing")
    db_path = DATA / "v10_live_cert.sqlite"
    os.environ.update(
        {
            "LINASBOT_DATA_ROOT": str(DATA),
            "OPENAI_API_KEY": key,
            "ENVIRONMENT": "local",
            "APP_MODE": "local",
            "CUSTOMER_AI_V10_RUNTIME": "true",
            "CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED": "true",
            "CUSTOMER_MEDIA_CONTEXT_ENABLED": "true",
            "CM_EMBEDDING_PROVIDER": "openai",
            "CM_EMBEDDING_MODEL": "text-embedding-3-small",
            "LINAS_WHATSAPP_ALLOW_SQLITE": "true",
            "LINAS_WHATSAPP_DATABASE_URL": f"sqlite:///{db_path}",
            "LINAS_BILLING_BACKEND": "file",
            "LINAS_AUTH_TOKEN_BACKEND": "file",
            "META_REGISTRY_BACKEND": "file",
            "DASHBOARD_AUTH_SECRET": "v10-live-cert-not-prod",
            "LINASLASER_API_BASE_URL": "https://example.invalid",
            "LINASLASER_API_TOKEN": "unused",
            "LINAS_CUSTOMER_RETRIEVAL_MODEL": "gpt-5.6-luna",
            "LINAS_CUSTOMER_ANSWER_MODEL": "gpt-5.6-terra",
            "MAX_CUSTOMER_RETRIEVAL_ROUNDS": "2",
            "CUSTOMER_DM_CONTEXT_WINDOW_HOURS": "1.5",
            "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
            "PYTHONPATH": str(WT),
        }
    )
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    return {"wt": WT, "data": DATA, "out": OUT, "assets": ASSETS, "db": db_path, "qa": qa_file}
