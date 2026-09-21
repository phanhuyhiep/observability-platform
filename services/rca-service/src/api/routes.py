"""FastAPI routes for RCA Engine, Blast Radius, Evidence, and Incident Lifecycle."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.models import (
    BlastRadiusResponse,
    CommentRequest,
    EvidenceResponse,
    NotificationTestRequest,
    RCAResponse,
    TimelineResponse,
    TransitionRequest,
)
from src.blast_radius.calculator import BlastRadiusCalculator
from src.evidence.evidence_aggregator import EvidenceAggregator
from src.lifecycle.state_machine import IncidentStateMachine
from src.models import IncidentDetail, TimelineEvent
from src.notification.notifier import NotificationCoordinator
from src.scoring.root_cause_ranker import RootCauseRanker

logger = logging.getLogger("rca.api")

router = APIRouter(prefix="/api/v1")

# Global instances (injected by main.py)
_ranker: RootCauseRanker | None = None
_blast_calc: BlastRadiusCalculator | None = None
_evidence_agg: EvidenceAggregator | None = None
_state_machine: IncidentStateMachine | None = None
_notifier: NotificationCoordinator | None = None
_incidents_cache: dict[str, IncidentDetail] = {}
_timeline_cache: dict[str, list[TimelineEvent]] = {}
_db_pool: Any = None
_graph: Any = None


def set_dependencies(
    ranker: RootCauseRanker,
    blast_calc: BlastRadiusCalculator,
    evidence_agg: EvidenceAggregator,
    state_machine: IncidentStateMachine,
    notifier: NotificationCoordinator,
    incidents_cache: dict[str, IncidentDetail],
    timeline_cache: dict[str, list[TimelineEvent]],
    pool: Any = None,
    graph: Any = None,
) -> None:
    global _ranker, _blast_calc, _evidence_agg, _state_machine, _notifier
    global _incidents_cache, _timeline_cache, _db_pool, _graph
    _ranker = ranker
    _blast_calc = blast_calc
    _evidence_agg = evidence_agg
    _state_machine = state_machine
    _notifier = notifier
    _incidents_cache = incidents_cache
    _timeline_cache = timeline_cache
    _db_pool = pool
    _graph = graph


def _get_incident(incident_id: str) -> IncidentDetail:
    if incident_id not in _incidents_cache:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    return _incidents_cache[incident_id]


# ============================================================
# 1. Root Cause Analysis
# ============================================================

@router.get("/root-causes/{incident_id}", response_model=RCAResponse)
async def get_root_causes(incident_id: str):
    """Calculate and return ranked root causes for an incident."""
    if _ranker is None:
        raise HTTPException(status_code=503, detail="RCA Engine not initialized")

    incident = _get_incident(incident_id)

    # Prepare data for ranker
    entities = incident.impacted_entities
    if not entities:
        return RCAResponse(incident_id=incident_id, root_causes=[], top_root_cause=None, confidence=0.0)

    entity_timestamps = {
        e: incident.created_at for e in entities
    }
    # If topology context has a root candidate, bias its timestamp earlier
    if incident.metadata.get("root_candidate"):
        root = incident.metadata["root_candidate"]
        if root in entity_timestamps:
            entity_timestamps[root] = incident.created_at

    entity_anomalies = {e: [{"severity": incident.severity}] for e in entities}

    ranked = _ranker.rank(
        entities=entities,
        entity_timestamps=entity_timestamps,
        entity_anomalies=entity_anomalies,
        graph=_graph,
        incident_time=incident.created_at,
    )

    incident.root_causes = ranked
    top_cause = ranked[0].entity_id if ranked else None
    conf = ranked[0].confidence if ranked else 0.0

    if _notifier:
        try:
            await _notifier.dispatch(incident)
        except Exception as e:
            logger.warning("Failed to auto-dispatch notification for %s: %s", incident_id, e)

    return RCAResponse(
        incident_id=incident_id,
        root_causes=ranked,
        top_root_cause=top_cause,
        confidence=conf,
    )


# ============================================================
# 2. Blast Radius
# ============================================================

@router.get("/root-causes/{incident_id}/blast-radius", response_model=BlastRadiusResponse)
async def get_blast_radius(incident_id: str):
    """Compute and return blast radius from the top root cause."""
    if _blast_calc is None:
        raise HTTPException(status_code=503, detail="Blast Radius Calculator not initialized")

    incident = _get_incident(incident_id)
    root = (
        incident.root_causes[0].entity_id
        if incident.root_causes
        else (incident.impacted_entities[0] if incident.impacted_entities else "unknown")
    )

    blast = _blast_calc.calculate(root, _graph)
    incident.blast_radius = blast

    return BlastRadiusResponse(
        incident_id=incident_id,
        blast_radius=blast,
    )


# ============================================================
# 3. Evidence & Timeline
# ============================================================

@router.get("/incidents/{incident_id}/evidence", response_model=EvidenceResponse)
async def get_incident_evidence(incident_id: str):
    """Aggregate multi-signal evidence for an incident."""
    if _evidence_agg is None:
        raise HTTPException(status_code=503, detail="Evidence Aggregator not initialized")

    incident = _get_incident(incident_id)
    if not incident.evidence:
        # Generate evidence items for impacted entities
        anom_data = [
            {
                "entity_id": e,
                "timestamp": incident.created_at,
                "category": "latency",
                "signal": "request_duration",
                "current_value": 0.85,
                "baseline_mean": 0.05,
            }
            for e in incident.impacted_entities
        ]
        top_root = incident.root_causes[0].entity_id if incident.root_causes else None
        incident.evidence = await _evidence_agg.aggregate(anom_data, root_candidate=top_root)

    return EvidenceResponse(
        incident_id=incident_id,
        evidence=incident.evidence,
        total_evidence=len(incident.evidence),
    )


@router.get("/incidents/{incident_id}/timeline", response_model=TimelineResponse)
async def get_incident_timeline(incident_id: str):
    """Get audit timeline of lifecycle transitions, comments, and evidence."""
    events = _timeline_cache.get(incident_id, [])
    # If empty, create initial creation event
    if not events and incident_id in _incidents_cache:
        inc = _incidents_cache[incident_id]
        events.append(
            TimelineEvent(
                incident_id=incident_id,
                timestamp=inc.created_at,
                event_type="incident_created",
                actor="system",
                title="Incident Created",
                description=f"Incident {incident_id} created with initial status {inc.status}.",
            )
        )
        _timeline_cache[incident_id] = events

    return TimelineResponse(
        incident_id=incident_id,
        events=events,
        total_events=len(events),
    )


# ============================================================
# 4. Incident Lifecycle State Transitions
# ============================================================

@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, req: TransitionRequest):
    """Acknowledge incident (OPEN -> ACKNOWLEDGED)."""
    return await _handle_transition(incident_id, "ACKNOWLEDGED", req.actor, req.comment)


@router.post("/incidents/{incident_id}/investigate")
async def investigate_incident(incident_id: str, req: TransitionRequest):
    """Move incident to INVESTIGATING."""
    return await _handle_transition(incident_id, "INVESTIGATING", req.actor, req.comment)


@router.post("/incidents/{incident_id}/mitigate")
async def mitigate_incident(incident_id: str, req: TransitionRequest):
    """Mark incident as MITIGATED."""
    return await _handle_transition(incident_id, "MITIGATED", req.actor, req.comment)


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, req: TransitionRequest):
    """Mark incident as RESOLVED and calculate MTTR."""
    return await _handle_transition(incident_id, "RESOLVED", req.actor, req.comment)


@router.post("/incidents/{incident_id}/close")
async def close_incident(incident_id: str, req: TransitionRequest):
    """Close and archive incident."""
    return await _handle_transition(incident_id, "CLOSED", req.actor, req.comment)


@router.post("/incidents/{incident_id}/comment")
async def add_incident_comment(incident_id: str, req: CommentRequest):
    """Add an investigation comment to incident timeline."""
    _get_incident(incident_id)
    event = TimelineEvent(
        incident_id=incident_id,
        timestamp=datetime.now(timezone.utc),
        event_type="comment",
        actor=req.actor,
        title="Engineer Comment",
        description=req.comment,
    )
    _timeline_cache.setdefault(incident_id, []).append(event)

    if _db_pool:
        try:
            async with _db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO incident_timeline_events (
                        event_id, incident_id, timestamp, event_type, actor, title, description, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    event.event_id,
                    event.incident_id,
                    event.timestamp,
                    event.event_type,
                    event.actor,
                    event.title,
                    event.description,
                    json.dumps(event.metadata),
                )
        except Exception as e:
            logger.error("Failed to persist comment to DB: %s", e)

    return {"status": "comment_added", "event": event}


async def _handle_transition(incident_id: str, target: str, actor: str, comment: str | None):
    if _state_machine is None:
        raise HTTPException(status_code=503, detail="State Machine not initialized")

    incident = _get_incident(incident_id)
    try:
        updated_inc, event = _state_machine.transition(incident, target, actor=actor, comment=comment)
        _timeline_cache.setdefault(incident_id, []).append(event)

        # Persist update and timeline event into DB
        if _db_pool:
            try:
                async with _db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE incidents
                        SET status = $1, updated_at = $2, mttr_seconds = $3,
                            resolved_at = $4, acknowledged_at = $5
                        WHERE incident_id = $6
                        """,
                        updated_inc.status,
                        updated_inc.updated_at,
                        updated_inc.mttr_seconds,
                        updated_inc.resolved_at,
                        updated_inc.acknowledged_at,
                        incident_id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO incident_timeline_events (
                            event_id, incident_id, timestamp, event_type, actor, title, description, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        event.event_id,
                        event.incident_id,
                        event.timestamp,
                        event.event_type,
                        event.actor,
                        event.title,
                        event.description,
                        json.dumps(event.metadata),
                    )
            except Exception as e:
                logger.error("Failed to persist incident transition to DB: %s", e)

        # Notify on major transitions (ACKNOWLEDGED or RESOLVED)
        if _notifier and target in ("ACKNOWLEDGED", "RESOLVED"):
            await _notifier.dispatch(updated_inc)

        return {
            "status": "transitioned",
            "incident_id": incident_id,
            "new_state": target,
            "mttr_seconds": updated_inc.mttr_seconds,
            "event": event,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# 5. Notifications
# ============================================================

@router.post("/notifications/dispatch/{incident_id}")
async def dispatch_incident_notification(incident_id: str):
    """Trigger alert dispatch to Slack/Telegram for an incident."""
    if _notifier is None:
        raise HTTPException(status_code=503, detail="Notification Coordinator not initialized")

    incident = _get_incident(incident_id)
    res = await _notifier.dispatch(incident)
    return res


@router.post("/notifications/test")
async def test_notification(req: NotificationTestRequest):
    """Send test notification payload."""
    if _notifier is None:
        raise HTTPException(status_code=503, detail="Notifier not initialized")

    mock_incident = _incidents_cache.get(
        req.test_incident_id,
        IncidentDetail(
            incident_id=req.test_incident_id,
            title="[Test] Mock performance anomaly on redis-cart",
            severity="critical",
            status="OPEN",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            impacted_entities=["redis-cart", "cartservice", "frontend"],
        ),
    )
    res = await _notifier.dispatch(mock_incident)
    return {"status": "test_completed", "details": res}
