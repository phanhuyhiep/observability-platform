"""Auto Resolver: automatically transitions incidents to RESOLVED when telemetry stabilizes."""

import logging
from datetime import datetime, timedelta, timezone

from src.lifecycle.state_machine import IncidentStateMachine
from src.models import IncidentDetail, TimelineEvent

logger = logging.getLogger("rca.lifecycle.auto_resolver")


class AutoResolver:
    """Monitors active incidents and auto-resolves those whose anomaly signals have normalized."""

    def __init__(self, state_machine: IncidentStateMachine, auto_resolve_minutes: int = 15):
        self.state_machine = state_machine
        self.auto_resolve_delta = timedelta(minutes=auto_resolve_minutes)

    def check_and_resolve(
        self,
        incident: IncidentDetail,
        active_anomaly_ids: set[str],
    ) -> tuple[IncidentDetail, TimelineEvent] | None:
        """
        If none of the incident's anomalies are currently active and last update > auto_resolve_delta,
        transition to RESOLVED.
        """
        if incident.status not in ("OPEN", "ACKNOWLEDGED", "INVESTIGATING", "MITIGATED"):
            return None

        # Check if any associated anomalies are still active
        has_active_anomalies = any(aid in active_anomaly_ids for aid in (incident.metadata.get("anomaly_ids") or []))
        if has_active_anomalies:
            return None

        now = datetime.now(timezone.utc)
        upd = incident.updated_at
        if upd.tzinfo is None:
            upd = upd.replace(tzinfo=timezone.utc)

        if now - upd >= self.auto_resolve_delta:
            logger.info("Auto-resolving incident %s (telemetry normalized for %s)", incident.incident_id, self.auto_resolve_delta)
            return self.state_machine.transition(
                incident,
                target_state="RESOLVED",
                actor="auto-resolver",
                comment=f"All telemetry signals normalized for {self.auto_resolve_delta.total_seconds() / 60:.0f} minutes.",
            )

        return None
