"""
services/auth_service.py
------------------------
Handles user authentication, password hashing, and tenant isolation.

SECURITY UPGRADE:
  Uses Python's built-in hashlib.scrypt (n=2**14, r=8, p=1, 16-byte salt, 64-byte key)
  with hmac.compare_digest to prevent timing attacks and rainbow table/GPU attacks.
  Hashes are stored in a self-describing format:
    "scrypt$16384$8$1$<salt_hex>$<hash_hex>"
  Legacy accounts with SHA-256 hashes are verified on login and transparently
  upgraded to scrypt without disrupting the user.
"""

import hashlib
import hmac
import os
from typing import Optional

from db.database import get_db
from db.models import User

# Standard scrypt parameters recommended for interactive logins
SCRYPT_N = 16384  # 2**14 CPU/memory cost
SCRYPT_R = 8      # block size
SCRYPT_P = 1      # parallelization
SCRYPT_DKLEN = 64 # output key length (64 bytes = 128 hex chars)
MIN_PASSWORD_LENGTH = 8


def _hash_password_scrypt(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """
    Hash a password using hashlib.scrypt.
    Returns (formatted_hash_string, salt_hex).
    Formatted string format: scrypt$16384$8$1$<salt_hex>$<hash_hex>
    """
    if salt is None:
        salt = os.urandom(16)
    
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=0,
        dklen=SCRYPT_DKLEN,
    )
    salt_hex = salt.hex()
    hash_hex = derived.hex()
    formatted = f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_hex}${hash_hex}"
    return formatted, salt_hex


def _verify_password(password: str, stored_hash: str, salt_hex: str) -> tuple[bool, bool]:
    """
    Verify password against stored_hash using hmac.compare_digest.
    Returns (is_valid, needs_upgrade).
    """
    # 1. Check if stored_hash is in self-describing scrypt format
    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) == 6:
            _, n_str, r_str, p_str, s_hex, expected_hex = parts
            try:
                n = int(n_str)
                r = int(r_str)
                p = int(p_str)
                salt = bytes.fromhex(s_hex)
                computed = hashlib.scrypt(
                    password.encode("utf-8"),
                    salt=salt,
                    n=n,
                    r=r,
                    p=p,
                    maxmem=0,
                    dklen=len(bytes.fromhex(expected_hex)),
                ).hex()
                is_valid = hmac.compare_digest(computed, expected_hex)
                needs_upgrade = (n != SCRYPT_N or r != SCRYPT_R or p != SCRYPT_P)
                return is_valid, needs_upgrade
            except Exception:
                return False, False

    # 2. Legacy SHA-256 fallback (64 hex characters)
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        legacy_computed = hashlib.sha256(salt_bytes + password.encode("utf-8")).hexdigest()
        if hmac.compare_digest(legacy_computed, stored_hash):
            return True, True  # Valid password, but needs transparent upgrade to scrypt
    except Exception:
        pass

    return False, False


def register_user(username: str, password: str, business_name: str) -> tuple[bool, str]:
    """
    Register a new user.
    Requires minimum 8 characters for password.
    Returns (success, message_or_tenant_id).
    """
    username = username.strip().lower()
    
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    
    with get_db() as db:
        # Check if user already exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return False, "Username already exists. Please choose another."
        
        password_hash, salt_hex = _hash_password_scrypt(password)
        
        # In this system, username is the tenant_id
        tenant_id = username
        
        new_user = User(
            username=username,
            password_hash=password_hash,
            salt=salt_hex,
            tenant_id=tenant_id,
            business_name=business_name.strip(),
        )
        
        db.add(new_user)
        db.commit()
        
        return True, tenant_id


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Check credentials. Returns the User object if successful, None otherwise.
    Transparently upgrades legacy SHA-256 hashes to scrypt upon successful login.
    """
    username = username.strip().lower()
    
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
            
        is_valid, needs_upgrade = _verify_password(password, user.password_hash, user.salt)
        if not is_valid:
            return None
            
        if needs_upgrade:
            # Transparently upgrade legacy hash to modern scrypt
            new_hash, new_salt = _hash_password_scrypt(password)
            user.password_hash = new_hash
            user.salt = new_salt
            db.flush()

        # Ensure attributes are populated in memory before expunging from session
        _ = (user.id, user.username, user.tenant_id, user.business_name, user.password_hash, user.salt)
        db.expunge(user)
        return user
