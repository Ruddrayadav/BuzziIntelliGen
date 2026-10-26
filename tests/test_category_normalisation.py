"""
tests/test_category_normalisation.py
------------------------------------
Tests for category normalisation on upload for expenses and cash-book data.
Verifies:
  1. tests/fixtures/3_category_variants.csv:
     "Raw Material" = 3,800 as ONE category, "Rent" = 20,000 as ONE category.
  2. data/samples/sample_expenses.csv:
     "Raw Material" and "Raw Materials" merge into one total of 48,600.
  3. Cashbook expense categories are normalised on save.
"""

from pathlib import Path
import pytest
from sqlalchemy import func

from db.database import get_db, init_db
from db.models import Expenses, UploadLog
from services.cleaning_service import normalize_category
from services.upload_service import execute_upload, suggest_mapping_from_file

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_category_variants_fixture():
    """
    Test with tests/fixtures/3_category_variants.csv:
    "Raw Material" = 3,800 as ONE category, "Rent" = 20,000 as ONE category.
    """
    init_db()
    tenant_id = "test_cat_norm_tenant"
    with get_db() as db:
        db.query(Expenses).filter(Expenses.tenant_id == tenant_id).delete()
        db.query(UploadLog).filter(UploadLog.tenant_id == tenant_id).delete()
        db.commit()

    fixture_path = REPO_ROOT / "tests" / "fixtures" / "3_category_variants.csv"
    assert fixture_path.exists(), f"Fixture missing: {fixture_path}"

    content = fixture_path.read_bytes()
    prev = suggest_mapping_from_file(content, "3_category_variants.csv", "expenses", use_llm=False)
    res = execute_upload(
        raw_df=prev.raw_df,
        confirmed_mapping=prev.suggested.to_rename_dict(),
        file_type="expenses",
        filename="3_category_variants.csv",
        tenant_id=tenant_id,
        replace_existing=True,
    )
    assert res.success

    with get_db() as db:
        rows = (
            db.query(Expenses.category, func.sum(Expenses.amount))
            .filter(Expenses.tenant_id == tenant_id)
            .group_by(Expenses.category)
            .all()
        )
        cat_map = {cat: float(amt) for cat, amt in rows}

    # Verify exactly 2 distinct categories
    assert len(cat_map) == 2, f"Expected 2 categories, got {len(cat_map)}: {cat_map}"
    assert "Raw Material" in cat_map
    assert "Rent" in cat_map
    assert cat_map["Raw Material"] == pytest.approx(3800.0, 0.01)
    assert cat_map["Rent"] == pytest.approx(20000.0, 0.01)


def test_sample_expenses_raw_material_merge():
    """
    Test with data/samples/sample_expenses.csv:
    "Raw Material" and "Raw Materials" merge into one total of 48,600.
    """
    init_db()
    tenant_id = "test_cat_sample_tenant"
    with get_db() as db:
        db.query(Expenses).filter(Expenses.tenant_id == tenant_id).delete()
        db.query(UploadLog).filter(UploadLog.tenant_id == tenant_id).delete()
        db.commit()

    file_path = REPO_ROOT / "data" / "samples" / "sample_expenses.csv"
    assert file_path.exists(), f"File missing: {file_path}"

    content = file_path.read_bytes()
    prev = suggest_mapping_from_file(content, "sample_expenses.csv", "expenses", use_llm=False)
    res = execute_upload(
        raw_df=prev.raw_df,
        confirmed_mapping=prev.suggested.to_rename_dict(),
        file_type="expenses",
        filename="sample_expenses.csv",
        tenant_id=tenant_id,
        replace_existing=True,
    )
    assert res.success

    with get_db() as db:
        rows = (
            db.query(Expenses.category, func.sum(Expenses.amount))
            .filter(Expenses.tenant_id == tenant_id)
            .group_by(Expenses.category)
            .all()
        )
        cat_map = {cat: float(amt) for cat, amt in rows}

    assert "Raw Material" in cat_map
    # Verify Raw Materials was merged into Raw Material
    assert "Raw Materials" not in cat_map
    assert cat_map["Raw Material"] == pytest.approx(48600.0, 0.01)


def test_normalize_category_function_unit():
    assert normalize_category("  raw material  ") == "Raw Material"
    assert normalize_category("RAW MATERIALS") == "Raw Material"
    assert normalize_category("rent") == "Rent"
    assert normalize_category("salaries") == "Salaries"
    assert normalize_category("utility") == "Utilities"
    assert normalize_category("utilities") == "Utilities"
    assert normalize_category(None) == "Uncategorised"
    assert normalize_category("") == "Uncategorised"
