"""Integration tests for RCA Service FastAPI Endpoints."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.main import app, incidents_cache
from src.models import IncidentDetail


@pytest.fixture
def client():
    with TestClient(app) as c:
        # Seed test incident into cache
        inc = IncidentDetail(
            incident_id="INC-1001",
            title="Cascading failure test on redis-cart",
            severity="critical",
            status="OPEN",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            impacted_entities=["redis-cart", "cartservice", "frontend"],
            metadata={"root_candidate": "redis-cart"},
        )
        incidents_cache["INC-1001"] = inc
        yield c


def test_root_and_health(client):
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["service"] == "rca-service"

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"


def test_get_root_causes(client):
    res = client.get("/api/v1/root-causes/INC-1001")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "INC-1001"
    assert len(data["root_causes"]) >= 1
    assert data["top_root_cause"] == "redis-cart"
    assert data["confidence"] > 0.5


def test_get_blast_radius(client):
    # Call root-causes first to populate root
    client.get("/api/v1/root-causes/INC-1001")
    res = client.get("/api/v1/root-causes/INC-1001/blast-radius")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "INC-1001"
    assert "cartservice" in data["blast_radius"]["direct_impact"]


def test_get_evidence(client):
    res = client.get("/api/v1/incidents/INC-1001/evidence")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "INC-1001"
    assert data["total_evidence"] >= 1


def test_get_timeline(client):
    res = client.get("/api/v1/incidents/INC-1001/timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["total_events"] >= 1


def test_lifecycle_transitions_api(client):
    # 1. Acknowledge
    res_ack = client.post(
        "/api/v1/incidents/INC-1001/acknowledge",
        json={"actor": "devops-engineer", "comment": "Incident acknowledged"},
    )
    assert res_ack.status_code == 200
    assert res_ack.json()["new_state"] == "ACKNOWLEDGED"

    # 2. Investigate
    res_inv = client.post(
        "/api/v1/incidents/INC-1001/investigate",
        json={"actor": "sre", "comment": "Checking redis pod memory"},
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["new_state"] == "INVESTIGATING"

    # 3. Add comment
    res_comment = client.post(
        "/api/v1/incidents/INC-1001/comment",
        json={"actor": "sre", "comment": "Memory spiked to 98%"},
    )
    assert res_comment.status_code == 200
    assert res_comment.json()["status"] == "comment_added"

    # 4. Resolve
    res_resolve = client.post(
        "/api/v1/incidents/INC-1001/resolve",
        json={"actor": "sre", "comment": "Redis memory cleared, latency normalized"},
    )
    assert res_resolve.status_code == 200
    assert res_resolve.json()["new_state"] == "RESOLVED"
    assert res_resolve.json()["mttr_seconds"] is not None


def test_notifications_test_api(client):
    res = client.post(
        "/api/v1/notifications/test",
        json={"channel": "slack", "test_incident_id": "INC-1001"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "test_completed"
