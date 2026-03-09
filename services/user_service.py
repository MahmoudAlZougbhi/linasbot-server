"""
User Service for Dashboard Authentication
Handles Firestore operations for dashboard users with bcrypt password hashing
"""

import os
import threading
import time
import uuid
import bcrypt
from datetime import datetime
from typing import Optional, Dict, List, Any
from google.cloud.firestore_v1.base_query import FieldFilter
from utils.utils import get_firestore_db


class AuthBackendUnavailableError(RuntimeError):
    """Raised when auth storage (Firestore) is temporarily unavailable."""


class UserService:
    """Service for managing dashboard users in Firestore"""

    COLLECTION = "artifacts/linas-ai-bot-backend/dashboard_users"
    AUTH_QUERY_TIMEOUT_SECONDS = float(os.getenv("AUTH_QUERY_TIMEOUT_SECONDS", "6"))
    AUTH_WRITE_TIMEOUT_SECONDS = float(os.getenv("AUTH_WRITE_TIMEOUT_SECONDS", "5"))
    AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS = int(
        os.getenv("AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS", "21600")
    )

    def __init__(self):
        self._db = None
        self._last_lastlogin_write_at: Dict[str, float] = {}

    @property
    def db(self):
        """Lazy-load Firestore database connection"""
        if self._db is None:
            t0 = time.monotonic()
            print(f"[auth:user_service] db property: first access, calling get_firestore_db t=0.00s", flush=True)
            self._db = get_firestore_db()
            elapsed = time.monotonic() - t0
            print(f"[auth:user_service] db property: get_firestore_db returned in {elapsed:.3f}s (db is None: {self._db is None})", flush=True)
        return self._db

    @property
    def collection(self):
        """Get the dashboard_users collection reference"""
        t0 = time.monotonic()
        if not self.db:
            raise Exception("Firestore not initialized")
        coll = self.db.collection("artifacts").document("linas-ai-bot-backend").collection("dashboard_users")
        elapsed = time.monotonic() - t0
        if elapsed > 0.1:
            print(f"[auth:user_service] collection property: accessed in {elapsed:.3f}s", flush=True)
        return coll

    # ==========================================
    # Password Methods
    # ==========================================

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its bcrypt hash"""
        t0 = time.monotonic()
        print(f"[auth:_verify_password] entry t=0.00s", flush=True)
        try:
            result = bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
            elapsed = time.monotonic() - t0
            print(f"[auth:_verify_password] done in {elapsed:.3f}s", flush=True)
            return result
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"[auth:_verify_password] ERROR after {elapsed:.3f}s: {e}", flush=True)
            return False

    # ==========================================
    # CRUD Operations
    # ==========================================

    def create_user(self, user_data: Dict[str, Any], created_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new dashboard user

        Args:
            user_data: Dict with email, password, name, role, permissions, status
            created_by: ID of the user creating this account

        Returns:
            Created user data (without password)
        """
        # Validate required fields
        if not user_data.get('email'):
            raise ValueError("Email is required")
        if not user_data.get('password'):
            raise ValueError("Password is required")

        # Check if email already exists
        existing = self.get_user_by_email(user_data['email'])
        if existing:
            raise ValueError("Email already exists")

        # Generate user ID
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Build user document
        user_doc = {
            "id": user_id,
            "email": user_data['email'].lower().strip(),
            "password": self._hash_password(user_data['password']),
            "name": user_data.get('name') or (user_data.get('email') or 'user@unknown').split('@')[0],
            "role": user_data.get('role', 'viewer'),
            "permissions": user_data.get('permissions'),
            "status": user_data.get('status', 'active'),
            "lastLogin": None,
            "createdAt": now,
            "createdBy": created_by,
            "updatedAt": now
        }

        # Save to Firestore
        self.collection.document(user_id).set(
            user_doc,
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )
        print(f"Created dashboard user: {user_doc['email']} (ID: {user_id})")

        # Return without password
        return self._sanitize_user(user_doc)

    def _is_transient_firestore_error(self, e: Exception) -> bool:
        """Check if error is transient (quota, timeout, network) and worth retrying."""
        lowered = str(e).lower()
        return any(
            marker in lowered
            for marker in (
                "429",
                "quota",
                "resource exhausted",
                "deadline",
                "timed out",
                "timeout",
                "unavailable",
                "connection",
            )
        )

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email address (includes password for auth)"""
        t_start = time.monotonic()
        email_lower = (email or "").lower().strip()
        print(f"[auth:get_user_by_email] ENTRY for {email_lower} t=0.00s", flush=True)
        max_retries = 3
        last_exception = None

        for attempt in range(max_retries):
            try:
                # Access collection (lazy Firestore init - may block on first access)
                t1 = time.monotonic()
                print(f"[auth:get_user_by_email] attempt {attempt + 1}/{max_retries}, accessing self.collection t={t1 - t_start:.3f}s", flush=True)
                coll = self.collection
                print(f"[auth:get_user_by_email] collection accessed in {time.monotonic() - t1:.3f}s", flush=True)

                # Firestore query - direct email lookup
                query = coll.where(
                    filter=FieldFilter("email", "==", email_lower)
                ).limit(1)

                t2 = time.monotonic()
                print(f"[auth:get_user_by_email] query.stream() START t={t2 - t_start:.3f}s (FIRESTORE NETWORK OP - may block)", flush=True)
                docs = list(
                    query.stream(
                        timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )
                elapsed = time.monotonic() - t2
                print(f"[auth:get_user_by_email] query.stream() RETURNED in {elapsed:.3f}s, doc_count={len(docs)}", flush=True)

                if docs:
                    result = docs[0].to_dict()
                    print(f"[auth:get_user_by_email] USER_FOUND in {time.monotonic() - t_start:.3f}s", flush=True)
                    return result
                print(f"[auth:get_user_by_email] USER_NOT_FOUND in {time.monotonic() - t_start:.3f}s", flush=True)
                return None
            except Exception as e:
                last_exception = e
                elapsed = time.monotonic() - t_start
                is_transient = self._is_transient_firestore_error(e)
                print(
                    f"[auth:get_user_by_email] ERROR after {elapsed:.3f}s (attempt {attempt + 1}/{max_retries}): {e} (transient={is_transient})",
                    flush=True,
                )
                if is_transient and attempt < max_retries - 1:
                    delay = (attempt + 1) * 2  # 2s, 4s
                    print(f"[auth:get_user_by_email] retrying in {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise AuthBackendUnavailableError(str(e)) from e

        raise AuthBackendUnavailableError(str(last_exception)) from last_exception

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID (includes password for internal use)"""
        try:
            doc = self.collection.document(user_id).get(
                timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                retry=None,
            )
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"[auth:get_user_by_id] Error: {e}", flush=True)
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users (without passwords)"""
        try:
            docs = self.collection.stream(
                timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                retry=None,
            )
            users = []
            for doc in docs:
                user_data = doc.to_dict()
                users.append(self._sanitize_user(user_data))
            return users
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a user's profile

        Args:
            user_id: User ID to update
            updates: Dict of fields to update (name, role, permissions, status, password)

        Returns:
            Updated user data (without password)
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                raise ValueError("User not found")

            # Build update dict
            update_data = {
                "updatedAt": datetime.utcnow().isoformat()
            }

            # Allowed fields to update
            allowed_fields = ['name', 'role', 'permissions', 'status']
            for field in allowed_fields:
                if field in updates:
                    update_data[field] = updates[field]

            # Handle password update separately (hash it)
            if 'password' in updates and updates['password']:
                update_data['password'] = self._hash_password(updates['password'])

            # Check if we're demoting the last admin
            if 'role' in updates and updates['role'] != 'admin' and user['role'] == 'admin':
                admin_count = self.count_active_admins()
                if admin_count <= 1:
                    raise ValueError("Cannot demote the last admin")

            # Check if we're deactivating the last admin
            if 'status' in updates and updates['status'] != 'active' and user['role'] == 'admin' and user['status'] == 'active':
                admin_count = self.count_active_admins()
                if admin_count <= 1:
                    raise ValueError("Cannot deactivate the last admin")

            self.collection.document(user_id).update(
                update_data,
                timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
                retry=None,
            )

            # Get updated user
            updated_user = self.get_user_by_id(user_id)
            return self._sanitize_user(updated_user)

        except ValueError:
            raise
        except Exception as e:
            print(f"Error updating user: {e}")
            raise

    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user

        Args:
            user_id: User ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                raise ValueError("User not found")

            # Prevent deleting the last admin
            if user['role'] == 'admin' and user.get('status') == 'active':
                admin_count = self.count_active_admins()
                if admin_count <= 1:
                    raise ValueError("Cannot delete the last admin")

            self.collection.document(user_id).delete(
                timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
                retry=None,
            )
            print(f"Deleted dashboard user: {user['email']} (ID: {user_id})")
            return True

        except ValueError:
            raise
        except Exception as e:
            print(f"Error deleting user: {e}")
            raise

    # ==========================================
    # Authentication
    # ==========================================

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user with email and password.

        CRITICAL: Successful login must NOT depend on lastLogin update.
        lastLogin is best-effort only; Firestore write failures must not block auth.

        Returns:
            User data (without password) if authentication succeeds, None otherwise
        """
        t0 = time.monotonic()

        def _elapsed() -> float:
            return time.monotonic() - t0

        email_norm = (email or "").strip().lower()
        print(f"[auth:authenticate] 1. ENTRY t=0.00s for {email_norm}", flush=True)

        # Step 1: Firestore user lookup (may trigger lazy db init)
        print(f"[auth:authenticate] 2. USER_LOOKUP_START t={_elapsed():.3f}s", flush=True)
        user = self.get_user_by_email(email_norm)
        print(f"[auth:authenticate] 3. USER_LOOKUP_END t={_elapsed():.3f}s", flush=True)

        if not user:
            print(f"[auth:authenticate] 3b. USER_NOT_FOUND t={_elapsed():.3f}s", flush=True)
            return None

        if user.get('status') != 'active':
            raise ValueError(f"Account is {user.get('status', 'inactive')}")

        # Step 2: Password verification (bcrypt - CPU-bound, can be slow)
        print(f"[auth:authenticate] 4. BCRYPT_VERIFY_START t={_elapsed():.3f}s", flush=True)
        if not self._verify_password(password, user.get('password') or ''):
            print(f"[auth:authenticate] 4b. PASSWORD_FAIL t={_elapsed():.3f}s", flush=True)
            return None
        print(f"[auth:authenticate] 5. BCRYPT_VERIFY_END t={_elapsed():.3f}s", flush=True)

        # Auth succeeded. Set lastLogin in memory for response; Firestore update is best-effort.
        now = datetime.utcnow().isoformat()
        user['lastLogin'] = now

        # Step 3: lastLogin Firestore update - BEST-EFFORT ONLY, must NOT block auth.
        # Throttle writes per user to reduce quota usage during repeated logins.
        disable_lastlogin_update = str(
            os.getenv("AUTH_DISABLE_LASTLOGIN_UPDATE", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
        now_epoch = time.time()
        last_write_at = self._last_lastlogin_write_at.get(user["id"], 0.0)
        min_interval = max(0, self.AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS)
        should_write_lastlogin = (
            not disable_lastlogin_update
            and (min_interval == 0 or (now_epoch - last_write_at) >= min_interval)
        )

        if should_write_lastlogin:
            self._last_lastlogin_write_at[user["id"]] = now_epoch

            def _update_lastlogin_background():
                try:
                    t_start = time.monotonic()
                    self.collection.document(user['id']).update(
                        {"lastLogin": now},
                        timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
                        retry=None,
                    )
                    elapsed = time.monotonic() - t_start
                    if elapsed > 1.0:
                        print(f"[auth:authenticate] lastLogin update completed in {elapsed:.3f}s (background)", flush=True)
                except Exception as e:
                    print(f"[auth:authenticate] lastLogin background update FAILED (auth still succeeds): {e}", flush=True)

            t = threading.Thread(target=_update_lastlogin_background, daemon=True)
            t.start()
            print(f"[auth:authenticate] 6. lastLogin DISPATCHED (non-blocking, best-effort) t={_elapsed():.3f}s", flush=True)
        else:
            print(
                f"[auth:authenticate] 6. lastLogin SKIPPED (disabled/throttled) t={_elapsed():.3f}s",
                flush=True,
            )

        # Step 4: Sanitize and return - no Firestore, fast
        print(f"[auth:authenticate] 7. SANITIZE_START t={_elapsed():.3f}s", flush=True)
        result = self._sanitize_user(user)
        print(f"[auth:authenticate] 8. RETURN_SUCCESS t={_elapsed():.3f}s", flush=True)
        return result

    def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        """
        Change user's password

        Args:
            user_id: User ID
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            True if password changed successfully
        """
        user = self.get_user_by_id(user_id)

        if not user:
            raise ValueError("User not found")

        # Verify current password
        if not self._verify_password(current_password, user['password']):
            raise ValueError("Current password is incorrect")

        # Update password
        self.collection.document(user_id).update(
            {
                "password": self._hash_password(new_password),
                "updatedAt": datetime.utcnow().isoformat()
            },
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )

        print(f"Password changed for user: {user['email']}")
        return True

    # ==========================================
    # Helpers
    # ==========================================

    def ensure_default_admin(self) -> Optional[Dict[str, Any]]:
        """
        Ensure at least one admin user exists
        Creates default admin@lina.com if no users exist

        Returns:
            Created admin user or None if users already exist
        """
        try:
            # Check if any users exist
            docs = list(
                self.collection.limit(1).stream(
                    timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                    retry=None,
                )
            )

            if len(docs) == 0:
                print("No dashboard users found. Creating default admin...")
                admin = self.create_user({
                    "email": "admin@lina.com",
                    "password": "admin123",
                    "name": "Admin",
                    "role": "admin",
                    "permissions": None,
                    "status": "active"
                }, created_by=None)
                print(f"Default admin created: admin@lina.com")
                return admin

            return None
        except Exception as e:
            print(f"Error ensuring default admin: {e}")
            return None

    def count_active_admins(self) -> int:
        """Count the number of active admin users"""
        try:
            query = self.collection.where(
                filter=FieldFilter("role", "==", "admin")
            ).where(filter=FieldFilter("status", "==", "active"))
            docs = list(
                query.stream(
                    timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                    retry=None,
                )
            )
            return len(docs)
        except Exception as e:
            print(f"Error counting admins: {e}")
            return 0

    def _sanitize_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields (password) from user data. Fast, in-memory only."""
        if not user:
            return None

        return {
            "id": user.get("id"),
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
            "permissions": user.get("permissions"),
            "status": user.get("status"),
            "lastLogin": user.get("lastLogin"),
            "createdAt": user.get("createdAt"),
            "createdBy": user.get("createdBy"),
            "updatedAt": user.get("updatedAt")
        }


# Global service instance
user_service = UserService()
