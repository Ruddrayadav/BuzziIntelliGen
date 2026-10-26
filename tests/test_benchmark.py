"""
tests/test_benchmark.py
-----------------------
Automated test suite validating the golden benchmark dataset, deterministic
calculations, separate evaluation tiers, and defensive out-of-scope handling.
"""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from scripts.run_accuracy_benchmark import (
    BENCHMARK_TENANT,
    SENSITIVE_TENANT_NUMBERS,
    compute_deterministic_number,
    format_benchmark_number,
    setup_benchmark_data,
    text_contains_expected_number,
)
from services.ai_service import ask_question

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestGoldenBenchmark:
    @classmethod
    def setup_class(cls):
        setup_benchmark_data()

    def test_golden_questions_json_structure(self):
        questions_path = REPO_ROOT / "tests" / "golden_questions.json"
        assert questions_path.exists(), "tests/golden_questions.json must exist"

        with open(questions_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 33, f"Expected 33 benchmark questions (25 analytical + 8 out-of-scope), found {len(data)}"

        analytical = [q for q in data if not q.get("is_out_of_scope", False)]
        out_of_scope = [q for q in data if q.get("is_out_of_scope", False)]

        assert len(analytical) == 25, f"Expected 25 analytical questions, found {len(analytical)}"
        assert len(out_of_scope) == 8, f"Expected 8 out-of-scope questions, found {len(out_of_scope)}"

        required_keys = {"id", "question", "expected_intent", "expected_metric", "expected_value"}
        for item in data:
            assert required_keys.issubset(item.keys())
            assert isinstance(item["id"], int)
            assert isinstance(item["question"], str)
            assert isinstance(item["expected_value"], (int, float))

    def test_deterministic_ground_truth_accuracy(self):
        questions_path = REPO_ROOT / "tests" / "golden_questions.json"
        with open(questions_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        analytical = [q for q in data if not q.get("is_out_of_scope", False)]
        for item in analytical:
            computed = compute_deterministic_number(item)
            expected = float(item["expected_value"])
            assert abs(computed - expected) < 0.01, (
                f"Question {item['id']} ('{item['question']}') mismatch: "
                f"expected {expected}, computed {computed}"
            )

    def test_out_of_scope_questions_structure(self):
        questions_path = REPO_ROOT / "tests" / "golden_questions.json"
        with open(questions_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        out_of_scope = [q for q in data if q.get("is_out_of_scope", False)]
        for item in out_of_scope:
            assert item["expected_intent"] == "unknown"
            assert item["is_out_of_scope"] is True

    def test_out_of_scope_safety_ask_question(self):
        """Out-of-scope questions must route to unknown and not return data or unasked business metrics."""
        with patch("services.ai_service._identify_intent") as mock_intent:
            mock_intent.return_value = {
                "intent": "unknown",
                "metric": "revenue",
                "order": "top",
                "period": "all",
                "limit": 5,
            }
            questions_path = REPO_ROOT / "tests" / "golden_questions.json"
            with open(questions_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            oos = [q for q in data if q.get("is_out_of_scope", False)]
            for item in oos:
                ans = ask_question(item["question"], BENCHMARK_TENANT)
                assert ans.intent == "unknown"
                assert ans.data is None
                # Must not contain unasked sensitive tenant metrics
                for s_num in SENSITIVE_TENANT_NUMBERS:
                    assert str(s_num) not in ans.text

    def test_format_benchmark_number_units_no_rupee(self):
        """Format units without rupee sign and as plain integer."""
        formatted_units = format_benchmark_number(36.0, "units")
        assert formatted_units == "36"
        assert "₹" not in formatted_units

        formatted_rev = format_benchmark_number(27530.0, "revenue")
        assert formatted_rev == "27,530.00"
        assert "₹" not in formatted_rev

    def test_text_contains_expected_number(self):
        assert text_contains_expected_number(27530.0, "Your total revenue is ₹27,530.00", "revenue")
        assert text_contains_expected_number(36.0, "Masala Chai sold 36 units", "units")
        assert text_contains_expected_number(-257669.0, "Net profit is -257,669", "revenue")
        assert not text_contains_expected_number(99999.0, "Total revenue is 27,530", "revenue")
