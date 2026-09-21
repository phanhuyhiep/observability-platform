"""Temporal Correlator: sliding time-window grouping of anomaly events."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.models import AnomalyEvent, CorrelationGroup

logger = logging.getLogger("correlation.temporal")

SEVERITY_ORDER = {"critical": 4, "high": 3, "warning": 2, "info": 1}


class TemporalCorrelator:
    """Groups anomalies occurring in close temporal proximity using sliding windows."""

    def __init__(
        self,
        window_size_seconds: int = 300,
        max_window_extension_seconds: int = 900,
        inactivity_timeout_seconds: int = 600,
    ):
        self.window_size = timedelta(seconds=window_size_seconds)
        self.max_extension = timedelta(seconds=max_window_extension_seconds)
        self.inactivity_timeout = timedelta(seconds=inactivity_timeout_seconds)
        self.active_groups: dict[str, CorrelationGroup] = {}

    def _get_higher_severity(self, s1: str, s2: str) -> str:
        score1 = SEVERITY_ORDER.get(s1.lower(), 1)
        score2 = SEVERITY_ORDER.get(s2.lower(), 1)
        return s1 if score1 >= score2 else s2

    def correlate(self, anomalies: list[AnomalyEvent]) -> list[CorrelationGroup]:
        """
        Feed new anomalies and group them with existing or new sliding windows.
        Returns all active and recently updated correlation groups.
        """
        # Sort anomalies chronologically
        sorted_anomalies = sorted(anomalies, key=lambda a: a.timestamp)
        now = datetime.now(timezone.utc)

        for anomaly in sorted_anomalies:
            ts = anomaly.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            anomaly.timestamp = ts

            matched_group: CorrelationGroup | None = None

            # 1. Look for matching active group
            for group in self.active_groups.values():
                if group.status != "active":
                    continue

                # Check window overlap
                window_end = group.window_end or (group.window_start + self.window_size)
                # Allow grouping if anomaly is within window_start - buffer and window_end + window_size
                if group.window_start - timedelta(seconds=60) <= ts <= window_end + self.window_size:
                    # Same namespace or cluster check
                    group_namespaces = {a.namespace for a in group.anomalies if a.namespace}
                    if not group_namespaces or anomaly.namespace in group_namespaces:
                        matched_group = group
                        break

            # 2. Add to existing group or create new
            if matched_group is not None:
                # Avoid duplicate anomaly addition
                existing_ids = {a.anomaly_id for a in matched_group.anomalies}
                if anomaly.anomaly_id not in existing_ids:
                    matched_group.anomalies.append(anomaly)
                    matched_group.updated_at = now
                    matched_group.severity_max = self._get_higher_severity(
                        matched_group.severity_max, anomaly.severity
                    )

                    # Extend window if anomaly occurred past current window_end
                    current_end = matched_group.window_end or (matched_group.window_start + self.window_size)
                    if ts > current_end:
                        max_allowed_end = matched_group.window_start + self.max_extension
                        matched_group.window_end = min(ts + self.window_size, max_allowed_end)

                    # Update distinct entity count
                    entities = {a.entity_id for a in matched_group.anomalies}
                    matched_group.entity_count = len(entities)
            else:
                # Create a new correlation group
                new_group = CorrelationGroup(
                    correlation_id=str(uuid4()),
                    created_at=now,
                    updated_at=now,
                    window_start=ts,
                    window_end=ts + self.window_size,
                    status="active",
                    correlation_type="temporal",
                    anomalies=[anomaly],
                    entity_count=1,
                    severity_max=anomaly.severity,
                )
                self.active_groups[new_group.correlation_id] = new_group

        # 3. Clean up inactive groups
        self._prune_inactive_groups(now)

        return list(self.active_groups.values())

    def _prune_inactive_groups(self, now: datetime) -> None:
        """Close groups that have not received events for inactivity_timeout."""
        for group in list(self.active_groups.values()):
            if group.status == "active":
                last_updated = group.updated_at
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                if now - last_updated > self.inactivity_timeout:
                    group.status = "closed"
                    logger.debug("Closed correlation group %s due to inactivity", group.correlation_id)
