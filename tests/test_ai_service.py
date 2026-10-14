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
from services.ai_service import ask_question, Answer, _identify_intent

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
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), product="Pizza", revenue=500),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), product="Pasta", revenue=200),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 3), product="Pizza", revenue=100),
        ])
        
        db.add_all([
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), category="Rent", amount=300),
        ])
        db.commit()


class TestAIService:
    
    @patch("services.ai_service.call_llm_json")
    def test_identify_intent(self, mock_llm_json):
        mock_llm_json.return_value = {"intent": "top_products", "limit": 2}
        
        result = _identify_intent("What are my top 2 dishes?")
        assert result["intent"] == "top_products"
        assert result["limit"] == 2

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_top_products(self, mock_llm_json, mock_llm):
        # 1. Mock intent
        mock_llm_json.return_value = {"intent": "top_products", "limit": 2}
        # 2. Mock explanation
        mock_llm.return_value = "Your top products are Pizza and Pasta."
        
        answer = ask_question("What are my top products?", TENANT)
        
        assert isinstance(answer, Answer)
        assert answer.intent == "top_products"
        assert answer.text == "Your top products are Pizza and Pasta."
        
        # Verify the actual data returned from DB
        assert len(answer.data) == 2
        assert answer.data.iloc[0]["product"] == "Pizza"
        assert answer.data.iloc[0]["total_revenue"] == 600.0  # 500 + 100
        assert answer.data.iloc[1]["product"] == "Pasta"
        assert answer.data.iloc[1]["total_revenue"] == 200.0

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_net_profit(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "net_profit"}
        mock_llm.return_value = "Your net profit is 500."
        
        answer = ask_question("What is my profit?", TENANT)
        
        assert answer.intent == "net_profit"
        assert len(answer.data) == 1
        assert answer.data.iloc[0]["Total Revenue"] == 800.0
        assert answer.data.iloc[0]["Total Expenses"] == 300.0
        assert answer.data.iloc[0]["Net Profit"] == 500.0

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
        assert answer.text == "Here is your month-over-month comparison."
        assert answer.data is not None

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_anomaly_detection(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "anomaly_detection"}
        mock_llm.return_value = "No anomalies detected in your store."

        answer = ask_question("Are there any anomalies?", TENANT)

        assert answer.intent == "anomaly_detection"
        assert answer.text == "No anomalies detected in your store."
        assert answer.data is not None

    @patch("services.ai_service.call_llm")
    @patch("services.ai_service.call_llm_json")
    def test_ask_question_profit_diagnosis(self, mock_llm_json, mock_llm):
        mock_llm_json.return_value = {"intent": "profit_diagnosis"}
        mock_llm.return_value = "Profit changed due to stable margins."

        answer = ask_question("Why did my profit drop?", TENANT)

        assert answer.intent == "profit_diagnosis"
        assert answer.text == "Profit changed due to stable margins."
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

