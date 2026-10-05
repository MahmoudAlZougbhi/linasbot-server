"""Copy Firestore documents into Postgres in batches of 40.

Stops on quota exhaustion and writes a resume cursor. The application process
does not import this script.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BATCH = 40
APP = "artifacts/linas-ai-bot-backend"


def _state_path() -> Path:
    raw = os.getenv("LINAS_FIRESTORE_COPY_STATE") or "/tmp/linas-firestore-copy.json"
    return Path(raw)


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"cursors": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _client() -> Any:
    from google.cloud import firestore
    from google.oauth2 import service_account

    key = os.environ["FIRESTORE_SERVICE_ACCOUNT_KEY_PATH"]
    creds = service_account.Credentials.from_service_account_file(key)
    return firestore.Client(credentials=creds, project=creds.project_id)


def _project_thread(session: Any, conversation_id: str, data: dict[str, Any]) -> None:
    from sqlalchemy import text

    tenant_id = str(data.get("tenant_id") or "").strip().lower()
    if not tenant_id:
        return
    stamp = data.get("last_message_at") or ""
    if not isinstance(stamp, str):
        stamp = getattr(stamp, "isoformat", lambda: str(stamp))()
    session.execute(
        text(
            """
            INSERT INTO linas_chat_threads (
                tenant_id, conversation_id, user_id, channel, conversation_state,
                last_message_at, last_message_text, user_name, user_phone,
                operator_id, unread_count, message_count
            ) VALUES (
                :tenant_id, :conversation_id, :user_id, :channel, :conversation_state,
                :last_message_at, :last_message_text, :user_name, :user_phone,
                :operator_id, :unread_count, :message_count
            )
            ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                last_message_at = excluded.last_message_at,
                last_message_text = excluded.last_message_text,
                message_count = excluded.message_count
            """
        ),
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "user_id": str(data.get("user_id") or ""),
            "channel": str(data.get("channel") or ""),
            "conversation_state": str(data.get("conversation_state") or "bot_active"),
            "last_message_at": stamp or "1970-01-01T00:00:00+00:00",
            "last_message_text": str(data.get("last_message_text") or "")[:500],
            "user_name": str(data.get("user_name") or ""),
            "user_phone": str(data.get("user_phone") or data.get("phone_clean") or ""),
            "operator_id": str(data.get("operator_id") or ""),
            "unread_count": int(data.get("unread_count") or 0),
            "message_count": int(data.get("message_count") or 0),
        },
    )


def _collection(db: Any, parent: str) -> Any:
    root = db.collection("artifacts").document("linas-ai-bot-backend")
    name = parent.rsplit("/", 1)[-1]
    return root.collection(name)


def _copy_collection(db: Any, session: Any, parent: str) -> int:
    from google.api_core.exceptions import ResourceExhausted
    from sqlalchemy import text

    state = _load_state()
    cursor = state["cursors"].get(parent)
    copied = 0
    while True:
        query = _collection(db, parent).order_by("__name__").limit(BATCH)
        if cursor:
            query = query.start_after([_collection(db, parent).document(cursor)])
        try:
            docs = list(query.stream(timeout=20, retry=None))
        except ResourceExhausted:
            state["blocked"] = "429"
            state["blocked_at"] = time.time()
            _save_state(state)
            print(f"copy_paused collection={parent} cursor={cursor or ''} reason=429")
            return copied
        if not docs:
            state["cursors"][parent] = ""
            state["done"] = state.get("done") or []
            if parent not in state["done"]:
                state["done"].append(parent)
            _save_state(state)
            print(f"copy_done collection={parent} rows={copied}")
            return copied
        for doc in docs:
            data = doc.to_dict() or {}
            path = f"{parent}/{doc.id}"
            session.execute(
                text(
                    """
                    INSERT INTO linas_documents (path, parent, doc_id, data_json, updated_at)
                    VALUES (:path, :parent, :doc_id, :data_json, :updated_at)
                    ON CONFLICT (path) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                    """
                ),
                {
                    "path": path,
                    "parent": parent,
                    "doc_id": doc.id,
                    "data_json": json.dumps(data, default=str),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
            cursor = doc.id
            copied += 1
            if parent.endswith("live_chat_index"):
                _project_thread(session, doc.id, data)
        session.commit()
        state["cursors"][parent] = cursor
        _save_state(state)
        print(f"copy_batch collection={parent} rows={copied} cursor={cursor}")
        if len(docs) < BATCH:
            state["done"] = state.get("done") or []
            if parent not in state["done"]:
                state["done"].append(parent)
            _save_state(state)
            return copied


def main() -> int:
    from db.session import whatsapp_session
    from services.persistence.document_store import DocumentClient

    db = _client()
    DocumentClient()
    parents = [
        f"{APP}/dashboard_users",
        f"{APP}/dashboard_sessions",
        f"{APP}/live_chat_index",
    ]
    total = 0
    with whatsapp_session(require=True) as session:
        for parent in parents:
            total += _copy_collection(db, session, parent)
    print(f"copy_total rows={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
