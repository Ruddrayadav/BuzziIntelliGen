"""
tests/test_mapping.py
----------------------
Tests for services/mapping_service.py.

KEY DESIGN DECISION:
  All tests use `use_llm=False`. This means:
    - Tests run without Ollama being active (CI-friendly).
    - We test the rule-based logic thoroughly.
    - The LLM path is tested separately with a mock.

HOW TO RUN:
  pytest tests/test_mapping.py -v
"""

from unittest.mock import patch

import pandas as pd
import pytest

from services.mapping_service import (
    ColumnMapping,
    _match_by_rules,
    _normalize_col,
    apply_mapping,
    suggest_mapping,
)


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _normalize_col
# ─────────────────────────────────────────────────────────────────────────────
class TestNormalizeCol:

    def test_lowercase(self):
        assert _normalize_col("Revenue") == "revenue"

    def test_strips_whitespace(self):
        assert _normalize_col("  date  ") == "date"

    def test_underscores_become_spaces(self):
        assert _normalize_col("unit_price") == "unit price"

    def test_hyphens_become_spaces(self):
        assert _normalize_col("sale-amount") == "sale amount"

    def test_multiple_spaces_collapsed(self):
        assert _normalize_col("order  id") == "order id"

    def test_combined(self):
        assert _normalize_col("  UNIT_PRICE  ") == "unit price"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _match_by_rules
# ─────────────────────────────────────────────────────────────────────────────
class TestMatchByRules:

    # ── Sales aliases ─────────────────────────────────────────────────────────
    def test_standard_name_maps_to_itself_sales(self):
        # If the column is already named correctly, it should still match
        assert _match_by_rules("date", "sales") == "date"
        assert _match_by_rules("product", "sales") == "product"
        assert _match_by_rules("revenue", "sales") == "revenue"

    def test_common_date_aliases(self):
        assert _match_by_rules("Dt", "sales") == "date"
        assert _match_by_rules("Sale Date", "sales") == "date"
        assert _match_by_rules("Transaction Date", "sales") == "date"

    def test_common_product_aliases(self):
        assert _match_by_rules("Item Name", "sales") == "product"
        assert _match_by_rules("Dish", "sales") == "product"
        assert _match_by_rules("Menu Item", "sales") == "product"
        assert _match_by_rules("item", "sales") == "product"

    def test_common_revenue_aliases(self):
        assert _match_by_rules("Total", "sales") == "revenue"
        assert _match_by_rules("Amt", "sales") == "revenue"
        assert _match_by_rules("Sale Amount", "sales") == "revenue"
        assert _match_by_rules("Gross", "sales") == "revenue"

    def test_common_quantity_aliases(self):
        assert _match_by_rules("Qty", "sales") == "quantity"
        assert _match_by_rules("Units", "sales") == "quantity"
        assert _match_by_rules("Pcs", "sales") == "quantity"

    def test_common_unit_price_aliases(self):
        assert _match_by_rules("Price", "sales") == "unit_price"
        assert _match_by_rules("Rate", "sales") == "unit_price"
        assert _match_by_rules("MRP", "sales") == "unit_price"

    def test_order_id_aliases(self):
        assert _match_by_rules("Bill No", "sales") == "order_id"
        assert _match_by_rules("Invoice Number", "sales") == "order_id"
        assert _match_by_rules("Txn ID", "sales") == "order_id"

    # ── Expenses aliases ──────────────────────────────────────────────────────
    def test_expenses_date(self):
        assert _match_by_rules("Date", "expenses") == "date"
        assert _match_by_rules("Payment Date", "expenses") == "date"

    def test_expenses_category(self):
        assert _match_by_rules("Type", "expenses") == "category"
        assert _match_by_rules("Expense Type", "expenses") == "category"
        assert _match_by_rules("Account Head", "expenses") == "category"

    def test_expenses_amount(self):
        assert _match_by_rules("Amount", "expenses") == "amount"
        assert _match_by_rules("Amt", "expenses") == "amount"
        assert _match_by_rules("Cost", "expenses") == "amount"
        assert _match_by_rules("Paid", "expenses") == "amount"

    def test_expenses_description(self):
        assert _match_by_rules("Details", "expenses") == "description"
        assert _match_by_rules("Remarks", "expenses") == "description"
        assert _match_by_rules("Particulars", "expenses") == "description"

    # ── Negative cases ────────────────────────────────────────────────────────
    def test_unknown_column_returns_none(self):
        assert _match_by_rules("SKU_REF_CODE", "sales") is None
        assert _match_by_rules("ZXQRT", "expenses") is None

    def test_case_insensitive(self):
        assert _match_by_rules("TOTAL", "sales") == "revenue"
        assert _match_by_rules("total", "sales") == "revenue"
        assert _match_by_rules("Total", "sales") == "revenue"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for suggest_mapping (rule-based path, use_llm=False)
