"""Blast Radius Calculator: determines direct and indirect cascade impact on services and users."""

import logging
import networkx as nx

from src.models import BlastRadius

logger = logging.getLogger("rca.blast_radius")


class BlastRadiusCalculator:
    """Calculates downstream and upstream failure impact propagation from root cause."""

    def __init__(
        self,
        max_depth: int = 4,
        user_facing_services: list[str] | None = None,
    ):
        self.max_depth = max_depth
        self.user_facing_services = set(
            user_facing_services or ["frontend", "api-gateway", "web", "ingress"]
        )

    def calculate(self, root_entity: str, graph: nx.DiGraph | None = None) -> BlastRadius:
        """
        Traverse the graph from root_entity to discover directly and indirectly affected services.
        In caller -> callee graph, callers of root_entity (predecessors) are impacted by root_entity failure.
        """
        if graph is None or root_entity not in graph:
            return BlastRadius(
                root_entity=root_entity,
                direct_impact=[],
                indirect_impact=[],
                total_impacted=0,
                user_facing_services=[root_entity] if root_entity in self.user_facing_services else [],
                estimated_user_impact="low",
            )

        # BFS on predecessors (callers that depend on root_entity)
        direct_impact: set[str] = set()
        indirect_impact: set[str] = set()

        visited = {root_entity: 0}
        queue = [(root_entity, 0)]

        while queue:
            curr, depth = queue.pop(0)
            if depth >= self.max_depth:
                continue

            for pred in graph.predecessors(curr):
                if pred not in visited or depth + 1 < visited[pred]:
                    visited[pred] = depth + 1
                    if depth + 1 == 1:
                        direct_impact.add(pred)
                    else:
                        indirect_impact.add(pred)
                    queue.append((pred, depth + 1))

        # Also check if root_entity itself is a caller whose downstream callees failed
        for succ in graph.successors(root_entity):
            if succ not in visited:
                direct_impact.add(succ)

        all_impacted = direct_impact.union(indirect_impact)
        impacted_user_facing = list(all_impacted.intersection(self.user_facing_services))
        if root_entity in self.user_facing_services:
            impacted_user_facing.append(root_entity)

        # Classify estimated user impact
        if any(uf in direct_impact for uf in self.user_facing_services):
            impact_level = "critical"
        elif impacted_user_facing:
            impact_level = "high"
        elif len(all_impacted) >= 3:
            impact_level = "medium"
        else:
            impact_level = "low"

        return BlastRadius(
            root_entity=root_entity,
            direct_impact=sorted(list(direct_impact)),
            indirect_impact=sorted(list(indirect_impact - direct_impact)),
            total_impacted=len(all_impacted),
            user_facing_services=sorted(impacted_user_facing),
            estimated_user_impact=impact_level,
        )
