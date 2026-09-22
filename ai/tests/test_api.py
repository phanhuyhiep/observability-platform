"""Integration tests for AI Enhancement Service FastAPI REST API."""

import pytest
from fastapi.testclient import TestClient

from ai.src.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["phase"] == 5


def test_ml_detect_normal_telemetry(client):
    payload = {
        "entity_id": "cartservice",
        "metrics": {
            "cpu_usage": 0.18,
            "memory_usage": 0.32,
            "p95_latency_ms": 48.0,
            "error_rate": 0.0,
            "request_throughput": 120.0,
            "dependency_latency_ms": 22.0,
        },
    }
    res = client.post("/api/v1/ml/detect", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["entity_id"] == "cartservice"
    assert "anomaly_score" in data
    assert "feature_attributions" in data
    assert data["is_anomaly"] is False


def test_ml_detect_anomaly_telemetry(client):
    payload = {
        "entity_id": "cartservice",
        "metrics": {
            "cpu_usage": 0.95,
            "memory_usage": 0.90,
            "p95_latency_ms": 4200.0,
            "error_rate": 0.75,
            "request_throughput": 10.0,
            "dependency_latency_ms": 3000.0,
        },
    }
    res = client.post("/api/v1/ml/detect", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["anomaly_score"] > 0.5


def test_ml_models_list_and_train(client):
    # Train
    train_payload = {"entity_id": "paymentservice", "n_estimators": 20}
    res_train = client.post("/api/v1/ml/models/train", json=train_payload)
    assert res_train.status_code == 200
    assert res_train.json()["status"] == "trained"

    # List
    res_list = client.get("/api/v1/ml/models")
    assert res_list.status_code == 200
    models = res_list.json()["models"]
    entities = [m["entity_id"] for m in models]
    assert "paymentservice" in entities


def test_forecasting_endpoint(client):
    res = client.get("/api/v1/forecast/cartservice/p95_latency_ms?horizon=30&interval=5")
    assert res.status_code == 200
    data = res.json()
    assert data["entity_id"] == "cartservice"
    assert len(data["forecast_points"]) == 6


def test_dynamic_baseline_endpoint(client):
    res = client.get("/api/v1/baselines/dynamic/cartservice/p95_latency_ms?current_value=45.0")
    assert res.status_code == 200
    data = res.json()
    assert data["expected_mean"] > 0.0
    assert data["is_anomalous"] is False


def test_incident_summary_endpoint(client):
    res = client.get("/api/v1/incidents/INC-888888/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "INC-888888"
    assert "summary_text" in data
    assert len(data["suggested_actions"]) > 0


def test_investigation_recommendations_endpoint(client):
    res = client.get("/api/v1/incidents/INC-888888/recommendations")
    assert res.status_code == 200
    data = res.json()
    assert len(data["recommendations"]) > 0
    assert len(data["runbooks"]) > 0


def test_similar_incidents_endpoint(client):
    res = client.get("/api/v1/incidents/INC-888888/similar")
    assert res.status_code == 200
    data = res.json()
    assert len(data["similar_incidents"]) > 0


def test_feedback_endpoint(client):
    feedback_payload = {
        "rating": 5,
        "helpful": True,
        "comments": "Great investigation steps, resolved issue in 2 mins!",
    }
    res = client.post("/api/v1/feedback/recommendations/INC-888888", json=feedback_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "recorded"


def test_html_rendering_endpoints(client):
    res_summary = client.get("/api/v1/incidents/INC-888888/summary", headers={"Accept": "text/html"})
    assert res_summary.status_code == 200
    assert "text/html" in res_summary.headers["content-type"]
    assert "AI Incident Copilot" in res_summary.text

    res_recs = client.get("/api/v1/incidents/INC-888888/recommendations", headers={"Accept": "text/html"})
    assert res_recs.status_code == 200
    assert "text/html" in res_recs.headers["content-type"]
    assert "AI Điều Tra Nguyên Nhân" in res_recs.text
