"""Topology Scorer: scores entities based on position in the Service Dependency Graph."""

import logging
import networkx as nx

logger = logging.getLogger("rca.scoring.topology")


class TopologyScorer:
    """
    Calculates topology score. In a caller -> callee graph, leaf dependencies
    (deepest callees with no or few downstream services) receive higher scores.
    """

    def score(self, entities: list[str], graph: nx.DiGraph | None = None) -> dict[str, float]:
        """
        Args:
            entities: list of impacted entity_ids
            graph: NetworkX directed graph (caller -> callee)
        Returns:
            dict of entity_id -> topology score in [0.0, 1.0]
        """
        if not entities:
            return {}

        if graph is None or len(graph) == 0:
            return {e: 0.5 for e in entities}

        entity_set = set(entities)
        scores = {}

        for eid in entities:
            if eid not in graph:
                scores[eid] = 0.4
                continue

            # Outgoing edges from eid to other impacted entities
            # If eid has 0 outgoing edges to other impacted entities, eid is a leaf among impacted!
            out_neighbors = set(graph.successors(eid)).intersection(entity_set)
            in_neighbors = set(graph.predecessors(eid)).intersection(entity_set)

            # High score if many services call this entity (high in_degree) and it calls few/none (low out_degree)
            in_count = len(in_neighbors)
            out_count = len(out_neighbors)

            # Heuristic score
            score = 0.5 + (in_count * 0.25) - (out_count * 0.20)
            # Boost if database or storage
            if "postgres" in eid or "redis" in eid or "db" in eid or "mysql" in eid:
                score += 0.2

            scores[eid] = round(min(1.0, max(0.1, score)), 3)

        return scores
