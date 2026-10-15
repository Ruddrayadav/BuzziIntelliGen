"""
tests/test_auth_service.py
--------------------------
Tests for user authentication, password security, and transparent hash upgrades.
"""

import hashlib
import os
import pytest
from db.database import get_db, init_db
from db.models import User
from services.auth_service import register_user, authenticate_user

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(User).filter(User.username.in_(["testuser", "testuser2", "legacyuser"])).delete()
        db.commit()


class TestAuthService:
    def test_register_and_authenticate_success(self):
        # Register a new user
        success, result = register_user("testuser", "my_secure_password", "My Shop")
        assert success is True
        assert result == "testuser"

        # Verify hash format in database is self-describing scrypt
        with get_db() as db:
            user_row = db.query(User).filter(User.username == "testuser").first()
            assert user_row is not None
            assert user_row.password_hash.startswith("scrypt$16384$8$1$")
        
        # Authenticate with correct password
        user = authenticate_user("testuser", "my_secure_password")
        assert user is not None
        assert user.username == "testuser"
        assert user.business_name == "My Shop"

    def test_short_password_rejected(self):
        # Password with 7 chars (< 8) must fail
        success, msg = register_user("testuser", "short12", "My Shop")
        assert success is False
        assert "at least 8 characters" in msg

    def test_authenticate_wrong_password(self):
        register_user("testuser2", "password123", "Test Biz")
        
        # Authenticate with wrong password fails
        user = authenticate_user("testuser2", "wrongpassword")
        assert user is None

    def test_register_duplicate_username_fails(self):
        success1, _ = register_user("testuser", "password123", "Biz 1")
        assert success1 is True
        
        success2, msg = register_user("testuser", "password456", "Biz 2")
        assert success2 is False
        assert "already exists" in msg

    def test_authenticate_nonexistent_user(self):
        user = authenticate_user("nobody", "validpassword")
        assert user is None

    def test_legacy_sha256_upgrade_works(self):
        """
        Verify that an old account with a legacy SHA-256 hash (64 hex chars)
        can log in and is transparently upgraded to scrypt.
        """
        raw_password = "my_legacy_password_2024"
        salt = os.urandom(16)
        legacy_hash = hashlib.sha256(salt + raw_password.encode("utf-8")).hexdigest()

        # Seed database directly with legacy user
        with get_db() as db:
            legacy_user = User(
                username="legacyuser",
                password_hash=legacy_hash,
                salt=salt.hex(),
                tenant_id="legacyuser",
                business_name="Legacy Store",
            )
            db.add(legacy_user)
            db.commit()

        # Verify initial state: stored hash is legacy 64 hex chars
        with get_db() as db:
            stored = db.query(User).filter(User.username == "legacyuser").first()
            assert stored is not None
            assert len(stored.password_hash) == 64
            assert not stored.password_hash.startswith("scrypt$")

        # Wrong password against legacy user fails without upgrading
        assert authenticate_user("legacyuser", "wrong_guess_123") is None

        # Correct login succeeds
        user = authenticate_user("legacyuser", raw_password)
        assert user is not None
        assert user.username == "legacyuser"

        # Check database: hash must now be upgraded to scrypt
        with get_db() as db:
            upgraded = db.query(User).filter(User.username == "legacyuser").first()
            assert upgraded is not None
            assert upgraded.password_hash.startswith("scrypt$16384$8$1$")
            upgraded_hash = upgraded.password_hash

        # Subsequent logins work cleanly with the new scrypt hash
        user2 = authenticate_user("legacyuser", raw_password)
        assert user2 is not None
        with get_db() as db:
            check_again = db.query(User).filter(User.username == "legacyuser").first()
            assert check_again.password_hash == upgraded_hash

