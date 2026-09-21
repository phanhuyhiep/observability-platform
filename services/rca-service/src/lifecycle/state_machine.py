"""Incident Lifecycle State Machine: enforces valid transitions, updates timestamps, logs timeline events."""

import logging
from datetime import datetime, timezone
from typing import Any

from src.models import IncidentDetail, TimelineEvent

logger = logging.getLogger("rca.lifecycle.state_machine")

VALID_TRANSITIONS = {
    "OPEN": {"ACKNOWLEDGED", "INVESTIGATING", "MITIGATED", "RESOLVED", "CLOSED"},
    "ACKNOWLEDGED": {"INVESTIGATING", "MITIGATED", "RESOLVED", "CLOSED"},
    "INVESTIGATING": {"MITIGATED", "RESOLVED", "CLOSED"},
    "MITIGATED": {"RESOLVED", "CLOSED", "INVESTIGATING"},
    "RESOLVED": {"CLOSED", "OPEN"},
    "CLOSED": {"OPEN"},
}


class IncidentStateMachine:
    """Manages state transitions and timeline auditing for incidents."""

    def transition(
        self,
        incident: IncidentDetail,
        target_state: str,
        actor: str = "engineer",
        comment: str | None = None,
    ) -> tuple[IncidentDetail, TimelineEvent]:
        """
        Transition incident to target_state.
        Raises ValueError if transition is invalid.
        """
        current_state = incident.status.upper()
        target = target_state.upper()

        if target == current_state:
            # Idempotent
            event = TimelineEvent(
                incident_id=incident.incident_id,
                timestamp=datetime.now(timezone.utc),
                event_type="comment" if comment else "status_noop",
                actor=actor,
                title=f"Incident remained in {target}",
                description=comment or f"Status confirmed as {target}",
            )
            return incident, event

        allowed = VALID_TRANSITIONS.get(current_state, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid status transition from '{current_state}' to '{target}'. "
                f"Allowed transitions: {sorted(list(allowed))}"
            )

        now = datetime.now(timezone.utc)
        incident.status = target
        incident.updated_at = now

        # Update specific lifecycle timestamps
        if target == "ACKNOWLEDGED" and not incident.acknowledged_at:
            incident.acknowledged_at = now
            if not incident.mttd_seconds:
                incident.mttd_seconds = (now - incident.created_at).total_seconds()

        elif target == "INVESTIGATING" and not incident.investigating_at:
            incident.investigating_at = now

        elif target == "MITIGATED" and not incident.mitigated_at:
            incident.mitigated_at = now

        elif target == "RESOLVED":
            incident.resolved_at = now
            incident.mttr_seconds = (now - incident.created_at).total_seconds()

        elif target == "CLOSED":
            incident.closed_at = now
            if not incident.resolved_at:
                incident.resolved_at = now
                incident.mttr_seconds = (now - incident.created_at).total_seconds()

        # Build timeline event
        desc_parts = [f"Status changed from {current_state} to {target} by {actor}."]
        if comment:
            desc_parts.append(f"Note: {comment}")
        if incident.mttr_seconds and target in ("RESOLVED", "CLOSED"):
            desc_parts.append(f"MTTR: {incident.mttr_seconds:.1f}s.")

        timeline_event = TimelineEvent(
            incident_id=incident.incident_id,
            timestamp=now,
            event_type="state_change",
            actor=actor,
            title=f"Status: {target}",
            description=" ".join(desc_parts),
            metadata={
                "from_status": current_state,
                "to_status": target,
                "mttr_seconds": incident.mttr_seconds,
            },
        )

        logger.info(
            "Incident %s transitioned: %s -> %s by %s",
            incident.incident_id,
            current_state,
            target,
            actor,
        )

        return incident, timeline_event
