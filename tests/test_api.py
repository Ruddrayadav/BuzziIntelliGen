"""Integration tests for the FastAPI wrapper and cookie-based tenant isolation."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.database import get_db, init_db
from db.models import Expenses, RejectedRow, Sales, UploadLog, User


API_USERS = ("api_user_a", "api_user_b", "api_auth_user")
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


