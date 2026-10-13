"""
tests/test_auth_service.py
--------------------------
Tests for the user authentication and registration logic.
"""

import pytest
from db.database import get_db, init_db
from db.models import User
from services.auth_service import register_user, authenticate_user

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(User).filter(User.username.in_(["testuser", "testuser2"])).delete()
        db.commit()

class TestAuthService:
    def test_register_and_authenticate_success(self):
        # Register a new user
        success, result = register_user("testuser", "my_secure_password", "My Shop")
        assert success is True
        assert result == "testuser"  # In our implementation, username is the tenant_id
        
        # Authenticate with correct password
        user = authenticate_user("testuser", "my_secure_password")
        assert user is not None
        assert user.username == "testuser"
        assert user.business_name == "My Shop"

    def test_authenticate_wrong_password(self):
        register_user("testuser2", "password123", "Test Biz")
        
        # Authenticate with wrong password
        user = authenticate_user("testuser2", "wrongpassword")
        assert user is None

    def test_register_duplicate_username_fails(self):
        success1, _ = register_user("testuser", "pass1", "Biz 1")
        assert success1 is True
        
        success2, msg = register_user("testuser", "pass2", "Biz 2")
        assert success2 is False
        assert "already exists" in msg

    def test_authenticate_nonexistent_user(self):
        user = authenticate_user("nobody", "pass")
        assert user is None
