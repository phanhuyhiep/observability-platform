"""Incident Merger: merges overlapping incidents sharing entities or temporal proximity."""

import logging
from datetime import datetime, timezone

from src.models import Incident

logger = logging.getLogger("correlation.incident.merger")

SEVERITY_ORDER = {"critical": 4, "high": 3, "warning": 2, "info": 1}


class IncidentMerger:
    """Merges newly created incidents into ongoing active incidents to prevent fragmentation."""

    def __init__(self, merge_window_seconds: int = 600):
        self.merge_window_seconds = merge_window_seconds

    def try_merge(
        self,
        candidate: Incident,
        active_incidents: list[Incident],
    ) -> tuple[Incident, bool]:
        """
        Attempt to merge candidate incident into an existing open incident.
        Returns:
            (resulting_incident, was_merged)
        """
        now = datetime.now(timezone.utc)
        cand_entities = set(candidate.impacted_entities)
        cand_root = (
            candidate.topology_context.root_entity_candidate
            if candidate.topology_context
            else None
        )

        for existing in active_incidents:
            if existing.status not in ("OPEN", "ACKNOWLEDGED"):
                continue

            # 1. Time difference check
            time_diff = abs((candidate.created_at - existing.updated_at).total_seconds())
            if time_diff > self.merge_window_seconds:
                continue

            # 2. Entity or Root Entity overlap check
            existing_entities = set(existing.impacted_entities)
            existing_root = (
                existing.topology_context.root_entity_candidate
                if existing.topology_context
                else None
            )

            entities_overlap = bool(cand_entities.intersection(existing_entities))
            root_overlap = cand_root is not None and cand_root == existing_root

            if entities_overlap or root_overlap:
                # Merge candidate into existing
                merged_anomalies = list(set(existing.anomaly_ids + candidate.anomaly_ids))
                merged_entities = sorted(list(existing_entities.union(cand_entities)))
                merged_namespaces = sorted(
                    list(set(existing.namespaces + candidate.namespaces))
                )

                # Escalate severity if candidate has higher severity
                cand_weight = SEVERITY_ORDER.get(candidate.severity.lower(), 1)
                exist_weight = SEVERITY_ORDER.get(existing.severity.lower(), 1)
                if cand_weight > exist_weight:
                    existing.severity = candidate.severity

                existing.anomaly_ids = merged_anomalies
                existing.anomaly_count = len(merged_anomalies)
                existing.impacted_entities = merged_entities
                existing.entity_count = len(merged_entities)
                existing.namespaces = merged_namespaces
                existing.updated_at = now

                # Preserve richer topology context if available
                if not existing.topology_context and candidate.topology_context:
                    existing.topology_context = candidate.topology_context
                if not existing.deployment_context and candidate.deployment_context:
                    existing.deployment_context = candidate.deployment_context

                logger.info(
                    "Merged incident candidate into existing %s (anomalies: %d, entities: %d)",
                    existing.incident_id,
                    existing.anomaly_count,
                    existing.entity_count,
                )
                return existing, True

        return candidate, False
