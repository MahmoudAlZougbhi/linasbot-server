"""UserService auth/password helpers (LOC split from user_service)."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any

import bcrypt
from google.cloud.firestore_v1.base_query import FieldFilter


class UserServiceAuthMixin:
    """Authentication, password, and sanitize helpers for UserService."""

    AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS: Any
    AUTH_QUERY_TIMEOUT_SECONDS: Any
    AUTH_WRITE_TIMEOUT_SECONDS: Any
    _last_lastlogin_write_at: Any
    _normalize_tenant_id: Any
    collection: Any
    get_user_by_email: Any
    get_user_by_id: Any

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return str(bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8"))

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its bcrypt hash"""
        t0 = time.monotonic()
        print("[auth:_verify_password] entry t=0.00s", flush=True)
        try:
            return bool(bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")))
        except Exception:
            elapsed = time.monotonic() - t0
            print(f"[auth:_verify_password] ERROR after {elapsed:.3f}s", flush=True)
            return False

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
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
        # Timing logs only — never print email / password material.
        print("[auth:authenticate] 1. ENTRY t=0.00s", flush=True)

        # Step 1: Firestore user lookup (may trigger lazy db init)
        print(f"[auth:authenticate] 2. USER_LOOKUP_START t={_elapsed():.3f}s", flush=True)
        user = self.get_user_by_email(email_norm)
        print(f"[auth:authenticate] 3. USER_LOOKUP_END t={_elapsed():.3f}s", flush=True)

        if not user:
            print(f"[auth:authenticate] 3b. USER_NOT_FOUND t={_elapsed():.3f}s", flush=True)
            return None

        if user.get("status") != "active":
            raise ValueError(f"Account is {user.get('status', 'inactive')}")

        # Step 2: Password verification (bcrypt - CPU-bound, can be slow)
        print(f"[auth:authenticate] 4. BCRYPT_VERIFY_START t={_elapsed():.3f}s", flush=True)
        if not self._verify_password(password, user.get("password") or ""):
            print(f"[auth:authenticate] 4b. PASSWORD_FAIL t={_elapsed():.3f}s", flush=True)
            return None
        print(f"[auth:authenticate] 5. BCRYPT_VERIFY_END t={_elapsed():.3f}s", flush=True)

        # Auth succeeded. Set lastLogin in memory for response; Firestore update is best-effort.
        now = datetime.utcnow().isoformat()
        user["lastLogin"] = now

        # Step 3: lastLogin Firestore update - BEST-EFFORT ONLY, must NOT block auth.
        # Throttle writes per user to reduce quota usage during repeated logins.
        disable_lastlogin_update = str(os.getenv("AUTH_DISABLE_LASTLOGIN_UPDATE", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        now_epoch = time.time()
        last_write_at = self._last_lastlogin_write_at.get(user["id"], 0.0)
        min_interval = max(0, self.AUTH_LASTLOGIN_MIN_WRITE_INTERVAL_SECONDS)
        should_write_lastlogin = not disable_lastlogin_update and (
            min_interval == 0 or (now_epoch - last_write_at) >= min_interval
        )

        if should_write_lastlogin:
            self._last_lastlogin_write_at[user["id"]] = now_epoch

            def _update_lastlogin_background() -> None:
                try:
                    t_start = time.monotonic()
                    self.collection.document(user["id"]).update(
                        {"lastLogin": now},
                        timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
                        retry=None,
                    )
                    elapsed = time.monotonic() - t_start
                    if elapsed > 1.0:
                        print(
                            f"[auth:authenticate] lastLogin update completed in {elapsed:.3f}s (background)", flush=True
                        )
                except Exception:
                    print(
                        "[auth:authenticate] lastLogin background update FAILED (auth still succeeds)",
                        flush=True,
                    )

            t = threading.Thread(target=_update_lastlogin_background, daemon=True)
            t.start()
            print(
                f"[auth:authenticate] 6. lastLogin DISPATCHED (non-blocking, best-effort) t={_elapsed():.3f}s",
                flush=True,
            )
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
        if not self._verify_password(current_password, user["password"]):
            raise ValueError("Current password is incorrect")

        # Update password and bump passwordEpoch so stale sessions fail closed
        next_epoch = int(user.get("passwordEpoch") or user.get("password_epoch") or 0) + 1
        self.collection.document(user_id).update(
            {
                "password": self._hash_password(new_password),
                "passwordEpoch": next_epoch,
                "updatedAt": datetime.utcnow().isoformat(),
            },
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )

        print(f"Password changed for user_id={user_id}")
        return True

    def set_password_with_reset(self, user_id: str, new_password: str) -> bool:
        """Set password after a validated reset token (bumps passwordEpoch)."""
        from services.admin_provisioning_service import validate_provision_password

        validate_provision_password(new_password)
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        next_epoch = int(user.get("passwordEpoch") or user.get("password_epoch") or 0) + 1
        self.collection.document(user_id).update(
            {
                "password": self._hash_password(new_password),
                "passwordEpoch": next_epoch,
                "updatedAt": datetime.utcnow().isoformat(),
            },
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )
        return True

    def mark_email_verified(self, user_id: str) -> dict[str, Any] | None:
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        now = datetime.utcnow().isoformat()
        self.collection.document(user_id).update(
            {
                "emailVerified": True,
                "emailVerifiedAt": now,
                "updatedAt": now,
            },
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )
        user["emailVerified"] = True
        user["emailVerifiedAt"] = now
        return self._sanitize_user(user)

    def change_email_address(self, user_id: str, new_email: str) -> dict[str, Any] | None:
        """Apply a confirmed email change; marks the new address verified."""
        email = (new_email or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("Valid email is required")
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        other = self.get_user_by_email(email)
        if other and str(other.get("id")) != str(user_id):
            raise ValueError("Email is unavailable")
        now = datetime.utcnow().isoformat()
        self.collection.document(user_id).update(
            {
                "email": email,
                "emailVerified": True,
                "emailVerifiedAt": now,
                "updatedAt": now,
            },
            timeout=self.AUTH_WRITE_TIMEOUT_SECONDS,
            retry=None,
        )
        user["email"] = email
        user["emailVerified"] = True
        user["emailVerifiedAt"] = now
        return self._sanitize_user(user)

    def is_email_verified(self, user: dict[str, Any] | None) -> bool:
        if not user:
            return False
        # Legacy linas / pre-SaaS accounts without the field remain usable.
        if "emailVerified" not in user:
            return True
        return bool(user.get("emailVerified"))

    def ensure_default_admin(self) -> dict[str, Any] | None:
        """
        Deprecated: never creates known default credentials.
        Use scripts/provision_dashboard_admin.py (offline CLI) instead.
        """
        print("[user_service] ensure_default_admin is disabled — refusing to create hardcoded admin credentials")
        return None

    def count_active_admins(self) -> int:
        """Count the number of active admin users"""
        try:
            query = self.collection.where(filter=FieldFilter("role", "==", "admin")).where(
                filter=FieldFilter("status", "==", "active")
            )
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

    def _sanitize_user(
        self,
        user: dict[str, Any],
        *,
        doc_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Remove sensitive fields (password) from user data. Fast, in-memory only."""
        if not user:
            return None

        user_id = str(user.get("id") or doc_id or "").strip()
        if not user_id:
            return None

        raw_tenant = user.get("tenantId")
        if raw_tenant is None or str(raw_tenant).strip() == "":
            raw_tenant = user.get("tenant_id")
        if raw_tenant is None or str(raw_tenant).strip() == "":
            return None
        try:
            tenant_id = self._normalize_tenant_id(raw_tenant)
        except (ValueError, TypeError):
            return None

        email_verified = True if "emailVerified" not in user else bool(user.get("emailVerified"))
        gender = str(user.get("gender") or "unset").strip().lower()
        if gender not in {"male", "female", "unset"}:
            gender = "unset"
        pref_lang = str(user.get("preferredLanguage") or "en").strip().lower()
        if pref_lang.startswith("ar"):
            pref_lang = "ar"
        elif pref_lang.startswith("fr"):
            pref_lang = "fr"
        else:
            pref_lang = "en"
        return {
            "id": user_id,
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
            "permissions": user.get("permissions"),
            "tenantId": tenant_id,
            "businessName": user.get("businessName"),
            "status": user.get("status"),
            "emailVerified": email_verified,
            "passwordEpoch": int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
            "lastLogin": user.get("lastLogin"),
            "createdAt": user.get("createdAt"),
            "createdBy": user.get("createdBy"),
            "updatedAt": user.get("updatedAt"),
            "gender": gender,
            "displayName": user.get("displayName") or user.get("name"),
            "preferredLanguage": pref_lang,
            "formOfAddress": user.get("formOfAddress") or "",
            "addressPromptAsked": bool(user.get("addressPromptAsked")),
        }
