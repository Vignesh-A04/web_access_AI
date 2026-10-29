"""Integration tests for FastAPI REST endpoints and embedded test website."""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(test_client: TestClient):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "gemini_configured" in data
    assert "playwright_ready" in data


def test_test_site_get(test_client: TestClient):
    resp = test_client.get("/test-site")
    assert resp.status_code == 200
    assert "Authorized Demo Registration & Task Form" in resp.text
    assert "registration-form" in resp.text
    assert "inventory-table" in resp.text


def test_test_site_submit(test_client: TestClient):
    resp = test_client.post(
        "/test-site/submit",
        data={
            "name": "Alice Tester",
            "email": "alice@example.com",
            "account_type": "business",
            "message": "Automate routine data entry",
            "agree_terms": "yes",
        },
    )
    assert resp.status_code == 200
    assert "Registration Confirmed!" in resp.text
    assert "alice@example.com" in resp.text


def test_create_task_validation_error(test_client: TestClient):
    # Invalid: missing instruction
    resp = test_client.post("/api/tasks", json={"url": "https://example.com"})
    assert resp.status_code == 422


def test_create_and_get_task(test_client: TestClient):
    resp = test_client.post(
        "/api/tasks",
        json={
            "url": "https://example.com",
            "instruction": "Inspect main page and list key headings.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    task_id = data["task_id"]
    assert task_id is not None
    assert data["status"] in ["QUEUED", "RUNNING"]

    # Retrieve task
    get_resp = test_client.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["task_id"] == task_id

    # Retrieve logs
    logs_resp = test_client.get(f"/api/tasks/{task_id}/logs")
    assert logs_resp.status_code == 200
    assert isinstance(logs_resp.json(), list)


def test_get_nonexistent_task(test_client: TestClient):
    resp = test_client.get("/api/tasks/nonexistent-id-404")
    assert resp.status_code == 404
