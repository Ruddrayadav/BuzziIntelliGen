"""
services/auth_service.py
------------------------
Handles user authentication and tenant isolation.

SECURITY NOTE FOR FYP:
  In a real production app, you would use bcrypt for password hashing.
  For this Final Year Project demo, we use Python's built-in hashlib (SHA-256)
  to demonstrate the concept of secure password storage without adding extra
  C-dependencies like bcrypt which can complicate deployment.
"""

import hashlib
import os
from typing import Optional
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User

def _hash_password(password: str, salt: bytes) -> str:
    """Hash the password with the given salt using SHA-256."""
    # We combine the password and salt, then hash it.
    # The result is a hex string.
    pwd_bytes = password.encode('utf-8')
    return hashlib.sha256(salt + pwd_bytes).hexdigest()

def register_user(username: str, password: str, business_name: str) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (success, message_or_tenant_id).
    """
    username = username.strip().lower()
    
    with get_db() as db:
        # Check if user already exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return False, "Username already exists. Please choose another."
        
        # Generate a random 16-byte salt
        salt = os.urandom(16)
        password_hash = _hash_password(password, salt)
        
        # In a real system, tenant_id might be a UUID. Here we use the username.
        tenant_id = username
        
        new_user = User(
            username=username,
            password_hash=password_hash,
            salt=salt.hex(),  # Store salt as hex string
            tenant_id=tenant_id,
            business_name=business_name
        )
        
        db.add(new_user)
        db.commit()
        
        return True, tenant_id

def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Check credentials. Returns the User object if successful, None otherwise.
    """
    username = username.strip().lower()
    
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
            
        salt = bytes.fromhex(user.salt)
        password_hash = _hash_password(password, salt)
        
        if password_hash == user.password_hash:
            db.expunge(user)
            return user
            
    return None
