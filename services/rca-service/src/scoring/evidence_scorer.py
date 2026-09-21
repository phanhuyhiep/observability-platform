"""Evidence Scorer: scores entities based on multi-signal evidence corroboration."""

import logging
from typing import Any

logger = logging.getLogger("rca.scoring.evidence")


class EvidenceScorer:
    """Scores entities based on diversity of corroborating telemetry signals."""

    def score(self, entities: list[str], evidence_items: list[dict[str, Any]]) -> dict[str, float]:
        if not entities:
            return {}

        scores = {}
        for eid in entities:
            entity_evidence = [ev for ev in evidence_items if ev.get("entity") == eid]
            types_found = {ev.get("type") for ev in entity_evidence}

            score = 0.2
            if "metric" in types_found:
                score += 0.35
            if "log" in types_found:
                score += 0.35
            if "trace" in types_found:
                score += 0.25
            if "k8s_event" in types_found:
                score += 0.15

            scores[eid] = round(min(1.0, score), 3)

        return scores
