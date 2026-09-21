"""Integration tests for FastAPI routes and Orchestrator."""

import pytest
from fastapi.testclient import TestClient

from src.api.routes import set_orchestrator
from src.config import AppConfig
from src.main import app
from src.orchestrator import CorrelationOrchestrator


@pytest.fixture(autouse=True)
def init_test_app():
    config = AppConfig()
    orch = CorrelationOrchestrator(config, pool=None)
    orch.builder.seed_default_topology()
    set_orchestrator(orch)
    yield


def test_root_and_health():
    client = TestClient(app)
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["service"] == "correlation-engine"

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"


def test_topology_endpoints():
    client = TestClient(app)
    res = client.get("/api/v1/topology/services")
    assert res.status_code == 200
    data = res.json()
    assert data["total_nodes"] > 0
    assert data["total_edges"] > 0

    # Downstream of frontend
    res_down = client.get("/api/v1/topology/services/frontend/downstream")
    assert res_down.status_code == 200
    assert "cartservice" in res_down.json()["dependencies"]

    # Upstream of redis-cart
    res_up = client.get("/api/v1/topology/services/redis-cart/upstream")
    assert res_up.status_code == 200
    assert "cartservice" in res_up.json()["dependencies"]


def test_deployment_webhook_and_list():
    client = TestClient(app)
    payload = {
        "entity_id": "paymentservice",
        "event_type": "deployment_rollout",
        "details": {"new_version": "v2.2.0"},
    }
    res = client.post("/api/v1/deployments", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "recorded"

    res_list = client.get("/api/v1/deployments?within_minutes=60")
    assert res_list.status_code == 200
    deps = res_list.json()["deployments"]
    assert any(d["entity_id"] == "paymentservice" for d in deps)
