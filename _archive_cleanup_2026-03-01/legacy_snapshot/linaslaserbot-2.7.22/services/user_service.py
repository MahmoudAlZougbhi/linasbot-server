"""
User Service for Dashboard Authentication
Handles Firestore operations for dashboard users with bcrypt password hashing
"""

import uuid
import bcrypt
from datetime import datetime
from typing import Optional, Dict, List, Any
from utils.utils import get_firestore_db


class UserService:
    """Service for managing dashboard users in Firestore"""

    COLLECTION = "artifacts/linas-ai-bot-backend/dashboard_users"

    def __init__(self):
        self._db = None

    @property
    def db(self):
        """Lazy-load Firestore database connection"""
        if self._db is None:
            self._db = get_firestore_db()
        return self._db

    @property
    def collection(self):
        """Get the dashboard_users collection reference"""
        if not self.db:
            raise Exception("Firestore not initialized")
        return self.db.collection("artifacts").document("linas-ai-bot-backend").collection("dashboard_users")

    # ==========================================
    # Password Methods
    # ==========================================

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            print(f"Password verification error: {e}")
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
            "permissions": user_data.get('permissions'),  # Custom permission overrides
            "status": user_data.get('status', 'active'),
            "lastLogin": None,
            "createdAt": now,
            "createdBy": created_by,
            "updatedAt": now
        }

        # Save to Firestore
        self.collection.document(user_id).set(user_doc)
        print(f"Created dashboard user: {user_doc['email']} (ID: {user_id})")

        # Return without password
        return self._sanitize_user(user_doc)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email address (includes password for auth)"""
        try:
            email_lower = email.lower().strip()
            query = self.collection.where("email", "==", email_lower).limit(1)
            docs = list(query.stream())

            if docs:
                return docs[0].to_dict()
            return None
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID (includes password for internal use)"""
        try:
            doc = self.collection.document(user_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"Error getting user by ID: {e}")
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users (without passwords)"""
        try:
            docs = self.collection.stream()
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

            self.collection.document(user_id).update(update_data)

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

            self.collection.document(user_id).delete()
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
        Authenticate a user with email and password

        Args:
            email: User's email
            password: Plain text password

        Returns:
            User data (without password) if authentication succeeds, None otherwise
        """
        user = self.get_user_by_email(email)

        if not user:
            return None

        # Check if user is active
        if user.get('status') != 'active':
            raise ValueError(f"Account is {user.get('status', 'inactive')}")

        # Verify password
        if not self._verify_password(password, user['password']):
            return None

        # Update last login
        now = datetime.utcnow().isoformat()
        self.collection.document(user['id']).update({
            "lastLogin": now
        })
        user['lastLogin'] = now

        return self._sanitize_user(user)

    def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        """
        Change a user's password

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
        self.collection.document(user_id).update({
            "password": self._hash_password(new_password),
            "updatedAt": datetime.utcnow().isoformat()
        })

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
            docs = list(self.collection.limit(1).stream())

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
            query = self.collection.where("role", "==", "admin").where("status", "==", "active")
            docs = list(query.stream())
            return len(docs)
        except Exception as e:
            print(f"Error counting admins: {e}")
            return 0

    def _sanitize_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields (password) from user data"""
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
