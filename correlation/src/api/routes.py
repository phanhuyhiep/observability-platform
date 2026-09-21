"""FastAPI routes for Correlation Engine & Incident Intelligence."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.models import (
    CorrelationListResponse,
    DependencyListResponse,
    DeploymentWebhookRequest,
    IncidentListResponse,
    ManualEdgeRequest,
    ServiceGraphResponse,
    UpdateIncidentStatusRequest,
)
from src.models import (
    CorrelationGroup,
    DeploymentEvent,
    Incident,
    ServiceEdge,
    ServiceNode,
)
from src.orchestrator import CorrelationOrchestrator

logger = logging.getLogger("correlation.api")

router = APIRouter(prefix="/api/v1")

# Global orchestrator instance (set by main.py)
_orchestrator: CorrelationOrchestrator | None = None


def set_orchestrator(orchestrator: CorrelationOrchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def _get_orchestrator() -> CorrelationOrchestrator:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


# ============================================================
# 1. Topology & Service Dependency Graph
# ============================================================

@router.get("/topology/services", response_model=ServiceGraphResponse)
async def get_service_graph():
    """Retrieve full service dependency graph."""
    orch = _get_orchestrator()
    nodes = orch.storage.get_all_nodes()
    edges = orch.storage.get_all_edges()
    return ServiceGraphResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )


@router.get("/topology/services/{service_id}")
async def get_service_node(service_id: str):
    """Retrieve a specific service node and its immediate neighbors."""
    orch = _get_orchestrator()
    nodes = {n.node_id: n for n in orch.storage.get_all_nodes()}
    if service_id not in nodes:
        raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found in topology graph")

    in_edges = [e for e in orch.storage.get_all_edges() if e.target_id == service_id]
    out_edges = [e for e in orch.storage.get_all_edges() if e.source_id == service_id]

    return {
        "node": nodes[service_id],
        "incoming_edges": in_edges,
        "outgoing_edges": out_edges,
    }


@router.get("/topology/services/{service_id}/upstream", response_model=DependencyListResponse)
async def get_upstream_services(service_id: str, depth: int = Query(default=3, ge=1, le=5)):
    """Get all upstream callers that depend on service_id."""
    orch = _get_orchestrator()
    upstream = orch.query.get_upstream(service_id, max_depth=depth)
    return DependencyListResponse(
        entity_id=service_id,
        direction="upstream",
        dependencies=upstream,
        count=len(upstream),
    )


@router.get("/topology/services/{service_id}/downstream", response_model=DependencyListResponse)
async def get_downstream_services(service_id: str, depth: int = Query(default=3, ge=1, le=5)):
    """Get all downstream callees that service_id depends on."""
    orch = _get_orchestrator()
    downstream = orch.query.get_downstream(service_id, max_depth=depth)
    return DependencyListResponse(
        entity_id=service_id,
        direction="downstream",
        dependencies=downstream,
        count=len(downstream),
    )


@router.post("/topology/edges")
async def create_manual_edge(req: ManualEdgeRequest):
    """Declare a manual dependency edge between services."""
    orch = _get_orchestrator()
    edge = ServiceEdge(
        source_id=req.source_id,
        target_id=req.target_id,
        dependency_type=req.dependency_type,
        metadata=req.metadata,
        discovered_by="manual",
    )
    orch.storage.add_edge(edge)
    if orch.pool:
        await orch.storage.sync_to_db(orch.pool)
    return {"status": "created", "edge": edge}


@router.delete("/topology/edges")
async def delete_edge(
    source_id: str = Query(...),
    target_id: str = Query(...),
    dependency_type: str = Query(default="http"),
):
    """Remove a dependency edge."""
    orch = _get_orchestrator()
    deleted = orch.storage.remove_edge(source_id, target_id, dependency_type)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")
    if orch.pool:
        async with orch.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM service_graph_edges WHERE source_id = $1 AND target_id = $2 AND dependency_type = $3",
                source_id,
                target_id,
                dependency_type,
            )
    return {"status": "deleted"}


# ============================================================
# 2. Correlation Groups
# ============================================================

@router.get("/correlations", response_model=CorrelationListResponse)
async def list_correlations(status: str | None = Query(default=None)):
    """List all correlation groups."""
    orch = _get_orchestrator()
    groups = list(orch.temporal.active_groups.values())
    if status:
        groups = [g for g in groups if g.status == status]
    groups.sort(key=lambda g: g.updated_at, reverse=True)
    return CorrelationListResponse(items=groups, total=len(groups))


@router.get("/correlations/{correlation_id}", response_model=CorrelationGroup)
async def get_correlation(correlation_id: str):
    """Get correlation group details."""
    orch = _get_orchestrator()
    if correlation_id in orch.temporal.active_groups:
        return orch.temporal.active_groups[correlation_id]
    raise HTTPException(status_code=404, detail="Correlation group not found")


@router.post("/correlations/evaluate")
async def trigger_evaluation():
    """Trigger an on-demand correlation evaluation cycle."""
    orch = _get_orchestrator()
    incidents = await orch.run_correlation_cycle()
    return {
        "status": "evaluated",
        "incidents_created_or_updated": len(incidents),
        "incidents": [i.incident_id for i in incidents],
    }


# ============================================================
# 3. Incidents
# ============================================================

@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
):
    """List incidents with optional filtering."""
    orch = _get_orchestrator()
    incidents = list(orch.active_incidents.values())

    if status:
        incidents = [i for i in incidents if i.status == status]
    if severity:
        incidents = [i for i in incidents if i.severity.lower() == severity.lower()]
    if entity_id:
        incidents = [i for i in incidents if entity_id in i.impacted_entities]

    incidents.sort(key=lambda i: i.created_at, reverse=True)
    return IncidentListResponse(items=incidents, total=len(incidents))


@router.get("/incidents/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Get detail of a specific incident."""
    orch = _get_orchestrator()
    if incident_id in orch.active_incidents:
        return orch.active_incidents[incident_id]
    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


