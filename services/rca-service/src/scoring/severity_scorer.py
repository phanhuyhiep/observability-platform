"""Severity Scorer: scores entities based on anomaly severity and deviation magnitude."""

import logging
from typing import Any

logger = logging.getLogger("rca.scoring.severity")

SEVERITY_MAP = {
    "critical": 1.0,
    "high": 0.75,
    "warning": 0.50,
    "info": 0.25,
}


class SeverityScorer:
    """Scores entities based on maximum anomaly severity and deviation score."""

    def score(self, entity_anomalies: dict[str, list[dict[str, Any]]]) -> dict[str, float]:
        scores = {}
        for eid, anoms in entity_anomalies.items():
            if not anoms:
                scores[eid] = 0.5
                continue

            max_sev_score = 0.0
            max_z = 0.0

            for a in anoms:
                sev = a.get("severity", "warning").lower()
                sev_score = SEVERITY_MAP.get(sev, 0.5)
                if sev_score > max_sev_score:
                    max_sev_score = sev_score

                z = a.get("z_score")
                if z is not None and isinstance(z, (int, float)):
                    if abs(z) > max_z:
                        max_z = abs(z)

            # Deviation multiplier (z-score >= 5.0 adds up to 0.1)
            z_boost = min(0.1, (max_z / 50.0)) if max_z > 3.0 else 0.0
            final_score = round(min(1.0, max_sev_score + z_boost), 3)
            scores[eid] = final_score

        return scores
