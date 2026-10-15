"""
tests/test_benchmark.py
-----------------------
Automated test suite validating the golden benchmark dataset and deterministic calculations.
"""

import json
from pathlib import Path
import pytest

from scripts.run_accuracy_benchmark import (
    BENCHMARK_TENANT,
    compute_deterministic_number,
    setup_benchmark_data,
)

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
        assert len(data) == 25, f"Expected 25 benchmark questions, found {len(data)}"

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

        for item in data:
            computed = compute_deterministic_number(item)
            expected = float(item["expected_value"])
            assert abs(computed - expected) < 0.01, (
                f"Question {item['id']} ('{item['question']}') mismatch: "
                f"expected {expected}, computed {computed}"
            )
