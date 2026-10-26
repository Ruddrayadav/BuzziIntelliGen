"""File-type detector supporting whole-word matching, value-based heuristics, and cash-book detection."""

import re
from typing import Optional
import pandas as pd


# ── Keyword Dictionaries with Word Boundaries ─────────────────────────────────

SALES_COLUMN_WORDS = (
    "sale", "sales", "revenue", "product", "products", "item", "items",
    "order", "orders", "order_id", "quantity", "qty", "unit_price",
    "selling_price", "subtotal", "customer", "invoice", "dish", "menu"
)

EXPENSE_COLUMN_WORDS = (
    "expense", "expenses", "cost", "costs", "vendor", "supplier", "payment",
    "bill", "bills", "salary", "salaries", "payroll", "utilities", "maintenance",
    "rent", "purchase", "purchases", "debit"
)

# Common small-business expense category names appearing in cell values
EXPENSE_CATEGORY_KEYWORDS = (
    "rent", "salary", "salaries", "wage", "wages", "electricity", "electric",
    "utility", "utilities", "raw material", "raw materials", "maintenance",
    "marketing", "cleaning", "repair", "repairs", "supplies", "water bill",
    "lpg", "cylinder", "vendor", "stationery", "internet", "transport",
    "freight", "packaging", "ad", "ads", "tax", "gst"
)

# Inflow vs Outflow keywords for cash-book / ledger files
INFLOW_KEYWORDS = {"sale", "sales", "credit", "cr", "income", "receipt", "receipts", "in", "deposit", "money_in", "cash_in"}
OUTFLOW_KEYWORDS = {"expense", "expenses", "debit", "dr", "payment", "payments", "purchase", "purchases", "out", "withdrawal", "money_out", "cash_out"}


def _has_word(text: str, word: str) -> bool:
    """Check if whole word exists in text using regex boundary \\b."""
    normalized = str(text).replace("_", " ").replace("-", " ")
    pattern = r'\b' + re.escape(word) + r'\b'
    return bool(re.search(pattern, normalized, re.IGNORECASE))


def detect_file_type(columns: list[str], df: Optional[pd.DataFrame] = None) -> str:
    """
    Classify uploaded file into 'sales', 'expenses', or 'cashbook'.

    Uses:
      1. Whole-word header matching with regex boundaries (avoids 'rent' matching 'current').
      2. Cash-book structural detection (Debit & Credit columns, or Type column with mixed In/Out).
      3. Value-based inspection of category/detail text cells when headers are generic (e.g. Type, Details, Amount).

    Returns:
        'sales' | 'expenses' | 'cashbook'
    """
    cleaned_cols = [str(c).strip() for c in columns if c is not None]
    col_lower_map = {c: c.lower().replace("_", " ").replace("-", " ") for c in cleaned_cols}

    # ── 1. Check for Cash-Book Structure ──────────────────────────────────────
    # Check 1a: Dual debit & credit amount columns
    has_debit_col = any(
        any(_has_word(col_text, kw) for kw in ("debit", "dr", "paid", "withdrawal", "money out", "cash out"))
        for col_text in col_lower_map.values()
    )
    has_credit_col = any(
        any(_has_word(col_text, kw) for kw in ("credit", "cr", "received", "deposit", "money in", "cash in", "receipt"))
        for col_text in col_lower_map.values()
    )

    if has_debit_col and has_credit_col:
        return "cashbook"

    # Check 1b: Type column with mixed Inflow and Outflow entries in DataFrame
    if df is not None and not df.empty:
        type_candidates = [
            c for c in cleaned_cols
            if any(_has_word(col_lower_map[c], kw) for kw in ("type", "txn type", "transaction type", "entry", "dr cr", "cr dr"))
        ]
        for col in type_candidates:
            vals = df[col].dropna().astype(str).str.strip().str.lower().unique()
            has_inflow = any(any(_has_word(v, kw) for kw in INFLOW_KEYWORDS) for v in vals)
            has_outflow = any(any(_has_word(v, kw) for kw in OUTFLOW_KEYWORDS) for v in vals)
            if has_inflow and has_outflow:
                return "cashbook"

    # ── 2. Header-Based Whole-Word Scoring ────────────────────────────────────
    sales_score = 0
    expense_score = 0

    for col_orig, col_text in col_lower_map.items():
        if any(_has_word(col_text, w) for w in SALES_COLUMN_WORDS):
            sales_score += 1
        if any(_has_word(col_text, w) for w in EXPENSE_COLUMN_WORDS):
            expense_score += 1

    # If headers show a decisive classification without ambiguity, return early
    if abs(sales_score - expense_score) >= 2:
        return "sales" if sales_score > expense_score else "expenses"

    # ── 3. Value-Based Inspection (Breaks ties or identifies generic headers like Date, Type, Details, Amount)
    if df is not None and not df.empty:
        text_cols = [
            c for c in cleaned_cols
            if c in df.columns and (pd.api.types.is_string_dtype(df[c]) or pd.api.types.is_object_dtype(df[c]))
        ]

        value_expense_hits = 0
        value_sales_hits = 0

        # Sample up to 50 rows
        sample_df = df[text_cols].head(50)
        for c in text_cols:
            col_text = col_lower_map[c]
            is_descriptive_col = any(_has_word(col_text, kw) for kw in (
                "type", "category", "detail", "details", "particular", "particulars",
                "description", "item", "narration", "remarks"
            ))
            multiplier = 2 if is_descriptive_col else 1

            for val in sample_df[c].dropna():
                val_str = str(val).strip().lower()
                if not val_str:
                    continue

                if any(_has_word(val_str, kw) for kw in EXPENSE_CATEGORY_KEYWORDS):
                    value_expense_hits += multiplier

                if any(_has_word(val_str, kw) for kw in ("order", "table", "dine in", "takeaway", "parcel", "swiggy", "zomato")):
                    value_sales_hits += multiplier

        if value_expense_hits > 0:
            expense_score += value_expense_hits
        if value_sales_hits > 0:
            sales_score += value_sales_hits

    # Default to sales if exactly tied with 0 score, else choose winner
    return "expenses" if expense_score > sales_score else "sales"
