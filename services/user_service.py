"""
User Service for Dashboard Authentication
Handles Firestore operations for dashboard users with bcrypt password hashing

Auth/password helpers: user_service_auth (LOC split).
"""

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, cast

from google.cloud.firestore_v1.base_query import FieldFilter

from services.user_service_auth import UserServiceAuthMixin
from utils.utils import get_firestore_db


class AuthBackendUnavailableError(RuntimeError):
    """Raised when auth storage (Firestore) is temporarily unavailable."""


class TenantIdRequiredError(ValueError):
    """Raised when tenant identifier is missing or empty."""


class UserService(UserServiceAuthMixin):
    """Service for managing dashboard users in Firestore"""

    COLLECTION = "artifacts/linas-ai-bot-backend/dashboard_users"
    AUTH_QUERY_TIMEOUT_SECONDS = float(os.getenv("AUTH_QUERY_TIMEOUT_SECONDS", "6"))
    AUTH_WRITE_TIMEOUT_SECONDS = float(os.getenv("AUTH_WRITE_TIMEOUT_SECONDS", "5"))
    AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS = int(os.getenv("AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS", "21600"))

    @staticmethod
    def _normalize_tenant_id(value: Any) -> str:
        if value is None:
            raise TenantIdRequiredError("Tenant identifier is required")
        tenant_id = str(value).strip().lower()
        if not tenant_id:
            raise TenantIdRequiredError("Tenant identifier is required")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", tenant_id):
            raise ValueError("Invalid tenant identifier")
        return tenant_id

    def __init__(self) -> None:
        self._db = None
        self._last_lastlogin_write_at: dict[str, float] = {}

    @property
    def db(self) -> Any:
        """Lazy-load Firestore database connection"""
        if self._db is None:
            t0 = time.monotonic()
            print("[auth:user_service] db property: first access, calling get_firestore_db t=0.00s", flush=True)
            self._db = get_firestore_db()
            elapsed = time.monotonic() - t0
            print(
                f"[auth:user_service] db property: get_firestore_db returned in {elapsed:.3f}s (db is None: {self._db is None})",
                flush=True,
            )
        return self._db

    @property
    def collection(self) -> Any:
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
    # CRUD Operations
    # ==========================================

    def create_user(self, user_data: dict[str, Any], created_by: str | None = None) -> dict[str, Any]:
        """
        Create a new dashboard user

        Args:
            user_data: Dict with email, password, name, role, permissions, status
            created_by: ID of the user creating this account

        Returns:
            Created user data (without password)
        """
        # Validate required fields
        if not user_data.get("email"):
            raise ValueError("Email is required")
        if not user_data.get("password"):
            raise ValueError("Password is required")

        from services.role_assignment import RoleAssignmentError, assert_assignable_role

        try:
            role = assert_assignable_role(
                str(user_data.get("role") or "viewer"),
                created_by=created_by,
            )
        except RoleAssignmentError as exc:
            raise ValueError(str(exc)) from exc

        # Check if email already exists
        existing = self.get_user_by_email(user_data["email"])
        if existing:
            raise ValueError("Email already exists")

        # Generate user ID
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Build user document
        user_doc = {
            "id": user_id,
            "email": user_data["email"].lower().strip(),
            "password": self._hash_password(user_data["password"]),
            "name": user_data.get("name") or (user_data.get("email") or "user@unknown").split("@")[0],
            "role": role,
            "permissions": user_data.get("permissions"),
            "tenantId": self._normalize_tenant_id(user_data.get("tenantId")),
            "status": user_data.get("status", "active"),
            "passwordEpoch": 0,
            "lastLogin": None,
            "createdAt": now,
            "createdBy": created_by,
            "updatedAt": now,
        }
        business_name = str(user_data.get("businessName") or "").strip()
        if business_name:
            user_doc["businessName"] = business_name[:120]

        # Optional owner preferences — never infer gender from email/name.
        gender_raw = str(user_data.get("gender") or "unset").strip().lower()
        user_doc["gender"] = gender_raw if gender_raw in {"male", "female", "unset"} else "unset"
        display_name = str(user_data.get("displayName") or user_data.get("name") or "").strip()
        if display_name:
            user_doc["displayName"] = display_name[:80]
        pref_lang = str(user_data.get("preferredLanguage") or "en").strip().lower()
        if pref_lang.startswith("ar"):
            user_doc["preferredLanguage"] = "ar"
        elif pref_lang.startswith("fr"):
            user_doc["preferredLanguage"] = "fr"
        else:
            user_doc["preferredLanguage"] = "en"
        form = str(user_data.get("formOfAddress") or "").strip()
        if form:
            user_doc["formOfAddress"] = form[:80]
        user_doc["addressPromptAsked"] = bool(user_data.get("addressPromptAsked", False))

        # SaaS public registration starts unverified; offline/provisioned admins default verified.
        if "emailVerified" in user_data:
            user_doc["emailVerified"] = bool(user_data.get("emailVerified"))
        else:
            created_by_norm = str(created_by or "").strip().lower()
            user_doc["emailVerified"] = created_by_norm not in {"public-register", "public_register"}

        # Save to Firestore
        self.collection.document(user_id).set(
            user_doc,
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )
        print(f"Created dashboard user: {user_doc['email']} (ID: {user_id})")

        # Return without password
        return self._sanitize_user(user_doc) or {} or {}

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

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
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
                print(
                    f"[auth:get_user_by_email] attempt {attempt + 1}/{max_retries}, accessing self.collection t={t1 - t_start:.3f}s",
                    flush=True,
                )
                coll = self.collection
                print(f"[auth:get_user_by_email] collection accessed in {time.monotonic() - t1:.3f}s", flush=True)

                # Firestore query - direct email lookup
                query = coll.where(filter=FieldFilter("email", "==", email_lower)).limit(1)

                t2 = time.monotonic()
                print(
                    f"[auth:get_user_by_email] query.stream() START t={t2 - t_start:.3f}s (FIRESTORE NETWORK OP - may block)",
                    flush=True,
                )
                docs = list(
                    query.stream(
                        timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )
                elapsed = time.monotonic() - t2
                print(
                    f"[auth:get_user_by_email] query.stream() RETURNED in {elapsed:.3f}s, doc_count={len(docs)}",
                    flush=True,
                )

                if docs:
                    result = docs[0].to_dict()
                    print(f"[auth:get_user_by_email] USER_FOUND in {time.monotonic() - t_start:.3f}s", flush=True)
                    return cast(dict[str, Any] | None, result)
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

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Get a user by ID (includes password for internal use)"""
        try:
            doc = self.collection.document(user_id).get(
                timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                retry=None,
            )
            if doc.exists:
                return cast(dict[str, Any] | None, doc.to_dict())
            return None
        except Exception as e:
            print(f"[auth:get_user_by_id] Error: {e}", flush=True)
            return None

    def tenant_id_exists(self, tenant_id: str) -> bool:
        """Return True when any dashboard user already uses this tenant id."""
        tid = self._normalize_tenant_id(tenant_id)
        try:
            query = self.collection.where(filter=FieldFilter("tenantId", "==", tid)).limit(1)
            docs = list(query.stream(timeout=self.AUTH_QUERY_TIMEOUT_SECONDS, retry=None))
            return len(docs) > 0
        except Exception as e:
            print(f"[auth:tenant_id_exists] Error: {e}", flush=True)
            # Fail closed: treat as taken so registration cannot collide on lookup failure.
            return True

    def get_all_users(self) -> list[dict[str, Any]]:
        """Get all users (without passwords)"""
        try:
            docs = self.collection.stream(
                timeout=self.AUTH_QUERY_TIMEOUT_SECONDS,
                retry=None,
            )
            users: list[dict[str, Any]] = []
            for doc in docs:
                user_data = doc.to_dict()
                sanitized = self._sanitize_user(user_data)
                if sanitized is not None:
                    users.append(sanitized)
            return users
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []

    def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
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
            update_data: dict[str, Any] = {"updatedAt": datetime.utcnow().isoformat()}

            if "role" in updates:
                from services.role_assignment import RoleAssignmentError, assert_assignable_role

                try:
                    updates = {
                        **updates,
                        "role": assert_assignable_role(
                            str(updates["role"]),
                            created_by=updates.get("_role_created_by"),
                        ),
                    }
                except RoleAssignmentError as exc:
                    raise ValueError(str(exc)) from exc

            # Allowed fields to update
            allowed_fields = ["name", "role", "permissions", "status"]
            for field in allowed_fields:
                if field in updates:
                    update_data[field] = updates[field]
            if "tenantId" in updates:
                update_data["tenantId"] = self._normalize_tenant_id(updates["tenantId"])

            if "gender" in updates and updates["gender"] is not None:
                g = str(updates["gender"]).strip().lower()
                update_data["gender"] = g if g in {"male", "female", "unset"} else "unset"
            if "displayName" in updates and updates["displayName"] is not None:
                update_data["displayName"] = str(updates["displayName"]).strip()[:80]
            if "preferredLanguage" in updates and updates["preferredLanguage"] is not None:
                lang = str(updates["preferredLanguage"]).strip().lower()
                if lang.startswith("ar"):
                    update_data["preferredLanguage"] = "ar"
                elif lang.startswith("fr"):
                    update_data["preferredLanguage"] = "fr"
                else:
                    update_data["preferredLanguage"] = "en"
            if "formOfAddress" in updates and updates["formOfAddress"] is not None:
                update_data["formOfAddress"] = str(updates["formOfAddress"]).strip()[:80]
            if "addressPromptAsked" in updates:
                update_data["addressPromptAsked"] = bool(updates["addressPromptAsked"])

            # Handle password update separately (hash it) and bump epoch for session invalidation
            if "password" in updates and updates["password"]:
                update_data["password"] = self._hash_password(updates["password"])
                update_data["passwordEpoch"] = int(user.get("passwordEpoch") or user.get("password_epoch") or 0) + 1

            # Check if we're demoting the last admin
            if "role" in updates and updates["role"] != "admin" and user["role"] == "admin":
                admin_count = self.count_active_admins()
                if admin_count <= 1:
                    raise ValueError("Cannot demote the last admin")

            # Check if we're deactivating the last admin
            if (
                "status" in updates
                and updates["status"] != "active"
                and user["role"] == "admin"
                and user["status"] == "active"
            ):
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
            if updated_user is None:
                raise ValueError(f"User not found after update: {user_id}")
            return self._sanitize_user(updated_user) or {}

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
            if user["role"] == "admin" and user.get("status") == "active":
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


# Global service instance
user_service = UserService()