# ─────────────────────────────────────────────────────────────────────────────
class TestSuggestMapping:

    def test_returns_column_mapping(self):
        cols = ["date", "product", "revenue"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert isinstance(result, ColumnMapping)

    def test_sample_sales_csv_columns(self):
        """
        Our sample_sales.csv has: order_id, date, item_name, category, qty, unit_price, total
        After mapping: item_name→product, total→revenue
        This is exactly the rename our tests/upload flow will do.
        """
        cols = ["order_id", "date", "item_name", "category", "qty", "unit_price", "total"]
        result = suggest_mapping(cols, "sales", use_llm=False)

        assert result.suggested["date"] == "date"
        assert result.suggested["order_id"] == "order_id"
        assert result.suggested["item_name"] == "product"
        assert result.suggested["category"] == "category"
        assert result.suggested["qty"] == "quantity"
        assert result.suggested["unit_price"] == "unit_price"
        assert result.suggested["total"] == "revenue"

    def test_sample_expenses_csv_columns(self):
        """
        Our sample_expenses.csv has: Date, Type, Details, Amount
        """
        cols = ["Date", "Type", "Details", "Amount"]
        result = suggest_mapping(cols, "expenses", use_llm=False)

        assert result.suggested["Date"] == "date"
        assert result.suggested["Type"] == "category"
        assert result.suggested["Details"] == "description"
        assert result.suggested["Amount"] == "amount"

    def test_is_complete_when_required_fields_mapped(self):
        cols = ["date", "item_name", "total"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert result.is_complete is True

    def test_missing_required_detected(self):
        """
        Sales file missing a revenue column → is_complete = False,
        and missing_required includes "revenue".
        """
        cols = ["date", "product"]   # no revenue/total/amount
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert result.is_complete is False
        assert "revenue" in result.missing_required

    def test_unmapped_raw_listed(self):
        cols = ["date", "product", "revenue", "XYZ_MYSTERY_COL"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert "XYZ_MYSTERY_COL" in result.unmapped_raw

    def test_method_tracks_rule_source(self):
        cols = ["date", "total"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert result.method["date"] == "rule"
        assert result.method["total"] == "rule"

    def test_method_marks_unmapped(self):
        cols = ["ZXQRT"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        assert result.method["ZXQRT"] == "unmapped"

    def test_unknown_file_type_raises(self):
        with pytest.raises(ValueError, match="Unknown file_type"):
            suggest_mapping(["date", "amount"], "inventory", use_llm=False)

    def test_to_rename_dict_excludes_none(self):
        cols = ["date", "product", "revenue", "UNKNOWN"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        rename = result.to_rename_dict()
        assert "UNKNOWN" not in rename
        assert rename["date"] == "date"

    def test_summary_lines_non_empty(self):
        cols = ["date", "total", "item_name"]
        result = suggest_mapping(cols, "sales", use_llm=False)
        lines = result.summary_lines()
        assert len(lines) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Tests for LLM path (mocked — no Ollama required)
# ─────────────────────────────────────────────────────────────────────────────
class TestSuggestMappingWithLLM:
    """
    We mock call_llm_json so this test works without Ollama running.

    WHAT IS MOCKING?
      `patch` temporarily replaces the real function with a fake one that
      returns whatever we tell it to. After the test, the real function
      is restored. This lets us test the logic around the LLM call
      without actually calling Ollama.
    """

    def test_llm_result_used_for_unmapped_columns(self):
        """
        When rules can't map "SkuRef", the LLM is called.
        If LLM says SkuRef → order_id, the mapping should reflect that.

        WHY patch "llm.llm.call_llm_json"?
          _match_by_llm does `from llm.llm import call_llm_json` at call time.
          Python's mock.patch must replace the function at its DEFINITION site
          (llm.llm), not at the import site of the caller.
        """
        fake_llm_response = [{"raw": "SkuRef", "standard": "order_id"}]

        with patch("llm.llm.call_llm_json", return_value=fake_llm_response):
            cols = ["date", "product", "revenue", "SkuRef"]
            result = suggest_mapping(cols, "sales", use_llm=True)

        assert result.suggested.get("SkuRef") == "order_id"
        assert result.method.get("SkuRef") == "llm"

    def test_llm_invalid_field_ignored(self):
        """
        If LLM suggests a field name not in our standard schema,
        it must be silently rejected (LLM cannot invent new fields).
        """
        fake_llm_response = [{"raw": "WeirdCol", "standard": "INVENTED_FIELD"}]

        from services.mapping_service import _match_by_llm
        with patch("llm.llm.call_llm_json", return_value=fake_llm_response):
            result = _match_by_llm(["WeirdCol"], "sales")

        # INVENTED_FIELD is not in STANDARD_COLUMNS["sales"] → must be None
        assert result.get("WeirdCol") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests for apply_mapping
# ─────────────────────────────────────────────────────────────────────────────
class TestApplyMapping:

    @pytest.fixture
    def sample_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Dt": ["2024-01-01"],
            "Item Name": ["Butter Chicken"],
            "Amt": [640],
            "Extra Col": ["ignore me"],
        })

    def test_renames_columns(self, sample_df):
        mapping = {"Dt": "date", "Item Name": "product", "Amt": "revenue"}
        result = apply_mapping(sample_df, mapping)
        assert list(result.columns) == ["date", "product", "revenue"]

    def test_drops_unmapped_columns(self, sample_df):
        mapping = {"Dt": "date", "Item Name": "product", "Amt": "revenue"}
        result = apply_mapping(sample_df, mapping)
        # "Extra Col" was not in the mapping, so it must be gone
        assert "Extra Col" not in result.columns

    def test_values_preserved(self, sample_df):
        mapping = {"Dt": "date", "Item Name": "product", "Amt": "revenue"}
        result = apply_mapping(sample_df, mapping)
        assert result["product"].iloc[0] == "Butter Chicken"
        assert result["revenue"].iloc[0] == 640

    def test_missing_key_in_df_ignored(self, sample_df):
        # "NonExistentCol" is in the mapping but not in the DataFrame
        # apply_mapping should silently ignore it
        mapping = {"Dt": "date", "NonExistentCol": "product", "Amt": "revenue"}
        result = apply_mapping(sample_df, mapping)
        assert "date" in result.columns
        assert "revenue" in result.columns
        # product will be absent since NonExistentCol didn't exist
        assert "product" not in result.columns

    def test_empty_mapping_raises(self, sample_df):
        with pytest.raises(ValueError, match="None of the mapping keys"):
            apply_mapping(sample_df, {"NONEXISTENT": "date"})


# ─────────────────────────────────────────────────────────────────────────────
# Integration: suggest → apply → clean pipeline test
# ─────────────────────────────────────────────────────────────────────────────
class TestFullPipeline:
    """
    End-to-end test for the mapping → apply → clean pipeline without the UI.
    This mirrors what upload_service.py will do in the next step.
    """

    def test_sales_csv_through_full_pipeline(self):
        """
        Load sample_sales.csv → suggest mapping → apply → clean.
        The final DataFrame should have standard column names and clean data.
        """
        from pathlib import Path
        from services.cleaning_service import clean_dataframe

        csv_path = Path("data/samples/sample_sales.csv")
        df = pd.read_csv(csv_path)

        # Step 1: suggest mapping (rules only, no LLM)
        mapping = suggest_mapping(df.columns.tolist(), "sales", use_llm=False)
        assert mapping.is_complete, f"Missing: {mapping.missing_required}"

        # Step 2: apply confirmed mapping
        standard_df = apply_mapping(df, mapping.to_rename_dict())
        assert "date" in standard_df.columns
        assert "product" in standard_df.columns
        assert "revenue" in standard_df.columns

        # Step 3: clean
        result = clean_dataframe(standard_df, "sales")
        assert result.success
        assert result.clean_count > 0
        assert result.duplicates_removed == 0

    def test_expenses_csv_through_full_pipeline(self):
        from pathlib import Path
        from services.cleaning_service import clean_dataframe

        csv_path = Path("data/samples/sample_expenses.csv")
        df = pd.read_csv(csv_path)

        mapping = suggest_mapping(df.columns.tolist(), "expenses", use_llm=False)
        assert mapping.is_complete, f"Missing: {mapping.missing_required}"

        standard_df = apply_mapping(df, mapping.to_rename_dict())
        assert "date" in standard_df.columns
        assert "category" in standard_df.columns
        assert "amount" in standard_df.columns

        result = clean_dataframe(standard_df, "expenses")
        assert result.success
        assert result.clean_count > 0
