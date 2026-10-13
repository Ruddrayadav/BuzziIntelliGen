"""
tests/test_cleaning.py
-----------------------
Unit tests for services/cleaning_service.py.

HOW TO RUN:
  # From the project root, with venv activated:
  pytest tests/test_cleaning.py -v

WHAT "UNIT TEST" MEANS:
  A unit test calls ONE small function with a known input and checks that
  the output matches what we expect. If the function is wrong, the test
  fails and tells us exactly which case broke.

  pytest is the test runner. It finds all functions starting with `test_`
  and runs them. A test PASSES if it raises no exceptions. A test FAILS if
  an `assert` statement is False or an unexpected exception is raised.

WHY TEST WITH THE ACTUAL MESSY SAMPLE FILE?
  It's not enough to test with clean made-up data. Our sample CSV has the
  same problems as real restaurant files. If cleaning_service handles those,
  it can handle the real thing.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from services.cleaning_service import (
    CleaningResult,
    _normalize_text,
    _parse_date,
    _parse_money,
    clean_dataframe,
    clean_expenses,
    clean_sales,
)

# Path to sample files (relative to project root, resolved absolutely)
SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"
SALES_CSV = SAMPLES_DIR / "sample_sales.csv"
EXPENSES_CSV = SAMPLES_DIR / "sample_expenses.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _parse_money
# ─────────────────────────────────────────────────────────────────────────────
class TestParseMoney:
    """
    We test _parse_money in isolation.
    If it fails, we know exactly where the bug is — no guessing.
    """

    def test_plain_integer(self):
        assert _parse_money(320) == 320.0

    def test_plain_string_number(self):
        assert _parse_money("320") == 320.0

    def test_rupee_symbol(self):
        assert _parse_money("₹640") == 640.0

    def test_rupee_with_comma_thousands(self):
        assert _parse_money("₹25,000") == 25000.0

    def test_rupee_with_comma_smaller(self):
        assert _parse_money("₹1,200") == 1200.0

    def test_no_symbol_with_comma(self):
        assert _parse_money("1,200") == 1200.0

    def test_float_value(self):
        assert _parse_money(1200.50) == 1200.50

    def test_empty_string_returns_none(self):
        assert _parse_money("") is None

    def test_nan_returns_none(self):
        assert _parse_money(float("nan")) is None

    def test_text_returns_none(self):
        assert _parse_money("N/A") is None

    def test_none_returns_none(self):
        assert _parse_money(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _parse_date
# ─────────────────────────────────────────────────────────────────────────────
class TestParseDate:
    """
    Every date format that appears in our sample CSVs must be handled.
    If a new date format breaks in production, add a test case here.
    """

    def test_iso_format(self):
        # 2024-01-03 — the standard format
        assert _parse_date("2024-01-03") == date(2024, 1, 3)

    def test_dd_mm_yyyy_slash(self):
        # 03/01/2024 — most common Indian format
        assert _parse_date("03/01/2024") == date(2024, 1, 3)

    def test_dd_mm_yyyy_dash(self):
        # 01-02-2024
        assert _parse_date("01-02-2024") == date(2024, 2, 1)

    def test_dd_mon_yyyy(self):
        # 5-Jan-2024
        assert _parse_date("5-Jan-2024") == date(2024, 1, 5)

    def test_mon_d_yyyy(self):
        # Jan 4 2024
        assert _parse_date("Jan 4 2024") == date(2024, 1, 4)

    def test_pandas_timestamp(self):
        # pandas Timestamp object (what pd.read_csv produces for some dates)
        ts = pd.Timestamp("2024-01-10")
        assert _parse_date(ts) == date(2024, 1, 10)

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_nan_returns_none(self):
        assert _parse_date(float("nan")) is None

    def test_gibberish_returns_none(self):
        assert _parse_date("not-a-date") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _normalize_text
# ─────────────────────────────────────────────────────────────────────────────
class TestNormalizeText:
    """
    Text normalization is critical for deduplication.
    'butter chicken' and 'BUTTER CHICKEN' must become 'Butter Chicken'.
    """

    def test_lowercase_to_title(self):
        assert _normalize_text("butter chicken") == "Butter Chicken"

    def test_uppercase_to_title(self):
        assert _normalize_text("BUTTER CHICKEN") == "Butter Chicken"

    def test_double_space_collapsed(self):
        # "Butter  Chicken" (two spaces) → "Butter Chicken" (one space)
        assert _normalize_text("Butter  Chicken") == "Butter Chicken"

    def test_leading_trailing_whitespace(self):
        assert _normalize_text("  Paneer Tikka  ") == "Paneer Tikka"

    def test_empty_string_returns_none(self):
        assert _normalize_text("") is None

    def test_nan_returns_none(self):
        assert _normalize_text(float("nan")) is None

    def test_title_case_false(self):
        # For descriptions we sometimes want to preserve original casing
        result = _normalize_text("monthly shop RENT", title_case=False)
        assert result == "monthly shop RENT"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for clean_sales (using the actual messy CSV)
# ─────────────────────────────────────────────────────────────────────────────
class TestCleanSales:
    """
    Integration tests: load the messy sample CSV and run the full pipeline.
    We check the output counts and spot-check specific values.
    """

    @pytest.fixture
    def raw_sales_df(self) -> pd.DataFrame:
        """Load the messy sample CSV. This fixture runs before each test."""
        df = pd.read_csv(SALES_CSV)
        # Rename columns to our standard schema (mapping_service does this
        # in real usage, but here we do it manually to isolate cleaning logic)
        df = df.rename(columns={
            "item_name": "product",
            "total": "revenue",
        })
        return df

    def test_returns_cleaning_result(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        assert isinstance(result, CleaningResult)

    def test_clean_count_less_than_raw(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        # Cleaning should always reduce or equal the row count
        assert result.clean_count <= result.raw_count
        assert result.raw_count == len(raw_sales_df)

    def test_duplicates_removed(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        # We no longer drop duplicates because identical sales on the same day are valid
        assert result.duplicates_removed == 0, "Expected duplicates to be kept"

    def test_revenue_is_numeric(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        # After cleaning, revenue must be float — no "₹640" strings
        assert result.clean_df["revenue"].dtype == float

    def test_no_null_revenue(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        assert result.clean_df["revenue"].isna().sum() == 0

    def test_no_null_date(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        assert result.clean_df["date"].isna().sum() == 0

    def test_dates_are_date_objects(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        # Every date in the clean DataFrame must be a Python date object
        for d in result.clean_df["date"]:
            assert isinstance(d, date), f"Expected date, got {type(d)}: {d}"

    def test_product_names_title_cased(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        products = result.clean_df["product"].unique()
        # All products must be Title Case — no "butter chicken" or "BUTTER CHICKEN"
        for p in products:
            assert p == p.title() or p == _normalize_text(p), (
                f"Product {p!r} is not normalized"
            )

    def test_butter_chicken_deduplicated(self, raw_sales_df):
        """
        The sample CSV has 'Butter Chicken' entered 2 different ways on Jan 3:
          row 1001: Butter Chicken   2024-01-03   ₹640
          row 1002: butter chicken   03/01/2024   640
        After cleaning, both are valid and should BOTH be kept.
        """
        result = clean_sales(raw_sales_df)
        jan3_butterchicken = result.clean_df[
            (result.clean_df["date"] == date(2024, 1, 3)) &
            (result.clean_df["product"] == "Butter Chicken") &
            (result.clean_df["revenue"] == 640.0)
        ]
        assert len(jan3_butterchicken) == 1, (
            f"Expected 1 Butter Chicken row for Jan 3 with 640.0 revenue, got {len(jan3_butterchicken)}"
        )

    def test_success_property_true(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        assert result.success is True

    def test_summary_string_non_empty(self, raw_sales_df):
        result = clean_sales(raw_sales_df)
        assert len(result.summary()) > 0

    def test_missing_product_retained(self, raw_sales_df):
        # Create a row with missing product but valid date and revenue
        test_row = pd.DataFrame([{
            "date": "2024-01-01",
            "product": None,
            "category": "Food",
            "revenue": "100.0"
        }])
        df = pd.concat([raw_sales_df, test_row], ignore_index=True)
        result = clean_sales(df)
        
        # Check that the row was kept and assigned 'Unknown' product
        unknown_rows = result.clean_df[
            (result.clean_df["date"] == date(2024, 1, 1)) & 
            (result.clean_df["revenue"] == 100.0)
        ]
        assert len(unknown_rows) == 1
        assert unknown_rows.iloc[0]["product"] == "Unknown"

# ─────────────────────────────────────────────────────────────────────────────
# Tests for clean_expenses (using the actual messy CSV)
# ─────────────────────────────────────────────────────────────────────────────
class TestCleanExpenses:

    @pytest.fixture
    def raw_expenses_df(self) -> pd.DataFrame:
        """Load the messy expenses CSV with standard column names."""
        df = pd.read_csv(EXPENSES_CSV)
        # Rename to standard schema
        df = df.rename(columns={
            "Date": "date",
            "Type": "category",
            "Details": "description",
            "Amount": "amount",
        })
        return df

    def test_returns_cleaning_result(self, raw_expenses_df):
        result = clean_expenses(raw_expenses_df)
        assert isinstance(result, CleaningResult)

    def test_duplicates_removed(self, raw_expenses_df):
        result = clean_expenses(raw_expenses_df)
        # Jan 1 rent appears twice in the sample but we keep duplicates now
        assert result.duplicates_removed == 0

    def test_amount_is_numeric(self, raw_expenses_df):
        result = clean_expenses(raw_expenses_df)
        assert result.clean_df["amount"].dtype == float

    def test_no_null_amount(self, raw_expenses_df):
        result = clean_expenses(raw_expenses_df)
        assert result.clean_df["amount"].isna().sum() == 0

    def test_categories_title_cased(self, raw_expenses_df):
        result = clean_expenses(raw_expenses_df)
        # "raw material", "Raw Materials", "raw materials" → "Raw Materials"
        categories = result.clean_df["category"].unique()
        for cat in categories:
            assert cat == cat.title(), f"Category {cat!r} not title-cased"

    def test_rent_deduplicated(self, raw_expenses_df):
        """Jan 1 rent (₹25,000) appears twice — both should remain."""
        result = clean_expenses(raw_expenses_df)
        jan1_rent = result.clean_df[
            (result.clean_df["date"] == date(2024, 1, 1)) &
            (result.clean_df["category"] == "Rent") &
            (result.clean_df["amount"] == 25000.0)
        ]
        assert len(jan1_rent) == 2, (
            f"Expected 2 rent rows for Jan 1 (duplicates kept), got {len(jan1_rent)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests for clean_dataframe (the public router function)
# ─────────────────────────────────────────────────────────────────────────────
class TestCleanDataframe:

    def test_routes_to_sales(self):
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "order_id": ["1001"],
            "product": ["Chai"],
            "category": ["Beverages"],
            "quantity": [2],
            "unit_price": [40],
            "revenue": [80],
        })
        result = clean_dataframe(df, file_type="sales")
        assert isinstance(result, CleaningResult)
        assert result.clean_count == 1

    def test_routes_to_expenses(self):
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "category": ["Rent"],
            "description": ["Monthly rent"],
            "amount": [25000],
        })
        result = clean_dataframe(df, file_type="expenses")
        assert isinstance(result, CleaningResult)
        assert result.clean_count == 1

    def test_unknown_type_raises(self):
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="Unknown file_type"):
            clean_dataframe(df, file_type="inventory")

    def test_file_type_case_insensitive(self):
        """'Sales', 'SALES', 'sales' should all work."""
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "order_id": [None],
            "product": ["Chai"],
            "category": ["Beverages"],
            "quantity": [2],
            "unit_price": [40],
            "revenue": [80],
        })
        result = clean_dataframe(df, file_type="SALES")
        assert result.clean_count == 1
