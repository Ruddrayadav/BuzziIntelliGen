"""Integration tests for the FastAPI wrapper and cookie-based tenant isolation."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.database import get_db, init_db
from db.models import Expenses, RejectedRow, Sales, UploadLog, User
from llm.llm import LLMError


API_USERS = (
    "api_user_a",
    "api_user_b",
    "api_auth_user",
    "api_cb_user",
    "api_dupe_user",
    "api_analytics_user",
    "api_ask_user",
    "api_rate_user",
)
SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


@pytest.fixture(autouse=True)
def clean_api_data(monkeypatch):
    """Keep API test accounts and their tenant rows separate from every other test."""
    monkeypatch.setenv("BIZINTEL_SESSION_SECRET", "api-test-session-secret")
    init_db()
    with get_db() as db:
        for username in API_USERS:
            db.query(RejectedRow).filter(RejectedRow.tenant_id == username).delete()
            db.query(Sales).filter(Sales.tenant_id == username).delete()
            db.query(Expenses).filter(Expenses.tenant_id == username).delete()
            db.query(UploadLog).filter(UploadLog.tenant_id == username).delete()
            db.query(User).filter(User.username == username).delete()
        db.commit()
    yield
    with get_db() as db:
        for username in API_USERS:
            db.query(RejectedRow).filter(RejectedRow.tenant_id == username).delete()
            db.query(Sales).filter(Sales.tenant_id == username).delete()
            db.query(Expenses).filter(Expenses.tenant_id == username).delete()
            db.query(UploadLog).filter(UploadLog.tenant_id == username).delete()
            db.query(User).filter(User.username == username).delete()
        db.commit()


def _register(client: TestClient, username: str, business_name: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "safe-test-password", "business_name": business_name},
    )
    assert response.status_code == 201, response.text


def _sample_sales_file() -> bytes:
    """Use the existing complete sales schema so we test the API, not new data rules."""
    return (SAMPLES_DIR / "sample_sales.csv").read_bytes()


def test_auth_session_never_returns_password_data():
    with TestClient(app) as client:
        _register(client, "api_auth_user", "Auth Shop")
        body = client.get("/api/auth/me").json()

        assert body == {"username": "api_auth_user", "business_name": "Auth Shop"}
        assert "password" not in str(body).lower()

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert client.get("/api/auth/me").json() == {"message": "Please log in to continue."}


def test_upload_preview_and_commit_return_safe_data():
    sales_file = _sample_sales_file()
    with TestClient(app) as client:
        _register(client, "api_user_a", "A Cafe")

        preview = client.post("/api/upload/preview", files={"file": ("sales.csv", sales_file, "text/csv")})
        assert preview.status_code == 200, preview.text
        preview_body = preview.json()
        assert preview_body["detected_type"] == "sales"
        assert preview_body["missing_required"] == []
        assert preview_body["sample_rows"]

        commit = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={
                "file_type": "sales",
                "mapping": json.dumps(preview_body["suggested_mapping"]),
            },
        )
        assert commit.status_code == 200, commit.text
        body = commit.json()
        assert body["success"] is True
        assert body["rows_read"] == 60
        assert body["rows_saved"] > 0


def test_user_a_data_is_not_readable_by_user_b_even_with_tenant_query_parameter():
    sales_file = _sample_sales_file()
    with TestClient(app) as client_a, TestClient(app) as client_b:
        _register(client_a, "api_user_a", "A Cafe")
        _register(client_b, "api_user_b", "B Cafe")

        commit = client_a.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={
                "file_type": "sales",
                "mapping": json.dumps({
                    "order_id": "order_id",
                    "date": "date",
                    "item_name": "product",
                    "category": "category",
                    "qty": "quantity",
                    "unit_price": "unit_price",
                    "total": "revenue",
                }),
            },
        )
        assert commit.status_code == 200, commit.text

        owner_a_dashboard = client_a.get("/api/dashboard")
        intruder_dashboard = client_b.get("/api/dashboard?tenant_id=api_user_a")

        assert owner_a_dashboard.status_code == 200
        assert owner_a_dashboard.json()["total_revenue"] > 0
        assert intruder_dashboard.status_code == 200
        assert intruder_dashboard.json()["total_revenue"] == 0.0


def test_dashboard_trend_endpoint():
    sales_file = _sample_sales_file()
    with TestClient(app) as client:
        _register(client, "api_auth_user", "Trend Cafe")
        client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={
                "file_type": "sales",
                "mapping": json.dumps({
                    "order_id": "order_id",
                    "date": "date",
                    "item_name": "product",
                    "category": "category",
                    "qty": "quantity",
                    "unit_price": "unit_price",
                    "total": "revenue",
                }),
            },
        )

        # 1. Weekly trend request
        weekly_res = client.get("/api/dashboard/trend?granularity=weekly")
        assert weekly_res.status_code == 200
        data = weekly_res.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "label" in data[0]
        assert "W" in data[0]["label"]
        assert "revenue" in data[0]

        # 2. Invalid granularity
        invalid_res = client.get("/api/dashboard/trend?granularity=hourly")
        assert invalid_res.status_code == 422


def test_upload_content_length_limit():
    sales_file = _sample_sales_file()
    with TestClient(app) as client:
        _register(client, "api_limit_user", "Limit Cafe")
        # Oversized Content-Length header should trigger immediate 413
        oversized_headers = {"content-length": str(15 * 1024 * 1024)}
        res = client.post(
            "/api/upload/preview",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            headers=oversized_headers,
        )
        assert res.status_code == 413
        assert "too large" in res.json()["message"].lower()


def test_upload_commit_mapping_validation():
    sales_file = _sample_sales_file()
    with TestClient(app) as client:
        _register(client, "api_valid_user", "Validation Cafe")

        # 1. Duplicate target mapping
        dup_mapping = {
            "order_id": "order_id",
            "date": "date",
            "item_name": "product",
            "category": "revenue",  # duplicate target
            "total": "revenue",     # duplicate target
        }
        res_dup = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(dup_mapping)},
        )
        assert res_dup.status_code == 400
        assert "Multiple columns were mapped to the same field" in res_dup.json()["message"]

        # 2. Missing required target (missing revenue)
        missing_mapping = {
            "order_id": "order_id",
            "date": "date",
            "item_name": "product",
        }
        res_missing = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(missing_mapping)},
        )
        assert res_missing.status_code == 400
        assert "Missing required field(s)" in res_missing.json()["message"]


def test_upload_duplicate_detection_and_replace():
    sales_file = _sample_sales_file()
    valid_mapping = {
        "order_id": "order_id",
        "date": "date",
        "item_name": "product",
        "category": "category",
        "qty": "quantity",
        "unit_price": "unit_price",
        "total": "revenue",
    }
    with TestClient(app) as client:
        _register(client, "api_dupe_user", "Dupe Cafe")

        # 1. First upload succeeds
        res1 = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(valid_mapping)},
        )
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # 2. Duplicate upload without replace returns 409 Conflict
        res2 = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(valid_mapping)},
        )
        assert res2.status_code == 409
        assert "already been imported" in res2.json()["message"]

        # 3. Duplicate upload with replace=True succeeds with 200
        res3 = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={
                "file_type": "sales",
                "mapping": json.dumps(valid_mapping),
                "replace": "true",
            },
        )
        assert res3.status_code == 200
        assert res3.json()["success"] is True


def test_upload_cashbook_preview_and_commit():
    cashbook_csv = (
        "Date,Particulars,Debit,Credit\n"
        "2024-01-01,Counter sale Jan 1,0,15000\n"
        "2024-01-01,Shop rent,25000,0\n"
        "2024-01-02,Tea and snacks,0,1200\n"
        "2024-01-02,Electricity bill,3200,0\n"
    ).encode("utf-8")

    with TestClient(app) as client:
        _register(client, "api_cb_user", "Cashbook Cafe")

        # 1. Preview detects cashbook
        prev = client.post(
            "/api/upload/preview",
            files={"file": ("cashbook.csv", cashbook_csv, "text/csv")},
        )
        assert prev.status_code == 200
        prev_data = prev.json()
        assert prev_data["detected_type"] == "cashbook"
        assert prev_data["is_cashbook"] is True
        assert prev_data["cashbook_summary"]["sales_count"] == 2
        assert prev_data["cashbook_summary"]["expenses_count"] == 2
        assert prev_data["cashbook_summary"]["sales_total"] == 16200.0
        assert prev_data["cashbook_summary"]["expenses_total"] == 28200.0

        # 2. Commit imports both sales and expenses
        commit = client.post(
            "/api/upload/commit",
            files={"file": ("cashbook.csv", cashbook_csv, "text/csv")},
            data={"file_type": "cashbook"},
        )
        assert commit.status_code == 200
        commit_data = commit.json()
        assert commit_data["success"] is True
        assert commit_data["is_cashbook"] is True
        assert commit_data["rows_saved"] == 4
        assert "Split into 2 sales" in commit_data["cashbook_summary"]

        # 3. Verify Dashboard shows both sides
        dash = client.get("/api/dashboard")
        assert dash.status_code == 200
        dash_data = dash.json()
        assert dash_data["total_revenue"] == 16200.0
        assert dash_data["total_expenses"] == 28200.0
        assert dash_data["net_profit"] == -12000.0


def test_analytics_month_validation_422():
    with TestClient(app) as client:
        _register(client, "api_analytics_user", "Analytics Cafe")

        # 1. Invalid regex on compare current_month
        res1 = client.get("/api/analytics/compare?current_month=invalid")
        assert res1.status_code == 422

        # 2. Out-of-bounds month (month 13)
        res2 = client.get("/api/analytics/compare?current_month=2024-13")
        assert res2.status_code == 422

        # 3. Non-padded month
        res3 = client.get("/api/analytics/compare?prior_month=2024-5")
        assert res3.status_code == 422

        # 4. Invalid on diagnosis
        res4 = client.get("/api/analytics/diagnosis?current_month=2024-99")
        assert res4.status_code == 422


def test_analytics_compare_incomplete_month_400():
    sales_file = _sample_sales_file()
    valid_mapping = {
        "order_id": "order_id",
        "date": "date",
        "item_name": "product",
        "category": "category",
        "qty": "quantity",
        "unit_price": "unit_price",
        "total": "revenue",
    }
    with TestClient(app) as client:
        _register(client, "api_analytics_user", "Analytics Cafe")

        # Upload sales data only (no expenses)
        res = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(valid_mapping)},
        )
        assert res.status_code == 200

        # Attempt compare
        compare_res = client.get("/api/analytics/compare")
        assert compare_res.status_code == 400
        message = compare_res.json()["message"]
        assert "only has sales" in message or "Comparison requires both sales and expenses" in message


def test_ask_ai_endpoint_success_and_offline_503():
    with TestClient(app) as client:
        _register(client, "api_ask_user", "AI Ask Cafe")

        # 1. Ollama online: returns 200 with answer
        with patch("services.ai_service.call_llm_json") as mock_json, \
             patch("services.ai_service.call_llm") as mock_text:
            mock_json.return_value = {"intent": "net_profit"}
            mock_text.return_value = "Your net profit is 0."

            res = client.post("/api/ask", json={"question": "What is my profit?"})
            assert res.status_code == 200
            data = res.json()
            assert data["intent"] == "net_profit"
            assert "Your net profit is 0." in data["text"]
            assert data["metric"] == "revenue"
            assert data["period"] == "all"
            assert data["period_label"] == "All time"
            assert "headline" in data and isinstance(data["headline"], str)

        # 2. Ollama offline: returns 503 Service Unavailable with friendly message
        with patch("services.ai_service.call_llm_json") as mock_json:
            mock_json.side_effect = LLMError("Could not reach Ollama")

            res_offline = client.post("/api/ask", json={"question": "What is my profit?"})
            assert res_offline.status_code == 503
            assert "The AI is not available right now" in res_offline.json()["message"]


def test_registration_rejects_password_under_8_characters():
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/register",
            json={"username": "short_pwd_user", "password": "123", "business_name": "Short Cafe"},
        )
        assert res.status_code == 422


def test_login_rate_limiting_returns_429():
    from api.routes.auth import reset_rate_limits
    reset_rate_limits()
    try:
        with TestClient(app) as client:
            _register(client, "api_rate_user", "Rate Cafe")

            # 5 failed attempts
            for i in range(5):
                res = client.post(
                    "/api/auth/login",
                    json={"username": "api_rate_user", "password": "wrong-password"},
                )
                assert res.status_code == 401, f"Attempt {i+1} should return 401"

            # 6th failed attempt within 10 minutes returns 429
            res6 = client.post(
                "/api/auth/login",
                json={"username": "api_rate_user", "password": "wrong-password"},
            )
            assert res6.status_code == 429
            assert "Too many failed login attempts" in res6.json()["message"]
    finally:
        reset_rate_limits()


def test_startup_refuses_insecure_placeholder_secret(monkeypatch):
    from api.deps import validate_session_secret
    
    # Missing secret
    monkeypatch.delenv("BIZINTEL_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        validate_session_secret()
    assert "missing or still set to the insecure placeholder" in str(exc_info.value)

    # Insecure placeholder secret
    monkeypatch.setenv("BIZINTEL_SESSION_SECRET", "replace-with-a-long-random-secret")
    with pytest.raises(RuntimeError) as exc_info2:
        validate_session_secret()
    assert "missing or still set to the insecure placeholder" in str(exc_info2.value)


def test_cookie_secure_flag_follows_env(monkeypatch):
    from api.deps import is_cookie_secure

    monkeypatch.setenv("BIZINTEL_COOKIE_SECURE", "false")
    assert is_cookie_secure() is False

    monkeypatch.setenv("BIZINTEL_COOKIE_SECURE", "true")
    assert is_cookie_secure() is True


def test_dashboard_endpoint_supports_date_filters_and_new_fields():
    sales_file = _sample_sales_file()
    with TestClient(app) as client:
        _register(client, "api_user_a", "A Cafe")
        
        # Preview to get valid mapping
        preview = client.post("/api/upload/preview", files={"file": ("sales.csv", sales_file, "text/csv")})
        assert preview.status_code == 200
        mapping = preview.json()["suggested_mapping"]

        # Commit sales
        res = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(mapping)},
        )
        assert res.status_code == 200

        # Query full dashboard
        dash_res = client.get("/api/dashboard")
        assert dash_res.status_code == 200
        data = dash_res.json()
        assert "category_performance" in data
        assert "total_transactions" in data
        assert "total_units_sold" in data
        assert "takeaways" in data
        assert "attention_items" in data
        assert "day_of_week_insight" in data
        assert "slow_movers" in data
        assert "target_pacing" in data
        assert isinstance(data["attention_items"], list)
        assert data["total_transactions"] > 0
        assert data["total_units_sold"] > 0

        # Query attention endpoint
        att_res = client.get("/api/dashboard/attention")
        assert att_res.status_code == 200
        att_data = att_res.json()
        assert isinstance(att_data, list)
        assert len(att_data) > 0

        # Query day-of-week endpoint
        dow_res = client.get("/api/dashboard/day-of-week")
        assert dow_res.status_code == 200
        dow_data = dow_res.json()
        assert "days" in dow_data
        assert "headline" in dow_data

        # Query slow-movers endpoint
        sm_res = client.get("/api/dashboard/slow-movers?limit=5")
        assert sm_res.status_code == 200
        sm_data = sm_res.json()
        assert isinstance(sm_data, list)
        assert len(sm_data) <= 5

        # Query target endpoints (Set, Get, Delete)
        set_target_res = client.post(
            "/api/dashboard/target",
            json={"month": "2024-01", "target_amount": 50000.0},
        )
        assert set_target_res.status_code == 200
        target_body = set_target_res.json()
        assert target_body["has_target"] is True
        assert target_body["target_amount"] == 50000.0

        get_target_res = client.get("/api/dashboard/target?month=2024-01")
        assert get_target_res.status_code == 200
        assert get_target_res.json()["target_amount"] == 50000.0

        # Invalid target rejected
        bad_target = client.post("/api/dashboard/target", json={"month": "2024-01", "target_amount": -10.0})
        assert bad_target.status_code == 422

        # Delete target
        del_target = client.delete("/api/dashboard/target?month=2024-01")
        assert del_target.status_code == 200
        assert del_target.json()["deleted"] is True

        # Query with date filter
        filtered_res = client.get("/api/dashboard?start_date=2024-01-01&end_date=2024-01-02")
        assert filtered_res.status_code == 200
        filtered_data = filtered_res.json()
        assert "total_revenue" in filtered_data

        # Query trend with both revenue and expenses
        trend_res = client.get("/api/dashboard/trend?granularity=weekly")
        assert trend_res.status_code == 200
        trend_data = trend_res.json()
        assert len(trend_data) > 0
        assert "revenue" in trend_data[0]
        assert "expenses" in trend_data[0]


def test_upload_history_audit_and_undo_endpoints():
    sales_file = _sample_sales_file()
    valid_mapping = {
        "order_id": "order_id",
        "date": "date",
        "item_name": "product",
        "category": "category",
        "qty": "quantity",
        "unit_price": "unit_price",
        "total": "revenue",
    }

    # 1. Unauthenticated requests are rejected (401)
    with TestClient(app) as unauth_client:
        assert unauth_client.get("/api/upload/history").status_code == 401
        assert unauth_client.get("/api/upload/history/1/skipped").status_code == 401
        assert unauth_client.delete("/api/upload/history/1").status_code == 401

    # 2. User A uploads a file
    with TestClient(app) as client_a:
        _register(client_a, "api_hist_a", "History Cafe A")

        # Initially empty history
        init_history = client_a.get("/api/upload/history")
        assert init_history.status_code == 200
        assert init_history.json() == []

        # Upload file
        res = client_a.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(valid_mapping)},
        )
        assert res.status_code == 200
        upload_id = res.json()["upload_log_id"]
        assert upload_id is not None

        # Verify history has 1 record
        hist_res = client_a.get("/api/upload/history")
        assert hist_res.status_code == 200
        history_list = hist_res.json()
        assert len(history_list) == 1
        assert history_list[0]["id"] == upload_id
        assert history_list[0]["filename"] == "sales.csv"
        assert history_list[0]["file_type"] == "sales"
        assert history_list[0]["rows_saved"] > 0

        # Verify skipped rows endpoint
        skipped_res = client_a.get(f"/api/upload/history/{upload_id}/skipped")
        assert skipped_res.status_code == 200
        assert isinstance(skipped_res.json(), list)

        # 3. User B cannot see or delete User A's upload (Strict Tenant Isolation)
        with TestClient(app) as client_b:
            _register(client_b, "api_hist_b", "History Cafe B")

            # User B history is empty
            b_hist = client_b.get("/api/upload/history")
            assert b_hist.status_code == 200
            assert b_hist.json() == []

            # User B cannot view User A's skipped rows -> 404
            b_skipped = client_b.get(f"/api/upload/history/{upload_id}/skipped")
            assert b_skipped.status_code == 404

            # User B cannot delete User A's upload -> 404
            b_delete = client_b.delete(f"/api/upload/history/{upload_id}")
            assert b_delete.status_code == 404

        # 4. User A performs rollback
        del_res = client_a.delete(f"/api/upload/history/{upload_id}")
        assert del_res.status_code == 200
        del_data = del_res.json()
        assert del_data["success"] is True
        assert del_data["deleted_upload_id"] == upload_id

        # History is now empty for User A
        empty_hist = client_a.get("/api/upload/history")
        assert empty_hist.status_code == 200
        assert empty_hist.json() == []

        # Second delete of same upload returns 404
        del_again = client_a.delete(f"/api/upload/history/{upload_id}")
        assert del_again.status_code == 404


def test_monthly_pdf_report_api_endpoint():
    # 1. Unauthenticated request returns 401
    with TestClient(app) as unauth_client:
        res = unauth_client.get("/api/reports/monthly-pdf")
        assert res.status_code == 401

    # 2. Authenticated user with no data gets 400
    with TestClient(app) as client:
        _register(client, "api_pdf_user", "PDF Cafe")

        # Invalid month format returns 422
        bad_month = client.get("/api/reports/monthly-pdf?month=2024-99")
        assert bad_month.status_code == 422

        # Valid month but no transactions for that month returns 400
        no_data_month = client.get("/api/reports/monthly-pdf?month=2024-01")
        assert no_data_month.status_code == 400
        assert "no financial transactions recorded" in no_data_month.json()["message"].lower()

        # Omitted month with no records at all returns 400
        no_data_user = client.get("/api/reports/monthly-pdf")
        assert no_data_user.status_code == 400
        assert "no sales or expense records found" in no_data_user.json()["message"].lower()


        # 3. Upload sample sales
        sales_file = _sample_sales_file()
        valid_mapping = {
            "order_id": "order_id",
            "date": "date",
            "item_name": "product",
            "category": "category",
            "qty": "quantity",
            "unit_price": "unit_price",
            "total": "revenue",
        }
        upload_res = client.post(
            "/api/upload/commit",
            files={"file": ("sales.csv", sales_file, "text/csv")},
            data={"file_type": "sales", "mapping": json.dumps(valid_mapping)},
        )
        assert upload_res.status_code == 200

        # 4. Generate report with explicit month
        pdf_res = client.get("/api/reports/monthly-pdf?month=2024-01")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert "bizintel-executive-report-2024-01.pdf" in pdf_res.headers["content-disposition"]
        assert pdf_res.content.startswith(b"%PDF-")
        assert b"%%EOF" in pdf_res.content

        # 5. Generate report without month (auto-resolves latest month in data)
        pdf_latest = client.get("/api/reports/monthly-pdf")
        assert pdf_latest.status_code == 200
        assert pdf_latest.headers["content-type"] == "application/pdf"
        assert pdf_latest.content.startswith(b"%PDF-")









