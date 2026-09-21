"""Root Cause Ranker: aggregates multi-signal scores and ranks candidate root causes."""

import logging
from datetime import datetime
from typing import Any

import networkx as nx

from src.config import RCAWeights
from src.models import RootCauseCandidate, ScoreBreakdown
from src.scoring.deployment_scorer import DeploymentScorer
from src.scoring.evidence_scorer import EvidenceScorer
from src.scoring.propagation_scorer import PropagationScorer
from src.scoring.severity_scorer import SeverityScorer
from src.scoring.temporal_scorer import TemporalScorer
from src.scoring.topology_scorer import TopologyScorer

logger = logging.getLogger("rca.scoring.ranker")


class RootCauseRanker:
    """Combines temporal, topological, propagation, severity, deployment, and evidence scores."""

    def __init__(self, weights: RCAWeights | None = None):
        self.weights = weights or RCAWeights()
        self.temporal_scorer = TemporalScorer()
        self.topology_scorer = TopologyScorer()
        self.propagation_scorer = PropagationScorer()
        self.severity_scorer = SeverityScorer()
        self.deployment_scorer = DeploymentScorer()
        self.evidence_scorer = EvidenceScorer()

    def rank(
        self,
        entities: list[str],
        entity_timestamps: dict[str, datetime],
        entity_anomalies: dict[str, list[dict[str, Any]]],
        graph: nx.DiGraph | None = None,
        incident_time: datetime | None = None,
        recent_deployments: list[dict[str, Any]] | None = None,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> list[RootCauseCandidate]:
        """Rank impacted entities by likelihood of being the root cause."""
        if not entities:
            return []

        recent_deployments = recent_deployments or []
        evidence_items = evidence_items or []
        inc_time = incident_time or min(entity_timestamps.values()) if entity_timestamps else datetime.utcnow()

        # 1. Compute individual score components
        s_temp = self.temporal_scorer.score(entity_timestamps)
        s_topo = self.topology_scorer.score(entities, graph)
        s_prop = self.propagation_scorer.score(entities, graph)
        s_sev = self.severity_scorer.score(entity_anomalies)
        s_dep = self.deployment_scorer.score(entities, inc_time, recent_deployments)
        s_evi = self.evidence_scorer.score(entities, evidence_items)

        # 2. Weighted score combination
        candidates: list[dict[str, Any]] = []

        for eid in entities:
            breakdown = ScoreBreakdown(
                temporal=s_temp.get(eid, 0.5),
                topology=s_topo.get(eid, 0.5),
                propagation=s_prop.get(eid, 0.3),
                severity=s_sev.get(eid, 0.5),
                deployment=s_dep.get(eid, 0.0),
                evidence=s_evi.get(eid, 0.2),
            )

            total_score = (
                self.weights.temporal * breakdown.temporal
                + self.weights.topology * breakdown.topology
                + self.weights.propagation * breakdown.propagation
                + self.weights.severity * breakdown.severity
                + self.weights.deployment * breakdown.deployment
                + self.weights.evidence * breakdown.evidence
            )
            total_score = round(min(1.0, max(0.05, total_score)), 3)

            # Collect anomaly signals for this entity
            anoms = entity_anomalies.get(eid, [])
            signals = sorted(list({a.get("signal", "unknown") for a in anoms if a.get("signal")}))
            first_ts = entity_timestamps.get(eid)

            candidates.append({
                "entity_id": eid,
                "score": total_score,
                "breakdown": breakdown,
                "signals": signals,
                "first_ts": first_ts,
            })

        # 3. Sort candidates descending by total_score
        candidates.sort(key=lambda c: c["score"], reverse=True)

        # 4. Calculate confidence scores
        results: list[RootCauseCandidate] = []
        top_score = candidates[0]["score"]
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0

        for rank_idx, c in enumerate(candidates, start=1):
            # Confidence considers absolute score and margin over next candidate
            if rank_idx == 1:
                margin = top_score - second_score
                confidence = round(min(0.98, max(0.50, top_score * 0.7 + margin * 0.3 + 0.2)), 2)
                desc = f"Primary root cause candidate (top score {top_score:.2f} with strong correlation signals)"
            else:
                confidence = round(max(0.20, c["score"] * 0.7), 2)
                desc = f"Secondary contributing factor or upstream cascading impact"

            results.append(
                RootCauseCandidate(
                    rank=rank_idx,
                    entity_id=c["entity_id"],
                    entity_type="database" if any(db in c["entity_id"] for db in ["postgres", "redis", "db"]) else "service",
                    description=desc,
                    score=c["score"],
                    confidence=confidence,
                    scores_breakdown=c["breakdown"],
                    first_anomaly_at=c["first_ts"],
                    anomaly_signals=c["signals"],
                )
            )

        return results
