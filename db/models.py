"""
db/models.py
------------
SQLAlchemy ORM table definitions.

WHY AN ORM?
  Writing raw SQL for every query is repetitive and error-prone.
  SQLAlchemy lets us define tables as Python classes and write queries
  in Python. If we later switch from SQLite to PostgreSQL, these class
  definitions stay exactly the same — only the DB_URL in config.py changes.

HOW TO READ THESE CLASSES:
  Each class = one database table.
  Each class attribute with Column() = one column in that table.
  The type inside Column() (String, Float, Date, etc.) maps to a SQL type.

TENANT ISOLATION:
  Every table has a `tenant_id` column. When an owner logs in, their
  user ID becomes their tenant_id. ALL queries must filter by tenant_id
  so owners never see each other's data. This is enforced at the service
  layer, not just the UI layer.
"""

from datetime import datetime, date as date_type

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# User (Tenant)
# ─────────────────────────────────────────────────────────────────────────────
class User(Base):
    """
    Represents a registered business owner.
    
    The tenant_id is the primary security boundary for the entire app.
    When a user logs in, we store their tenant_id in the session and 
    use it to filter all queries in Sales, Expenses, and UploadLog.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(32), nullable=False)
    
    # The unique identifier used across all data tables for this owner
    tenant_id = Column(String(64), unique=True, nullable=False, index=True)
    business_name = Column(String(100), nullable=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User {self.username} tenant={self.tenant_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# UploadLog
# ─────────────────────────────────────────────────────────────────────────────
class UploadLog(Base):
    """
    Records every file upload attempt.

    WHY THIS TABLE EXISTS:
      We want to know:
      - Which file did these rows come from?
      - How many rows were in the raw file vs. after cleaning?
      - Did the upload succeed, partially succeed, or fail?

    Linking Sales/Expenses rows back to an UploadLog lets the owner
    see "these 120 rows came from your January sales file" and lets
    us delete or re-process a bad upload cleanly.
    """

    __tablename__ = "upload_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Security boundary — which user owns this upload?
    tenant_id = Column(String(64), nullable=False, index=True)

    # The original filename the user chose (e.g. "Jan_Sales.xlsx").
    # We store this for display only — never execute it as a path.
    filename = Column(String(255), nullable=False)

    # "sales" or "expenses"
    file_type = Column(String(20), nullable=False)

    # SHA-256 hash of the uploaded file bytes for duplicate detection per tenant
    file_hash = Column(String(64), nullable=True, index=True)


    # How many rows were in the raw uploaded file?
    row_count_raw = Column(Integer, nullable=True)

    # How many rows made it through cleaning and were stored?
    row_count_clean = Column(Integer, nullable=True)

    # "success" | "partial" | "failed"
    status = Column(String(20), nullable=False, default="success")

    # Human-readable notes (e.g. "12 duplicate rows removed, 3 rows had
    # unparseable dates and were dropped"). Shown to the owner.
    notes = Column(Text, nullable=True)

    # When was this upload processed?
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # SQLAlchemy "relationship" — lets us write upload.sales_rows in Python
    # to get all Sales rows linked to this upload. backref="upload" adds a
    # reverse link so a Sales row can do row.upload to get its UploadLog.
    sales_rows = relationship("Sales", back_populates="upload", cascade="all, delete-orphan")
    expense_rows = relationship("Expenses", back_populates="upload", cascade="all, delete-orphan")
    rejected_rows = relationship("RejectedRow", back_populates="upload", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<UploadLog id={self.id} tenant={self.tenant_id} "
            f"file={self.filename} status={self.status}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# RejectedRow
# ─────────────────────────────────────────────────────────────────────────────
class RejectedRow(Base):
    """
    Stores rows that were dropped during the cleaning process (Phase 1).
    Instead of silently ignoring data, we store it here with a reason
    so the owner can audit what was missed.
    """
    __tablename__ = "rejected_rows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    
    upload_id = Column(
        Integer, ForeignKey("upload_log.id", ondelete="CASCADE"), nullable=False
    )
    upload = relationship("UploadLog", back_populates="rejected_rows")

    # Store the row as a JSON string so we don't need a strict schema
    row_data = Column(Text, nullable=False)
    
    # Why was it rejected? (e.g., "Missing revenue", "Exact duplicate")
    reason = Column(String(255), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<RejectedRow id={self.id} upload={self.upload_id} reason={self.reason!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Sales
# ─────────────────────────────────────────────────────────────────────────────
class Sales(Base):
    """
    Standard internal schema for sales data.

    WHY A STANDARD SCHEMA?
      Every owner's CSV has different column names ("Amt", "Total", "Revenue",
      "Sale Price"). The mapping step (Step 1D) converts those messy columns
      into this fixed schema. From here on, ALL code only talks to THIS schema,
      never to raw CSV column names. That's why analytics, charts, and AI
      prompts are simple — they always see the same columns.

    COLUMN DESIGN:
      - Nullable columns (quantity, unit_price) because real data often has gaps.
      - revenue is NOT nullable — it's the most important number; rows without
        it are dropped during cleaning.
      - order_id is nullable because some cafes don't use order numbers.
    """

    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Security ───────────────────────────────────────────────────────────
    tenant_id = Column(String(64), nullable=False, index=True)

    # ── Link to upload ────────────────────────────────────────────────────
    # ForeignKey means "this column references the id column in upload_log".
    # ondelete="CASCADE" means if the UploadLog row is deleted, all its
    # Sales rows are deleted automatically.
    upload_id = Column(
        Integer, ForeignKey("upload_log.id", ondelete="CASCADE"), nullable=False
    )
    upload = relationship("UploadLog", back_populates="sales_rows")

    # ── Standard sales fields (the internal schema) ───────────────────────
    date = Column(Date, nullable=False)
    order_id = Column(String(50), nullable=True)       # some shops don't use order IDs
    product = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    quantity = Column(Float, nullable=True)            # nullable: not all files have qty
    unit_price = Column(Float, nullable=True)          # nullable: not all files have price
    revenue = Column(Float, nullable=False)            # MUST have revenue — core metric

    # ── Audit ─────────────────────────────────────────────────────────────
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ── Composite index ───────────────────────────────────────────────────
    # Why? Our most common query pattern is:
    #   "Get all sales for tenant X between date A and date B"
    # An index on (tenant_id, date) makes this query fast even with
    # millions of rows. Without it, the DB scans every row every time.
    __table_args__ = (
        Index("ix_sales_tenant_date", "tenant_id", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Sales id={self.id} tenant={self.tenant_id} "
            f"date={self.date} product={self.product!r} revenue={self.revenue}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Expenses
# ─────────────────────────────────────────────────────────────────────────────
class Expenses(Base):
    """
    Standard internal schema for expense data.

    Simpler than Sales because expenses don't have product/quantity concepts.
    The key fields are: when was it, what type of cost, how much.
    """

    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Security ───────────────────────────────────────────────────────────
    tenant_id = Column(String(64), nullable=False, index=True)

    # ── Link to upload ────────────────────────────────────────────────────
    upload_id = Column(
        Integer, ForeignKey("upload_log.id", ondelete="CASCADE"), nullable=False
    )
    upload = relationship("UploadLog", back_populates="expense_rows")

    # ── Standard expense fields ───────────────────────────────────────────
    date = Column(Date, nullable=False)
    category = Column(String(100), nullable=False)     # Rent, Salaries, Raw Materials…
    description = Column(String(500), nullable=True)   # Optional free-text detail
    amount = Column(Float, nullable=False)             # MUST have amount

    # ── Audit ─────────────────────────────────────────────────────────────
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ── Composite index ───────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_expenses_tenant_date", "tenant_id", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Expenses id={self.id} tenant={self.tenant_id} "
            f"date={self.date} category={self.category!r} amount={self.amount}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Revenue Targets (Step 2.3)
# ─────────────────────────────────────────────────────────────────────────────
class RevenueTarget(Base):
    """
    Stores monthly revenue targets set by the business owner.
    One target per tenant per month (YYYY-MM).
    """

    __tablename__ = "revenue_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    month = Column(String(7), nullable=False)  # "YYYY-MM"
    target_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "month", name="uq_revenue_target_tenant_month"),
        Index("ix_revenue_target_tenant_month", "tenant_id", "month"),
    )

    def __repr__(self) -> str:
        return f"<RevenueTarget tenant={self.tenant_id} month={self.month} target={self.target_amount}>"


# ─────────────────────────────────────────────────────────────────────────────
# Chat Messages (Step 3.3)
# ─────────────────────────────────────────────────────────────────────────────
class ChatMessage(Base):
    """
    Stores natural language Q&A history per tenant for Ask AI.
    Strictly isolated by tenant_id.
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    metric = Column(String(50), nullable=True)
    period = Column(String(50), nullable=True)
    period_label = Column(String(100), nullable=True)
    headline = Column(Text, nullable=True)
    table_data = Column(Text, nullable=True)  # JSON-encoded table rows/columns
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_chat_messages_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} tenant={self.tenant_id} q={self.question[:30]!r}>"


