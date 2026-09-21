"""Topology Correlator: analyzes service dependencies to determine causality and root entity."""

import logging
from typing import Any

from src.graph.graph_query import GraphQuery
from src.models import CorrelationGroup, TopologyContext

logger = logging.getLogger("correlation.topology")


class TopologyCorrelator:
    """Enriches correlation groups with Service Dependency Graph topology context."""

    def __init__(self, query: GraphQuery, max_hop_depth: int = 3):
        self.query = query
        self.max_hop_depth = max_hop_depth

    def correlate(self, group: CorrelationGroup) -> CorrelationGroup:
        """Analyze anomalies in group against service graph topology."""
        if not group.anomalies:
            return group

        # 1. Map earliest anomaly timestamp per entity
        entity_timestamps: dict[str, Any] = {}
        for a in group.anomalies:
            eid = a.entity_id
            if eid not in entity_timestamps or a.timestamp < entity_timestamps[eid]:
                entity_timestamps[eid] = a.timestamp

        distinct_entities = list(entity_timestamps.keys())

        if len(distinct_entities) == 1:
            # Single entity with multiple anomalies (e.g. CPU + latency)
            group.topology_context = TopologyContext(
                has_dependency_relation=False,
                propagation_direction="isolated",
                propagation_paths=[],
                root_entity_candidate=distinct_entities[0],
                topology_confidence=0.6,
                dependency_chains=[distinct_entities[0]],
            )
            return group

        # 2. Check pairwise paths between all entity pairs
        connected_pairs = []
        propagation_paths = []
        dependency_chains = []

        for i, e1 in enumerate(distinct_entities):
            for e2 in distinct_entities[i + 1 :]:
                rel = self.query.find_relationship(e1, e2, self.max_hop_depth)
                if rel:
                    direction, path = rel
                    connected_pairs.append((e1, e2, direction, path))
                    propagation_paths.append(path)
                    chain_str = " ➔ ".join(path)
                    if chain_str not in dependency_chains:
                        dependency_chains.append(chain_str)

        has_relations = len(connected_pairs) > 0

        # 3. Determine Root Entity Candidate & Propagation Direction
        root_candidate = None
        direction_type = "none"
        confidence = 0.5

        if has_relations:
            # Rank candidates: earliest timestamp + topological depth
            # In microservices, deep downstream dependency (e.g. database/backend) failing first is downstream causality
            # Sort entities by timestamp
            sorted_by_time = sorted(distinct_entities, key=lambda e: entity_timestamps[e])
            earliest_entity = sorted_by_time[0]

            # Check if earliest_entity is a callee (downstream of others)
            # If callers had anomalies after this callee, the callee is the root cause!
            callers_of_earliest = self.query.get_upstream(earliest_entity, self.max_hop_depth)
            impacted_callers = [e for e in distinct_entities if e in callers_of_earliest]

            if impacted_callers:
                # Upstream callers were impacted by earliest downstream service
                root_candidate = earliest_entity
                direction_type = "downstream_caused_upstream_impact"
                confidence = 0.90
            else:
                # Check if earliest entity called others (e.g. traffic surge from frontend)
                callees_of_earliest = self.query.get_downstream(earliest_entity, self.max_hop_depth)
                impacted_callees = [e for e in distinct_entities if e in callees_of_earliest]
                if impacted_callees:
                    root_candidate = earliest_entity
                    direction_type = "upstream_surge_propagated_downstream"
                    confidence = 0.85
                else:
                    root_candidate = earliest_entity
                    direction_type = "chronological"
                    confidence = 0.70
        else:
            # No topological edge found between entities
            sorted_by_time = sorted(distinct_entities, key=lambda e: entity_timestamps[e])
            root_candidate = sorted_by_time[0]
            direction_type = "unconnected_temporal"
            confidence = 0.40

        group.topology_context = TopologyContext(
            has_dependency_relation=has_relations,
            propagation_direction=direction_type,
            propagation_paths=propagation_paths,
            root_entity_candidate=root_candidate,
            topology_confidence=round(confidence, 2),
            dependency_chains=dependency_chains,
        )

        if has_relations:
            group.correlation_type = "topology"

        return group
