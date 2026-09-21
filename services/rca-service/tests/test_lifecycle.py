"""Unit tests for Incident Lifecycle State Machine and Auto-Resolver."""

from datetime import datetime, timedelta, timezone
import pytest

from src.lifecycle.auto_resolver import AutoResolver
from src.lifecycle.state_machine import IncidentStateMachine
from src.models import IncidentDetail


@pytest.fixture
def sample_incident():
    now = datetime.now(timezone.utc) - timedelta(minutes=20)
    return IncidentDetail(
        incident_id="INC-1001",
        title="High latency on redis-cart cascading to cartservice",
        severity="critical",
        status="OPEN",
        created_at=now,
        updated_at=now,
        impacted_entities=["redis-cart", "cartservice", "frontend"],
        metadata={"anomaly_ids": ["anom-1", "anom-2"]},
    )


def test_valid_lifecycle_transitions(sample_incident):
    sm = IncidentStateMachine()

    # OPEN -> ACKNOWLEDGED
    inc, ev = sm.transition(sample_incident, "ACKNOWLEDGED", actor="alice", comment="Looking into this")
    assert inc.status == "ACKNOWLEDGED"
    assert inc.acknowledged_at is not None
    assert inc.mttd_seconds is not None
    assert ev.event_type == "state_change"

    # ACKNOWLEDGED -> INVESTIGATING
    inc, ev = sm.transition(inc, "INVESTIGATING", actor="bob")
    assert inc.status == "INVESTIGATING"
    assert inc.investigating_at is not None

    # INVESTIGATING -> MITIGATED
    inc, ev = sm.transition(inc, "MITIGATED", actor="charlie", comment="Restarted redis-cart pod")
    assert inc.status == "MITIGATED"
    assert inc.mitigated_at is not None

    # MITIGATED -> RESOLVED
    inc, ev = sm.transition(inc, "RESOLVED", actor="charlie", comment="Latency normal")
    assert inc.status == "RESOLVED"
    assert inc.resolved_at is not None
    assert inc.mttr_seconds is not None
    assert inc.mttr_seconds > 0

    # RESOLVED -> CLOSED
    inc, ev = sm.transition(inc, "CLOSED", actor="system")
    assert inc.status == "CLOSED"
    assert inc.closed_at is not None


def test_invalid_lifecycle_transition(sample_incident):
    sm = IncidentStateMachine()
    
    # First move to INVESTIGATING
    sm.transition(sample_incident, "INVESTIGATING", actor="alice")

    # INVESTIGATING cannot jump backwards to OPEN
    with pytest.raises(ValueError) as exc:
        sm.transition(sample_incident, "OPEN", actor="alice")
    assert "Invalid status transition" in str(exc.value)


def test_idempotent_transition(sample_incident):
    sm = IncidentStateMachine()
    # Transitioning to the current state should be idempotent
    inc, ev = sm.transition(sample_incident, "OPEN", actor="alice")
    assert inc.status == "OPEN"
    assert ev.title == "Incident remained in OPEN"


def test_auto_resolver(sample_incident):
    sm = IncidentStateMachine()
    resolver = AutoResolver(state_machine=sm, auto_resolve_minutes=15)

    # Active anomalies still exist -> do not resolve
    active_anomalies = {"anom-1"}
    res = resolver.check_and_resolve(sample_incident, active_anomalies)
    assert res is None
    assert sample_incident.status == "OPEN"

    # No active anomalies left, and updated_at was 20 mins ago (> 15 min threshold) -> should resolve
    empty_active = set()
    res = resolver.check_and_resolve(sample_incident, empty_active)
    assert res is not None
    resolved_inc, ev = res
    assert resolved_inc.status == "RESOLVED"
    assert resolved_inc.resolved_at is not None
    assert ev.actor == "auto-resolver"
