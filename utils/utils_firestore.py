"""Firestore client init (canonical utils.utils re-export)."""

from __future__ import annotations

import json
import os
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

# Global Firestore DB instance
_firestore_db = None
_firestore_init_done = False


def initialize_firestore() -> Any:
    """
    Initializes Firebase Admin SDK and Firestore client.
    This should be called once at application startup.
    """
    import time

    global _firestore_db, _firestore_init_done
    t0 = time.monotonic()

    def _elapsed() -> Any:
        return time.monotonic() - t0

    try:
        print("[auth:Firestore] initialize_firestore ENTRY t=0.00s", flush=True)

        # Check if Firebase Admin SDK is already initialized
        if not firebase_admin._apps:
            # Get the service account key path from environment
            service_account_key_path = os.getenv("FIRESTORE_SERVICE_ACCOUNT_KEY_PATH", "data/firebase_data.json")
            print(
                f"[auth:Firestore] step 1: key_path={service_account_key_path} exists={os.path.exists(service_account_key_path)} t={_elapsed():.3f}s",
                flush=True,
            )

            if not os.path.exists(service_account_key_path):
                print(f"❌ Firebase service account key file not found at: {service_account_key_path}")
                print("🔧 Firestore disabled - chat history won't be saved.")
                _firestore_db = None
                return

            # Load service account to log project config (no secrets)
            with open(service_account_key_path) as f:
                service_account = json.load(f)
            project_id = service_account.get("project_id", "?")
            storage_bucket = service_account.get("storageBucket")
            client_email = service_account.get("client_email", "?")
            print(
                f"[auth:Firestore] step 2: project_id={project_id} client_email={client_email} t={_elapsed():.3f}s",
                flush=True,
            )

            # Initialize Firebase Admin SDK with service account credentials
            cred = credentials.Certificate(service_account_key_path)
            print(f"[auth:Firestore] step 3: credentials.Certificate done t={_elapsed():.3f}s", flush=True)

            options = {}
            if storage_bucket:
                options["storageBucket"] = storage_bucket

            firebase_admin.initialize_app(cred, options)
            print(f"[auth:Firestore] step 4: firebase_admin.initialize_app done t={_elapsed():.3f}s", flush=True)
            if storage_bucket:
                print(f"📦 Storage bucket configured: {storage_bucket}")
        else:
            print(f"[auth:Firestore] Firebase Admin already initialized, skipping init t={_elapsed():.3f}s", flush=True)

        # Initialize Firestore client (lazy - no network until first op)
        _firestore_db = firestore.client()
        _firestore_init_done = True
        print(
            f"[auth:Firestore] step 5: firestore.client() done t={_elapsed():.3f}s (first network op will happen on first query)",
            flush=True,
        )
        print("✅ Firestore client initialized successfully!")

    except Exception as e:
        print(f"❌ ERROR initializing Firestore after {_elapsed():.3f}s: {e}")
        print("🔧 Firestore disabled - chat history won't be saved.")
        print("💡 To fix this:")
        print("   1. Go to: https://console.cloud.google.com/datastore/setup?project=linas-ai-bot")
        print("   2. Create a Firestore database in Native mode")
        print("   3. Or update the project ID in firebase_data.json")
        _firestore_db = None
        import traceback

        traceback.print_exc()


def get_firestore_db() -> Any:
    """Returns the initialized Firestore client instance."""
    if _firestore_db is None:
        print("[auth:Firestore] get_firestore_db: triggering initialize_firestore (lazy init)", flush=True)
        initialize_firestore()
    return _firestore_db
