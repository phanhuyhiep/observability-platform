"""In-memory and PostgreSQL storage for Service Dependency Graph."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg
import networkx as nx

from src.models import ServiceEdge, ServiceNode

logger = logging.getLogger("correlation.graph.storage")


class GraphStorage:
    """Manages NetworkX in-memory representation and PostgreSQL persistence."""

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self._nodes_cache: dict[str, ServiceNode] = {}
        self._edges_cache: dict[tuple[str, str, str], ServiceEdge] = {}

    def add_node(self, node: ServiceNode) -> None:
        """Add or update a node in the graph."""
        now = datetime.now(timezone.utc)
        if node.first_seen is None:
            node.first_seen = now
        node.last_seen = now

        self._nodes_cache[node.node_id] = node
        self.graph.add_node(
            node.node_id,
            node_type=node.node_type,
            namespace=node.namespace,
            cluster=node.cluster,
            metadata=node.metadata,
            last_seen=node.last_seen,
        )

    def add_edge(self, edge: ServiceEdge) -> None:
        """Add or update a directed edge in the graph."""
        now = datetime.now(timezone.utc)
        if edge.first_seen is None:
            edge.first_seen = now
        edge.last_seen = now

        key = (edge.source_id, edge.target_id, edge.dependency_type)
        self._edges_cache[key] = edge

        # Ensure source and target nodes exist
        if edge.source_id not in self.graph:
            self.add_node(ServiceNode(node_id=edge.source_id, node_type="service"))
        if edge.target_id not in self.graph:
            # Check target type heuristic
            target_type = "database" if "postgres" in edge.target_id or "redis" in edge.target_id or "db" in edge.target_id else "service"
            self.add_node(ServiceNode(node_id=edge.target_id, node_type=target_type))

        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            dependency_type=edge.dependency_type,
            discovered_by=edge.discovered_by,
            metadata=edge.metadata,
            last_seen=edge.last_seen,
        )

    def remove_edge(self, source_id: str, target_id: str, dependency_type: str = "http") -> bool:
        """Remove an edge from memory cache and graph."""
        key = (source_id, target_id, dependency_type)
        if key in self._edges_cache:
            del self._edges_cache[key]
        if self.graph.has_edge(source_id, target_id):
            self.graph.remove_edge(source_id, target_id)
            return True
        return False

    def get_all_nodes(self) -> list[ServiceNode]:
        """Return all nodes in graph."""
        return list(self._nodes_cache.values())

    def get_all_edges(self) -> list[ServiceEdge]:
        """Return all edges in graph."""
        return list(self._edges_cache.values())

    async def load_from_db(self, pool: asyncpg.Pool) -> None:
        """Load graph nodes and edges from PostgreSQL into NetworkX."""
        try:
            async with pool.acquire() as conn:
                nodes_rows = await conn.fetch("SELECT * FROM service_graph_nodes")
                for row in nodes_rows:
                    meta = row["metadata"]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    node = ServiceNode(
                        node_id=row["node_id"],
                        node_type=row["node_type"],
                        namespace=row["namespace"],
                        cluster=row["cluster"],
                        metadata=meta or {},
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                    )
                    self.add_node(node)

                edges_rows = await conn.fetch("SELECT * FROM service_graph_edges")
                for row in edges_rows:
                    meta = row["metadata"]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    edge = ServiceEdge(
                        edge_id=str(row["edge_id"]),
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        dependency_type=row["dependency_type"],
                        discovered_by=row["discovered_by"],
                        metadata=meta or {},
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                    )
                    self.add_edge(edge)

            logger.info(
                "Loaded %d nodes and %d edges from DB",
                len(self._nodes_cache),
                len(self._edges_cache),
            )
        except Exception as e:
            logger.error("Failed to load graph from database: %s", e)

    async def sync_to_db(self, pool: asyncpg.Pool) -> None:
        """Persist in-memory nodes and edges to PostgreSQL."""
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for node in self._nodes_cache.values():
                        await conn.execute(
                            """
                            INSERT INTO service_graph_nodes (node_id, node_type, namespace, cluster, metadata, first_seen, last_seen)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (node_id) DO UPDATE SET
                                node_type = EXCLUDED.node_type,
                                metadata = EXCLUDED.metadata,
                                last_seen = EXCLUDED.last_seen;
                            """,
                            node.node_id,
                            node.node_type,
                            node.namespace,
                            node.cluster,
                            json.dumps(node.metadata),
                            node.first_seen,
                            node.last_seen,
                        )

                    for edge in self._edges_cache.values():
                        await conn.execute(
                            """
                            INSERT INTO service_graph_edges (source_id, target_id, dependency_type, metadata, discovered_by, first_seen, last_seen)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (source_id, target_id, dependency_type) DO UPDATE SET
                                metadata = EXCLUDED.metadata,
                                discovered_by = EXCLUDED.discovered_by,
                                last_seen = EXCLUDED.last_seen;
                            """,
                            edge.source_id,
                            edge.target_id,
                            edge.dependency_type,
                            json.dumps(edge.metadata),
                            edge.discovered_by,
                            edge.first_seen,
                            edge.last_seen,
                        )
            logger.debug("Successfully synced graph to PostgreSQL")
        except Exception as e:
            logger.error("Failed to sync graph to database: %s", e)
