"""Propagation Scorer: measures blast impact across dependent services."""

import logging
import networkx as nx

logger = logging.getLogger("rca.scoring.propagation")


class PropagationScorer:
    """Scores entities based on how many other impacted entities depend on them."""

    def score(self, entities: list[str], graph: nx.DiGraph | None = None) -> dict[str, float]:
        if not entities:
            return {}

        if graph is None or len(graph) == 0:
            return {e: 0.5 for e in entities}

        entity_set = set(entities)
        scores = {}
        total = max(1, len(entities) - 1)

        for eid in entities:
            if eid not in graph:
                scores[eid] = 0.2
                continue

            # Upstream callers of eid (services that depend on eid)
            # Find all nodes that can reach eid in the directed graph
            try:
                # In DiGraph where edge is caller -> callee, predecessors can reach eid
                dependents = set()
                visited = {eid}
                queue = [eid]
                while queue:
                    curr = queue.pop(0)
                    for pred in graph.predecessors(curr):
                        if pred not in visited:
                            visited.add(pred)
                            if pred in entity_set:
                                dependents.add(pred)
                            queue.append(pred)

                ratio = len(dependents) / total
                scores[eid] = round(min(1.0, max(0.1, 0.2 + 0.8 * ratio)), 3)
            except Exception as e:
                logger.warning("Error computing propagation score for %s: %s", eid, e)
                scores[eid] = 0.3

        return scores
