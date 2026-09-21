"""Deployment Correlator: detects correlation between anomalies and recent deployment/rollout events."""

import logging
from datetime import datetime, timedelta, timezone

from src.models import CorrelationGroup, DeploymentContext, DeploymentEvent

logger = logging.getLogger("correlation.deployment")


class DeploymentCorrelator:
    """Matches anomaly events with recent deployments occurring within the correlation window."""

    def __init__(self, correlation_window_seconds: int = 1800):
        self.correlation_window = timedelta(seconds=correlation_window_seconds)

    def correlate(
        self,
        group: CorrelationGroup,
        recent_deployments: list[DeploymentEvent],
    ) -> CorrelationGroup:
        """Check if any anomaly in the group correlates with recent deployment events."""
        if not group.anomalies or not recent_deployments:
            return group

        earliest_anomaly = min(group.anomalies, key=lambda a: a.timestamp)
        earliest_ts = earliest_anomaly.timestamp
        if earliest_ts.tzinfo is None:
            earliest_ts = earliest_ts.replace(tzinfo=timezone.utc)

        distinct_entities = {a.entity_id for a in group.anomalies}

        best_match: DeploymentEvent | None = None
        min_time_delta_sec = float("inf")

        for dep in recent_deployments:
            dep_ts = dep.timestamp
            if dep_ts.tzinfo is None:
                dep_ts = dep_ts.replace(tzinfo=timezone.utc)

            # Deploy must happen before or at the time of the anomaly
            if dep_ts <= earliest_ts and (earliest_ts - dep_ts) <= self.correlation_window:
                # Check entity match (exact match or service name prefix match)
                if dep.entity_id in distinct_entities or any(dep.entity_id in e or e in dep.entity_id for e in distinct_entities):
                    delta_sec = (earliest_ts - dep_ts).total_seconds()
                    if delta_sec < min_time_delta_sec:
                        min_time_delta_sec = delta_sec
                        best_match = dep

        if best_match is not None:
            # Calculate confidence decaying with time
            if min_time_delta_sec <= 300:  # <= 5 mins
                confidence = 0.95
            elif min_time_delta_sec <= 900:  # <= 15 mins
                confidence = 0.85
            else:
                confidence = 0.70

            group.deployment_context = DeploymentContext(
                deployment_correlated=True,
                event_id=best_match.event_id,
                deployed_entity=best_match.entity_id,
                time_since_deploy_seconds=round(min_time_delta_sec, 1),
                deployment_confidence=confidence,
                details=best_match.details,
            )

            # If also topology correlated, it's hybrid; otherwise deployment
            if group.correlation_type == "topology":
                group.correlation_type = "hybrid"
            else:
                group.correlation_type = "deployment"

            logger.info(
                "Correlated group %s with deployment %s (delta: %.1fs, confidence: %.2f)",
                group.correlation_id,
                best_match.entity_id,
                min_time_delta_sec,
                confidence,
            )

        return group
