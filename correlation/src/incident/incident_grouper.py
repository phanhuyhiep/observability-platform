"""Incident Grouper: transforms correlated anomaly groups into formal Incident candidates."""

import logging
from datetime import datetime, timezone

from src.models import CorrelationGroup, Incident

logger = logging.getLogger("correlation.incident.grouper")

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "warning": 2, "info": 1}


class IncidentGrouper:
    """Evaluates correlation groups and produces structured Incidents."""

    def __init__(
        self,
        auto_create: bool = True,
        min_anomalies: int = 2,
        critical_auto_create: bool = True,
    ):
        self.auto_create = auto_create
        self.min_anomalies = min_anomalies
        self.critical_auto_create = critical_auto_create
        self._next_id_counter = 1001

    def set_starting_id(self, start_id: int) -> None:
        """Set the starting counter for INC-XXXX generation."""
        self._next_id_counter = start_id

    def generate_incident_id(self) -> str:
        """Generate human-readable ID like INC-1001."""
        inc_id = f"INC-{self._next_id_counter}"
        self._next_id_counter += 1
        return inc_id

    def should_create_incident(self, group: CorrelationGroup) -> bool:
        """Check if group meets incident creation threshold."""
        if not self.auto_create:
            return False

        anom_count = len(group.anomalies)
        if anom_count >= self.min_anomalies:
            return True

        if self.critical_auto_create:
            has_critical = any(a.severity == "critical" for a in group.anomalies)
            if has_critical:
                return True

        return False

    def calculate_severity(self, group: CorrelationGroup) -> str:
        """Calculate overall Incident severity based on anomaly count and severity."""
        severities = [a.severity.lower() for a in group.anomalies]
        if "critical" in severities:
            return "critical"

        high_count = severities.count("high")
        if high_count >= 3:
            return "critical"
        if high_count >= 1:
            return "high"

        if "warning" in severities:
            return "warning"

        return "info"

    def generate_title(self, group: CorrelationGroup) -> str:
        """Generate a concise, descriptive title based on correlation context."""
        # 1. Deployment correlation title
        if group.deployment_context and group.deployment_context.deployment_correlated:
            entity = group.deployment_context.deployed_entity
            version = group.deployment_context.details.get("new_version", "")
            ver_str = f" v{version}" if version else ""
            return f"[{entity}] performance degradation after deployment{ver_str}"

        # 2. Topology correlation title with root candidate
        if group.topology_context and group.topology_context.root_entity_candidate:
            root = group.topology_context.root_entity_candidate
            impacted = {a.entity_id for a in group.anomalies if a.entity_id != root}
            if impacted:
                return f"[{root}] failure causing cascade to {', '.join(sorted(list(impacted))[:2])}"
            return f"[{root}] service anomaly event"

        # 3. Multiple entities in same namespace
        namespaces = {a.namespace for a in group.anomalies if a.namespace}
        ns_str = list(namespaces)[0] if namespaces else "cluster"
        categories = {a.category for a in group.anomalies}
        cat_str = list(categories)[0] if categories else "performance"

        return f"Multiple correlated {cat_str} anomalies in namespace [{ns_str}]"

    def create_incident(self, group: CorrelationGroup, custom_id: str | None = None) -> Incident:
        """Create an Incident object from a CorrelationGroup."""
        now = datetime.now(timezone.utc)
        incident_id = custom_id or self.generate_incident_id()
        severity = self.calculate_severity(group)
        title = self.generate_title(group)

        impacted_entities = sorted(list({a.entity_id for a in group.anomalies}))
        namespaces = sorted(list({a.namespace for a in group.anomalies if a.namespace}))
        anomaly_ids = [a.anomaly_id for a in group.anomalies]

        return Incident(
            incident_id=incident_id,
            title=title,
            severity=severity,
            status="OPEN",
            created_at=now,
            updated_at=now,
            correlation_id=group.correlation_id,
            anomaly_count=len(anomaly_ids),
            entity_count=len(impacted_entities),
            impacted_entities=impacted_entities,
            namespaces=namespaces,
            cluster=group.anomalies[0].cluster if group.anomalies else None,
            topology_context=group.topology_context,
            deployment_context=group.deployment_context,
            anomaly_ids=anomaly_ids,
            metadata={
                "correlation_type": group.correlation_type,
                "window_start": group.window_start.isoformat(),
                "window_end": group.window_end.isoformat() if group.window_end else None,
            },
        )
