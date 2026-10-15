"""
tests/test_ai_service.py
------------------------
Tests for the AI Service.
We mock the LLM calls so we don't need Ollama running, ensuring tests are fast and deterministic.
"""

import pytest
from unittest.mock import patch
from datetime import date
import pandas as pd

from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog
from llm.llm import LLMError
from services.ai_service import (
    ask_question,
    Answer,
    _identify_intent,
    _resolve_relative_period,
    _verify_llm_numbers,
)

TENANT = "test_tenant_ai"


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()

        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=1, row_count_clean=1)
        db.add(ul)
        db.flush()

        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), product="Pizza", revenue=500, quantity=5),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), product="Pasta", revenue=200, quantity=2),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 3), product="Pizza", revenue=100, quantity=1),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 5), product="Salad", revenue=150, quantity=3),
        ])

        db.add_all([
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), category="Rent", description="Monthly office rent", amount=300),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 15), category="Utilities", description="Electricity bill", amount=80),
        ])
        db.commit()


class TestAIService:

    @patch("services.ai_service.call_llm_json")
    def test_identify_intent_simple(self, mock_llm_json):
        mock_llm_json.return_value = {"intent": "top_products", "limit": 2}

        result = _identify_intent("What are my top 2 dishes?")
        assert result["intent"] == "top_products"
        assert result["limit"] == 2
        assert result["metric"] == "revenue"
        assert result["order"] == "top"
        assert result["period"] == "all"

    @patch("services.ai_service.call_llm_json")
    def test_identify_intent_structured_parameters(self, mock_llm_json):
        mock_llm_json.return_value = {
            "intent": "bottom_products",
            "metric": "units",
            "order": "bottom",
            "period": "this_month",
            "limit": 3,
        }

        result = _identify_intent("What 3 items sold the least volume this month?")
        assert result["intent"] == "bottom_products"
        assert result["metric"] == "units"
        assert result["order"] == "bottom"
        assert result["period"] == "this_month"
        assert result["limit"] == 3

    def test_resolve_relative_period(self):
        # Anchor is 2024-02-05 (latest sales date in setup_db)
        period_str, label, start_d, end_d = _resolve_relative_period(TENANT, "this_month")
        assert period_str == "2024-02"
        assert "February 2024" in label
        assert start_d == date(2024, 2, 1)
        assert end_d == date(2024, 2, 29)

        period_str_last, label_last, start_d_last, end_d_last = _resolve_relative_period(TENANT, "last_month")
        assert period_str_last == "2024-01"
        assert "January 2024" in label_last
        assert start_d_last == date(2024, 1, 1)
        assert end_d_last == date(2024, 1, 31)

        period_str_iso, label_iso, start_d_iso, end_d_iso = _resolve_relative_period(TENANT, "2024-01")
        assert period_str_iso == "2024-01"
        assert label_iso == "January 2024"
        assert start_d_iso == date(2024, 1, 1)
        assert end_d_iso == date(2024, 1, 31)

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_top_products(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "top_products", "limit": 2}
        mock_llm.return_value = "Your top products are Pizza and Pasta."

        answer = ask_question("What are my top products?", TENANT)

        assert isinstance(answer, Answer)
        assert answer.intent == "top_products"
        assert "Your top products are Pizza and Pasta." in answer.text
        assert "[Revenue · All time]" in answer.text
        assert answer.metric == "revenue"
        assert answer.period_label == "All time"
        assert "Pizza" in answer.headline

        # Verify actual data returned from DB
        assert len(answer.data) == 2
        assert answer.data.iloc[0]["product"] == "Pizza"
        assert answer.data.iloc[0]["total_revenue"] == 600.0
        assert answer.data.iloc[1]["product"] == "Pasta"
        assert answer.data.iloc[1]["total_revenue"] == 200.0

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_bottom_products(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {
            "intent": "bottom_products",
            "metric": "units",
            "order": "bottom",
            "period": "all",
            "limit": 2,
        }
        mock_llm.return_value = "Pasta sold the fewest units."

        answer = ask_question("Which items sold the lowest volume?", TENANT)

        assert answer.intent == "bottom_products"
        assert answer.metric == "units"
        assert "lowest-selling" in answer.headline
        assert answer.data is not None
        assert len(answer.data) >= 1

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_highest_revenue_month(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "highest_revenue_month"}
        mock_llm.return_value = "Your highest revenue month was January 2024 with 800 in sales."

        answer = ask_question("What was my best month?", TENANT)

        assert answer.intent == "highest_revenue_month"
        assert "January 2024" in answer.headline
        assert answer.data is not None
        assert answer.data.iloc[0]["Month"] == "January 2024"

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_biggest_expense(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "biggest_expense", "limit": 3}
        mock_llm.return_value = "Your largest single expense was Rent for 300."

        answer = ask_question("What was my biggest expense?", TENANT)

        assert answer.intent == "biggest_expense"
        assert "Rent" in answer.headline
        assert "₹300.00" in answer.headline
        assert answer.data is not None
        assert answer.data.iloc[0]["Category"] == "Rent"

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_expense_by_category(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "expense_by_category"}
        mock_llm.return_value = "Here is your expense breakdown by category."

        answer = ask_question("Break down my expenses by category", TENANT)

        assert answer.intent == "expense_by_category"
        assert answer.data is not None
        assert "Rent" in list(answer.data["Category"])

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_business_summary(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "business_summary"}
        mock_llm.return_value = "Your business is performing well."

        answer = ask_question("How is my business performing?", TENANT)

        assert answer.intent == "business_summary"
        assert "Health" in answer.headline or "Revenue" in answer.headline
        assert answer.data is not None
        assert len(answer.data) >= 1

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_net_profit(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "net_profit"}
        mock_llm.return_value = "Your net profit is 570."

        answer = ask_question("What is my profit?", TENANT)

        assert answer.intent == "net_profit"
        assert len(answer.data) == 1
        assert answer.data.iloc[0]["Total Revenue"] == 950.0  # 500+200+100+150
        assert answer.data.iloc[0]["Total Expenses"] == 380.0  # 300+80
        assert answer.data.iloc[0]["Net Profit"] == 570.0

    @patch("services.ai_service.call_llm_json")
    def test_ask_question_unknown_intent(self, mock_llm_json):
        mock_llm_json.return_value = {"intent": "unknown"}

        answer = ask_question("How is the weather?", TENANT)

        assert answer.intent == "unknown"
        assert answer.data is None
        assert "I don't know how to answer that yet" in answer.text

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_period_comparison(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "period_comparison"}
        mock_llm.return_value = "Here is your month-over-month comparison."

        answer = ask_question("Compare this month with last month", TENANT)

        assert answer.intent == "period_comparison"
        assert "Here is your month-over-month comparison." in answer.text
        assert answer.data is not None

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_anomaly_detection(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "anomaly_detection"}
        mock_llm.return_value = "No anomalies detected in your store."

        answer = ask_question("Are there any anomalies?", TENANT)

        assert answer.intent == "anomaly_detection"
        assert "No anomalies detected in your store." in answer.text
        assert answer.data is not None

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_profit_diagnosis(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "profit_diagnosis"}
        mock_llm.return_value = "Profit changed due to stable margins."

        answer = ask_question("Why did my profit drop?", TENANT)

        assert answer.intent == "profit_diagnosis"
        assert "Profit changed due to stable margins." in answer.text
        assert answer.data is not None

    @patch("services.ai_service.call_llm_json")
    def test_ask_question_ollama_offline_returns_distinct_state(self, mock_llm_json):
        mock_llm_json.side_effect = LLMError("Could not reach the AI model")

        answer = ask_question("What are my top products?", TENANT)

        assert answer.intent == "ai_unavailable"
        assert answer.data is None
        assert "The AI is not available right now" in answer.text
        assert "I don't know how to answer that yet" not in answer.text

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_llm_offline_during_explanation(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "net_profit"}
        mock_llm.side_effect = LLMError("Connection lost")

        answer = ask_question("What is my profit?", TENANT)

        assert answer.intent == "net_profit"
        assert answer.data is not None
        assert "temporarily unavailable" in answer.text
        assert answer.headline != ""

    def test_verify_llm_numbers_catches_hallucination(self):
        df = pd.DataFrame([{"Product": "Pizza", "Revenue": 500.0, "Units": 10}])
        code_headline = "For All time, Pizza was top with ₹500.00."

        # Case 1: Valid numbers that exist in the dataframe
        truthful_text = "You earned 500 on Pizza across 10 units."
        verified = _verify_llm_numbers(truthful_text, df, code_headline)
        assert verified == truthful_text

        # Case 2: Hallucinated number (999999) not in the dataframe
        hallucinated_text = "You made 999999 in total profit!"
        guarded = _verify_llm_numbers(hallucinated_text, df, code_headline)
        # Should reject hallucination and fall back to verified code headline
        assert guarded == code_headline
