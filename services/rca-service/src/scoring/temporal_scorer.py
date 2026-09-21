"""Temporal Scorer: scores entities based on earliest anomaly onset timestamp."""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rca.scoring.temporal")


class TemporalScorer:
    """Calculates temporal score. The earliest failing entity receives the highest score."""

    def score(self, entity_timestamps: dict[str, datetime]) -> dict[str, float]:
        """
        Args:
            entity_timestamps: dict of entity_id -> earliest anomaly timestamp
        Returns:
            dict of entity_id -> temporal score in [0.0, 1.0]
        """
        if not entity_timestamps:
            return {}

        if len(entity_timestamps) == 1:
            return {next(iter(entity_timestamps)): 1.0}

        # Ensure all have tzinfo
        normalized = {}
        for eid, ts in entity_timestamps.items():
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            normalized[eid] = ts

        sorted_entities = sorted(normalized.items(), key=lambda x: x[1])
        earliest_ts = sorted_entities[0][1]
        latest_ts = sorted_entities[-1][1]

        total_span = (latest_ts - earliest_ts).total_seconds()
        if total_span <= 0:
            return {eid: 1.0 for eid in entity_timestamps}

        scores = {}
        for eid, ts in normalized.items():
            delta = (ts - earliest_ts).total_seconds()
            # Linear decay from 1.0 to 0.1 over total_span
            decay = 1.0 - (delta / total_span) * 0.9
            scores[eid] = round(max(0.1, decay), 3)

        # Ensure earliest has exactly 1.0
        scores[sorted_entities[0][0]] = 1.0
        return scores
