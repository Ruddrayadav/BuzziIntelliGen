"""
tests/conftest.py
-----------------
Pytest configuration and global fixtures.

CRITICAL SAFETY RULE:
Tests must NEVER touch the developer's real database (data/biz_intelligence.db).
This conftest intercepts database initialization and directs all test queries
to an isolated temporary SQLite file that is wiped after the test run.
"""

import os
import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# 1. Point DB_URL to a temporary file before any other module imports settings
_temp_dir = tempfile.TemporaryDirectory()
_temp_db_path = Path(_temp_dir.name) / "test_bizintel.db"
os.environ["DB_URL"] = f"sqlite:///{_temp_db_path}"
os.environ["BIZINTEL_SESSION_SECRET"] = "test-session-secret-must-be-long-and-secure-32chars"

# 2. Import config and db modules now
import config
from config import settings
import db.database as db_module
from db.database import Base, init_db

# Ensure settings object reflects the test DB
settings.DB_URL = f"sqlite:///{_temp_db_path}"

# Re-create engine and SessionLocal bound strictly to the temporary test DB
test_engine = create_engine(
    settings.DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(test_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()

db_module.engine = test_engine
db_module.SessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)

# Initialize schema in test database
init_db()


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database():
    """Ensure the entire test suite runs inside the isolated temporary SQLite database."""
    init_db()
    yield _temp_db_path
    # Teardown: dispose engine connections and clean up temporary directory
    db_module.engine.dispose()
    _temp_dir.cleanup()
