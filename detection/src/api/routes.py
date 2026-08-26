"""FastAPI routes for Detection Service API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..models import AnomalyEvent, AnomalyFilter, AnomalyListResponse, Baseline, Rule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["detection"])

# These will be set by main.py during startup
_orchestrator = None
_db_pool = None


def set_dependencies(orchestrator, db_pool):
    """Inject dependencies from main app."""
    global _orchestrator, _db_pool
    _orchestrator = orchestrator
    _db_pool = db_pool


# ============================================================
# Anomaly Events
# ============================================================

@router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    entity_type: str | None = None,
    entity_id: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    detector: str | None = None,
    status: str | None = Query(default="active"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List anomaly events with filters."""
    if not _db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    conditions = []
    params: list[Any] = []
    idx = 1

    if entity_type:
        conditions.append(f"entity_type = ${idx}")
        params.append(entity_type)
        idx += 1
    if entity_id:
        conditions.append(f"entity_id = ${idx}")
        params.append(entity_id)
        idx += 1
    if severity:
        conditions.append(f"severity = ${idx}")
        params.append(severity)
        idx += 1
    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1
    if detector:
        conditions.append(f"detector = ${idx}")
        params.append(detector)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * limit

    total_row = await _db_pool.fetchrow(
        f"SELECT COUNT(*) as cnt FROM anomaly_events WHERE {where}", *params
    )
    total = total_row["cnt"] if total_row else 0

    rows = await _db_pool.fetch(
        f"""
        SELECT * FROM anomaly_events
        WHERE {where}
        ORDER BY detected_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params, limit, offset,
    )

    items = [_row_to_anomaly(r) for r in rows]
    return AnomalyListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/anomalies/{anomaly_id}")
async def get_anomaly(anomaly_id: str):
    """Get a specific anomaly event by ID."""
    if not _db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db_pool.fetchrow(
        "SELECT * FROM anomaly_events WHERE anomaly_id = $1", anomaly_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    return _row_to_anomaly(row)


@router.patch("/anomalies/{anomaly_id}")
async def update_anomaly_status(anomaly_id: str, status: str):
    """Update anomaly status (resolve, suppress)."""
    if not _db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    if status not in ("active", "resolved", "suppressed"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = await _db_pool.execute(
        """
        UPDATE anomaly_events SET status = $1,
            resolved_at = CASE WHEN $1 = 'resolved' THEN now() ELSE resolved_at END
        WHERE anomaly_id = $2
        """,
        status, anomaly_id,
    )
    return {"updated": True, "anomaly_id": anomaly_id, "status": status}


# ============================================================
# Rules
# ============================================================

@router.get("/rules")
async def list_rules():
    """List all loaded detection rules."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    rules = _orchestrator.rule_detector.get_rules()
    return [r.model_dump() for r in rules]


@router.post("/rules")
async def create_rule(rule: Rule):
    """Create a new custom detection rule."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    _orchestrator.rule_detector.add_rule(rule)
    return {"created": True, "rule_id": rule.id}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a detection rule."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    removed = _orchestrator.rule_detector.remove_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True, "rule_id": rule_id}


# ============================================================
# Baselines
# ============================================================

@router.get("/baselines")
async def list_baselines():
    """List all computed baselines."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    baselines = await _orchestrator.baseline_storage.list_baselines()
    return [b.model_dump() for b in baselines]


@router.get("/baselines/{entity_id}/{metric}")
async def get_baseline(entity_id: str, metric: str, entity_type: str = "service"):
    """Get baseline for a specific entity/metric."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    baseline = await _orchestrator.baseline_storage.get_baseline(
        entity_type, entity_id, metric
    )
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return baseline.model_dump()


# ============================================================
# Health
# ============================================================

@router.get("/health", tags=["health"])
async def health_check():
    """Service health check."""
    db_ok = False
    if _db_pool:
        try:
            await _db_pool.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "detectors": {
            "rule": _orchestrator.config.detectors.rule.enabled if _orchestrator else False,
            "zscore": _orchestrator.config.detectors.zscore.enabled if _orchestrator else False,
            "ewma": _orchestrator.config.detectors.ewma.enabled if _orchestrator else False,
        },
    }


# ============================================================
# Helpers
# ============================================================

def _row_to_anomaly(row) -> dict:
    """Convert a database row to anomaly event dict."""
    return {
        "anomaly_id": str(row["anomaly_id"]),
        "version": row["version"],
        "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
        "detected_at": row["detected_at"].isoformat() if row["detected_at"] else None,
        "entity": {
            "type": row["entity_type"],
            "id": row["entity_id"],
            "namespace": row["namespace"],
            "cluster": row.get("cluster"),
        },
        "detection": {
            "detector": row["detector"],
            "category": row["category"],
            "signal": row["signal"],
            "severity": row["severity"],
            "score": float(row["score"]) if row["score"] else 0,
            "confidence": float(row["confidence"]) if row["confidence"] else 0,
        },
        "values": {
            "current": row["current_value"],
            "baseline_mean": row["baseline_mean"],
            "baseline_std": row["baseline_std"],
            "z_score": row["z_score"],
        },
        "context": {
            "window": row["time_window"],
            "baseline_window": row["baseline_window"],
            "rule_id": row["rule_id"],
        },
        "status": row["status"],
    }
