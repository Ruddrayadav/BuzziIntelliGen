"""
db/database.py
--------------
Database engine, session factory, and initialization helpers.

CONCEPTS EXPLAINED:
  Engine:  The low-level connection to the database file/server.
           Think of it as the "phone line" to the database.

  Session: A short-lived workspace for one set of operations.
           Think of it as a "shopping cart" — you put things in,
           and commit() is the "checkout" that saves them to the DB.
           If something goes wrong, rollback() throws away the cart.

  Base:    A registry that SQLAlchemy uses to know which Python classes
           are database tables. All our models inherit from Base.

HOW TO USE THE SESSION (the correct pattern):
  with get_db() as db:
      db.add(some_row)
      db.commit()
  # Session is automatically closed when the `with` block ends.

WHY CONTEXT MANAGER (with get_db()):
  Always guarantees the session is closed, even if an exception happens.
  A forgotten open session can leak connections and corrupt data.

SWITCHING TO POSTGRESQL LATER:
  1. pip install psycopg2-binary
  2. Change DB_URL in config.py to:
     "postgresql://user:password@localhost:5432/biz_db"
  3. That's it — models.py, services, and tests stay exactly the same.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Declarative Base
# ─────────────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Parent class for all ORM models.

    Every model (Sales, Expenses, UploadLog) inherits from this.
    Base.metadata holds a registry of all table definitions, which is
    used by init_db() to create the actual tables in the database.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────
# check_same_thread=False is required for SQLite when used with Streamlit,
# which runs in a multi-threaded environment.
# This argument is silently ignored if we switch to PostgreSQL.
_connect_args = {"check_same_thread": False} if "sqlite" in settings.DB_URL else {}

engine = create_engine(
    settings.DB_URL,
    connect_args=_connect_args,
    # echo=True prints every SQL statement to the console — useful for
    # debugging but noisy. Change to True temporarily when debugging SQL.
    echo=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# SQLite-specific: enable WAL mode and foreign-key enforcement
# ─────────────────────────────────────────────────────────────────────────────
# SQLite by default does NOT enforce foreign keys — we have to turn it on.
# WAL (Write-Ahead Logging) mode allows concurrent reads while a write is
# happening, which prevents "database is locked" errors in Streamlit.
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # type: ignore[type-arg]
    """
    Runs once every time a new low-level DB connection is opened.
    Only has any effect on SQLite; PostgreSQL ignores PRAGMA statements.
    """
    if "sqlite" in settings.DB_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")   # enforce FK constraints
        cursor.execute("PRAGMA journal_mode = WAL")  # allow concurrent reads
        cursor.close()


# ─────────────────────────────────────────────────────────────────────────────
# Session Factory
# ─────────────────────────────────────────────────────────────────────────────
# SessionLocal is a factory (a class) that creates new Session objects.
# autocommit=False means we explicitly call db.commit() — nothing is saved
# until we say so. autoflush=False avoids surprising automatic SQL.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# Session Context Manager
# ─────────────────────────────────────────────────────────────────────────────
@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session as a context manager.

    Usage:
        with get_db() as db:
            db.add(some_model_instance)
            db.commit()

    Guarantees:
      - The session is always closed, even if an exception is raised.
      - On exception, the session is rolled back automatically so no
        partial data is written to the database.

    WHY NOT RETURN A SESSION DIRECTLY?
      If you forget to close a session (db.close()), you leak the
      connection. The `with` keyword makes closing automatic.
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()   # undo any changes made in this session
        raise           # re-raise the exception so the caller knows
    finally:
        db.close()      # always close, regardless of success or failure


# ─────────────────────────────────────────────────────────────────────────────
# Initialise the Database
# ─────────────────────────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Create all tables defined in models.py if they don't already exist.

    Safe to call on every app startup — SQLAlchemy uses CREATE TABLE IF NOT
    EXISTS so existing data is never wiped.

    This is our simple dev-time migration approach. In Phase 6 we'll add
    Alembic for proper, versioned migrations.

    IMPORTANT: models.py must be imported BEFORE this function is called
    so that SQLAlchemy's Base knows about those table classes. That's why
    the import is here at the bottom, not at the top of the file.
    """
    # Importing here guarantees models are registered with Base before
    # create_all() runs. Without this import, the tables won't be created.
    import db.models  # noqa: F401  (imported for its side effect of registration)

    Base.metadata.create_all(bind=engine)


def get_engine():
    """Return the shared engine. Useful for pandas read_sql and testing."""
    return engine


def health_check() -> bool:
    """
    Return True if the database is reachable, False otherwise.
    Used at startup to give a friendly error instead of a cryptic crash.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