@router.patch("/incidents/{incident_id}", response_model=Incident)
async def update_incident_status(incident_id: str, req: UpdateIncidentStatusRequest):
    """Update incident lifecycle status (e.g. ACKNOWLEDGED, RESOLVED, CLOSED)."""
    orch = _get_orchestrator()
    if incident_id not in orch.active_incidents:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    incident = orch.active_incidents[incident_id]
    incident.status = req.status
    now = datetime.now(timezone.utc)
    incident.updated_at = now
    if req.status in ("RESOLVED", "CLOSED"):
        incident.resolved_at = now

    if orch.pool:
        await orch.save_incident(incident)

    return incident


# ============================================================
# 4. Deployment Events Webhook
# ============================================================

@router.post("/deployments")
async def record_deployment(req: DeploymentWebhookRequest):
    """Receive and record deployment event from CI/CD webhook or Kubernetes."""
    orch = _get_orchestrator()
    ts = req.timestamp or datetime.now(timezone.utc)
    event = DeploymentEvent(
        timestamp=ts,
        event_type=req.event_type,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        namespace=req.namespace,
        cluster=req.cluster,
        details=req.details,
    )
    orch.deployment_collector.record_event(event)
    if orch.pool:
        await orch.deployment_collector.save_to_db(orch.pool, event)

    return {"status": "recorded", "event_id": event.event_id}


@router.get("/deployments")
async def list_deployments(within_minutes: int = Query(default=60, ge=5, le=1440)):
    """List recent deployment events."""
    orch = _get_orchestrator()
    deps = orch.deployment_collector.get_recent_deployments(within_seconds=within_minutes * 60)
    deps.sort(key=lambda d: d.timestamp, reverse=True)
    return {"deployments": deps, "total": len(deps)}
