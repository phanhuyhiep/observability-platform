"""Deployment Scorer: boosts score of entities that underwent recent deployments."""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rca.scoring.deployment")


class DeploymentScorer:
    """Scores entities based on proximity to recent deployment/rollout events."""

    def score(
        self,
        entities: list[str],
        incident_time: datetime,
        recent_deployments: list[dict[str, Any]],
    ) -> dict[str, float]:
        if incident_time.tzinfo is None:
            incident_time = incident_time.replace(tzinfo=timezone.utc)

        scores = {e: 0.0 for e in entities}
        if not recent_deployments:
            return scores

        for dep in recent_deployments:
            dep_entity = dep.get("entity_id")
            if not dep_entity:
                continue

            dep_ts = dep.get("timestamp")
            if isinstance(dep_ts, str):
                dep_ts = datetime.fromisoformat(dep_ts.replace("Z", "+00:00"))
            if dep_ts and dep_ts.tzinfo is None:
                dep_ts = dep_ts.replace(tzinfo=timezone.utc)

            if dep_ts and dep_ts <= incident_time:
                delta_sec = (incident_time - dep_ts).total_seconds()
                if delta_sec <= 1800:  # within 30 mins
                    if delta_sec <= 300:
                        dep_score = 1.0
                    elif delta_sec <= 900:
                        dep_score = 0.75
                    else:
                        dep_score = 0.40

                    # Match exact or substring
                    for eid in entities:
                        if eid == dep_entity or dep_entity in eid or eid in dep_entity:
                            if dep_score > scores[eid]:
                                scores[eid] = dep_score

        return scores
