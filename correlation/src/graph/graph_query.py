"""Query interface for Service Dependency Graph."""

import networkx as nx

from src.graph.graph_storage import GraphStorage


class GraphQuery:
    """Provides upstream, downstream, path, and topology traversal queries."""

    def __init__(self, storage: GraphStorage):
        self.storage = storage

    @property
    def graph(self) -> nx.DiGraph:
        return self.storage.graph

    def get_downstream(self, entity_id: str, max_depth: int = 3) -> list[str]:
        """
        Get all services called by entity_id (dependencies / callees).
        Path: entity_id -> target.
        """
        if entity_id not in self.graph:
            return []

        downstream = set()
        visited = {entity_id: 0}
        queue = [(entity_id, 0)]

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for neighbor in self.graph.successors(curr):
                if neighbor not in visited or depth + 1 < visited[neighbor]:
                    visited[neighbor] = depth + 1
                    downstream.add(neighbor)
                    queue.append((neighbor, depth + 1))

        return list(downstream)

    def get_upstream(self, entity_id: str, max_depth: int = 3) -> list[str]:
        """
        Get all services that call entity_id (dependents / callers).
        Path: caller -> entity_id.
        """
        if entity_id not in self.graph:
            return []

        upstream = set()
        visited = {entity_id: 0}
        queue = [(entity_id, 0)]

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for neighbor in self.graph.predecessors(curr):
                if neighbor not in visited or depth + 1 < visited[neighbor]:
                    visited[neighbor] = depth + 1
                    upstream.add(neighbor)
                    queue.append((neighbor, depth + 1))

        return list(upstream)

    def find_path(self, source_id: str, target_id: str, max_depth: int = 3) -> list[str] | None:
        """Find shortest directed path from source_id to target_id within max_depth."""
        if source_id not in self.graph or target_id not in self.graph:
            return None

        try:
            path = nx.shortest_path(self.graph, source=source_id, target=target_id)
            if len(path) - 1 <= max_depth:
                return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        return None

    def find_relationship(self, entity_a: str, entity_b: str, max_depth: int = 3) -> tuple[str, list[str]] | None:
        """
        Find topological relationship between two entities.
        Returns:
            - ("downstream", path): entity_a calls entity_b (path from a to b)
            - ("upstream", path): entity_b calls entity_a (path from b to a)
            - None if no direct/multi-hop path within max_depth
        """
        # Check A -> B
        path_ab = self.find_path(entity_a, entity_b, max_depth)
        if path_ab:
            return ("downstream", path_ab)

        # Check B -> A
        path_ba = self.find_path(entity_b, entity_a, max_depth)
        if path_ba:
            return ("upstream", path_ba)

        return None
