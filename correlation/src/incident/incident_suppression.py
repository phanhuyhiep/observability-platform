"""Incident Suppression: suppresses duplicate alerts when an active incident for the root entity exists."""

import logging

from src.models import Incident

logger = logging.getLogger("correlation.incident.suppression")


class IncidentSuppression:
    """Suppresses redundant incident creation to minimize alert fatigue."""

    def __init__(self, suppression_window_seconds: int = 1800):
        self.suppression_window_seconds = suppression_window_seconds

    def should_suppress(
        self,
        candidate: Incident,
        active_incidents: list[Incident],
    ) -> tuple[bool, str | None, str | None]:
        """
        Check if candidate incident should be suppressed.
        Returns:
            (is_suppressed, reason, existing_incident_id)
        """
        cand_root = (
            candidate.topology_context.root_entity_candidate
            if candidate.topology_context
            else None
        )
        cand_entities = set(candidate.impacted_entities)

        for existing in active_incidents:
            if existing.status not in ("OPEN", "ACKNOWLEDGED"):
                continue

            # Check time window
            age = (candidate.created_at - existing.created_at).total_seconds()
            if age > self.suppression_window_seconds:
                continue

            # 1. Exact root entity suppression
            existing_root = (
                existing.topology_context.root_entity_candidate
                if existing.topology_context
                else None
            )
            if cand_root and existing_root and cand_root == existing_root:
                reason = f"Active incident {existing.incident_id} already exists for root entity [{cand_root}]"
                logger.info("Suppressed incident candidate: %s", reason)
                return True, reason, existing.incident_id

            # 2. Complete subset suppression (if candidate entities are all already tracked by existing incident)
            if cand_entities and cand_entities.issubset(set(existing.impacted_entities)):
                reason = f"Active incident {existing.incident_id} already covers all entities: {cand_entities}"
                logger.info("Suppressed incident candidate: %s", reason)
                return True, reason, existing.incident_id

        return False, None, None
