"""
Enhanced Authentication Module for Monaco Payroll System
=======================================================
Secure user authentication with bcrypt password hashing and file locking
"""

from __future__ import annotations
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd
import bcrypt

# Try to import pyarrow, fallback to pickle
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

# Configuration
USERS_FILE = Path('data/users.parquet')
LOCK_FILE = Path('data/users.lock')
BCRYPT_ROUNDS = 12
LOCK_TIMEOUT = 5.0

logger = logging.getLogger(__name__)


def _acquire_lock(timeout: float = LOCK_TIMEOUT):
    """Acquire file lock for thread-safe operations"""
    start = time.time()
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            # Atomic create operation; fails if file exists
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"Could not acquire lock after {timeout}s")
            time.sleep(0.05)


def _release_lock():
    """Release file lock"""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Error releasing lock: {e}")


class AuthManager:
    """
    Authentication Manager with bcrypt and file locking
    
    Schema: username | name | role | created_at | hash_bcrypt
    
    Roles: 'admin', 'comptable'
    """

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        """Create empty DataFrame with correct schema"""
        return pd.DataFrame(columns=[
            "username", "name", "role", "created_at", "hash_bcrypt"
        ])

    @staticmethod
    def _ensure_store():
        """Ensure data directory exists"""
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_df() -> pd.DataFrame:
        """Load users DataFrame from storage"""
        AuthManager._ensure_store()
        
        # Try parquet first
        if USERS_FILE.exists() and HAS_PYARROW:
            return pd.read_parquet(USERS_FILE)
        
        # Try pickle fallback
        pkl_file = USERS_FILE.with_suffix(".pkl")
        if pkl_file.exists():
            return pd.read_pickle(pkl_file)
        
        return AuthManager._empty_df()

    @staticmethod
    def _save_df(df: pd.DataFrame):
        """Save users DataFrame to storage with locking"""
        _acquire_lock()
        try:
            if HAS_PYARROW:
                df.to_parquet(USERS_FILE, index=False)
            else:
                df.to_pickle(USERS_FILE.with_suffix(".pkl"))
        finally:
            _release_lock()

    # ---------- Password hashing methods ----------
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, hash_bcrypt: str) -> bool:
        """Verify password against bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode(), hash_bcrypt.encode())
        except Exception as e:
            logger.error(f"bcrypt verification error: {e}")
            return False

    # ---------- Public API ----------

    @staticmethod
    def verify_user(username: str, password: str) -> Optional[Dict]:
        """
        Verify user credentials and return user info
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            User dict with username, role, name if valid, None otherwise
        """
        try:
            df = AuthManager._load_df()
            user_row = df[df["username"] == username]
            
            if user_row.empty:
                return None
                
            user_data = user_row.iloc[0]
            hash_value = user_data["hash_bcrypt"]
            
            # Handle missing or invalid hash
            if pd.isna(hash_value) or not hash_value:
                logger.warning(f"No password hash for user: {username}")
                return None
            
            # Verify password
            if AuthManager.verify_password(password, str(hash_value)):
                return {
                    "username": username,
                    "role": user_data["role"],
                    "name": user_data["name"],
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error verifying user {username}: {e}")
            return None

    @staticmethod
    def add_or_update_user(username: str, password: str, role: str = "comptable", name: str = ""):
        """
        Add new user or update existing user
        
        Args:
            username: Unique username (no spaces)
            password: Plain text password
            role: User role ('admin' or 'comptable')
            name: Display name
        """
        if not username or any(c.isspace() for c in username):
            raise ValueError("Invalid username (no spaces allowed)")
        
        if not password:
            raise ValueError("Password cannot be empty")
        
        if role not in ['admin', 'comptable']:
            raise ValueError("Role must be 'admin' or 'comptable'")
        
        try:
            df = AuthManager._load_df()
            now = datetime.utcnow().isoformat()
            hash_value = AuthManager.hash_password(password)
            
            # Check if user exists
            if (df["username"] == username).any():
                # Update existing user
                mask = df["username"] == username
                df.loc[mask, ["name", "role", "hash_bcrypt"]] = [name, role, hash_value]
                logger.info(f"Updated user: {username}")
            else:
                # Add new user
                new_user = pd.DataFrame([{
                    "username": username,
                    "name": name,
                    "role": role,
                    "created_at": now,
                    "hash_bcrypt": hash_value
                }])
                df = pd.concat([df, new_user], ignore_index=True)
                logger.info(f"Added new user: {username}")
            
            AuthManager._save_df(df)
            
        except Exception as e:
            logger.error(f"Error adding/updating user {username}: {e}")
            raise

    @staticmethod
    def list_users() -> List[Dict]:
        """
        List all users (without sensitive data)
        
        Returns:
            List of user dicts with username, name, role, created_at
        """
        try:
            df = AuthManager._load_df()
            users = []
            
            for _, user in df.iterrows():
                users.append({
                    "username": user["username"],
                    "name": user["name"],
                    "role": user["role"],
                    "created_at": str(user["created_at"])
                })
            
            return users
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []

    @staticmethod
    def remove_users(usernames: List[str]):
        """
        Remove users by username
        
        Args:
            usernames: List of usernames to remove
        """
        if not usernames:
            return
        
        try:
            df = AuthManager._load_df()
            original_count = len(df)
            
            df = df[~df["username"].isin(usernames)]
            removed_count = original_count - len(df)
            
            AuthManager._save_df(df)
            logger.info(f"Removed {removed_count} users")
            
        except Exception as e:
            logger.error(f"Error removing users: {e}")
            raise

    @staticmethod
    def user_exists(username: str) -> bool:
        """Check if user exists"""
        try:
            df = AuthManager._load_df()
            return (df["username"] == username).any()
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return False

    @staticmethod
    def create_default_users():
        """
        Create default users for the Monaco Payroll System
        Only creates users if none exist
        """
        try:
            # Only create if no users exist
            if len(AuthManager.list_users()) > 0:
                logger.info("Users already exist, skipping default user creation")
                return
            
            # Create default admin user
            AuthManager.add_or_update_user(
                username="admin",
                password="admin123",
                role="admin",
                name="Administrateur Système"
            )
            
            # Create default comptable user
            AuthManager.add_or_update_user(
                username="comptable",
                password="compta123",
                role="comptable", 
                name="Comptable Monaco"
            )
            
            logger.info("Created default users: admin and comptable")
            
        except Exception as e:
            logger.error(f"Error creating default users: {e}")
            raise

    @staticmethod
    def get_user_info(username: str) -> Optional[Dict]:
        """Get user information without authentication"""
        try:
            df = AuthManager._load_df()
            user_row = df[df["username"] == username]
            
            if user_row.empty:
                return None
                
            user_data = user_row.iloc[0]
            return {
                "username": username,
                "name": user_data["name"],
                "role": user_data["role"],
                "created_at": str(user_data["created_at"])
            }
            
        except Exception as e:
            logger.error(f"Error getting user info for {username}: {e}")
            return None

    @staticmethod
    def change_password(username: str, old_password: str, new_password: str) -> bool:
        """
        Change user password with verification
        
        Args:
            username: Username
            old_password: Current password
            new_password: New password
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Verify current password
            user = AuthManager.verify_user(username, old_password)
            if not user:
                return False
            
            # Update with new password
            user_info = AuthManager.get_user_info(username)
            if not user_info:
                return False
            
            AuthManager.add_or_update_user(
                username=username,
                password=new_password,
                role=user_info["role"],
                name=user_info["name"]
            )
            
            logger.info(f"Password changed for user: {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error changing password for {username}: {e}")
            return False

    @staticmethod
    def get_stats() -> Dict:
        """Get user statistics"""
        try:
            df = AuthManager._load_df()
            total_users = len(df)
            
            if total_users == 0:
                return {
                    "total_users": 0,
                    "admin_users": 0,
                    "comptable_users": 0
                }
            
            admin_users = len(df[df["role"] == "admin"])
            comptable_users = len(df[df["role"] == "comptable"])
            
            return {
                "total_users": total_users,
                "admin_users": admin_users,
                "comptable_users": comptable_users
            }
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {"error": str(e)}

    @staticmethod
    def is_admin(username: str) -> bool:
        """Check if user has admin role"""
        user_info = AuthManager.get_user_info(username)
        return user_info and user_info["role"] == "admin"

    @staticmethod
    def is_comptable(username: str) -> bool:
        """Check if user has comptable role"""
        user_info = AuthManager.get_user_info(username)
        return user_info and user_info["role"] == "comptable"