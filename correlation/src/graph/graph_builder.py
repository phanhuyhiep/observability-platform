"""Service Dependency Graph Builder from OpenTelemetry traces and seed metadata."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.graph.graph_storage import GraphStorage
from src.models import ServiceEdge, ServiceNode

logger = logging.getLogger("correlation.graph.builder")


class GraphBuilder:
    """Builds and enriches service dependency graph."""

    def __init__(self, storage: GraphStorage, tempo_url: str = "http://tempo.observability.svc.cluster.local:3200"):
        self.storage = storage
        self.tempo_url = tempo_url.rstrip("/")

    def seed_default_topology(self) -> None:
        """Seed default microservices-demo topology as baseline."""
        services = [
            ("frontend", "service"),
            ("cartservice", "service"),
            ("productcatalogservice", "service"),
            ("currencyservice", "service"),
            ("paymentservice", "service"),
            ("shippingservice", "service"),
            ("emailservice", "service"),
            ("checkoutservice", "service"),
            ("recommendationservice", "service"),
            ("adservice", "service"),
            ("redis-cart", "database"),
            ("detection-service", "service"),
            ("detection-postgres", "database"),
        ]

        for s_id, s_type in services:
            self.storage.add_node(
                ServiceNode(
                    node_id=s_id,
                    node_type=s_type,
                    namespace="default" if "detection" not in s_id else "observability",
                    metadata={"source": "seed_topology"},
                )
            )

        edges = [
            ("frontend", "cartservice", "grpc"),
            ("frontend", "productcatalogservice", "grpc"),
            ("frontend", "currencyservice", "grpc"),
            ("frontend", "recommendationservice", "grpc"),
            ("frontend", "shippingservice", "grpc"),
            ("frontend", "checkoutservice", "grpc"),
            ("frontend", "adservice", "grpc"),
            ("checkoutservice", "cartservice", "grpc"),
            ("checkoutservice", "productcatalogservice", "grpc"),
            ("checkoutservice", "currencyservice", "grpc"),
            ("checkoutservice", "paymentservice", "grpc"),
            ("checkoutservice", "shippingservice", "grpc"),
            ("checkoutservice", "emailservice", "grpc"),
            ("cartservice", "redis-cart", "database"),
            ("recommendationservice", "productcatalogservice", "grpc"),
            ("detection-service", "detection-postgres", "database"),
        ]

        for src, dst, dep_type in edges:
            self.storage.add_edge(
                ServiceEdge(
                    source_id=src,
                    target_id=dst,
                    dependency_type=dep_type,
                    discovered_by="seed_topology",
                    metadata={"protocol": dep_type},
                )
            )

        logger.info("Seeded default microservices-demo topology into graph storage")

    async def build_from_tempo(self, query_range_minutes: int = 60) -> int:
        """Query Tempo for recent traces and extract dependency edges."""
        edges_discovered = 0
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Search recent traces
                search_url = f"{self.tempo_url}/api/search"
                params = {"limit": 30}
                res = await client.get(search_url, params=params)

                if res.status_code != 200:
                    logger.warning("Tempo search returned status %d: %s", res.status_code, res.text)
                    return 0

                data = res.json()
                traces = data.get("traces", [])
                logger.info("Found %d recent traces in Tempo to analyze", len(traces))

                for trace_summary in traces:
                    trace_id = trace_summary.get("traceID")
                    if not trace_id:
                        continue

                    # 2. Get trace detail
                    trace_res = await client.get(f"{self.tempo_url}/api/traces/{trace_id}")
                    if trace_res.status_code == 200:
                        trace_data = trace_res.json()
                        edges_discovered += self._parse_spans_for_edges(trace_data)

        except httpx.ConnectError:
            logger.warning("Cannot connect to Tempo at %s. Using cached/seed graph.", self.tempo_url)
        except Exception as e:
            logger.error("Error building graph from Tempo: %s", e)

        return edges_discovered

    def _parse_spans_for_edges(self, trace_data: dict[str, Any]) -> int:
        """Extract parent-child service calls from spans."""
        # Handles both Jaeger JSON format and OTLP JSON format
        batches = trace_data.get("batches", [])
        spans_by_id = {}
        service_by_span = {}

        for batch in batches:
            resource = batch.get("resource", {})
            attributes = resource.get("attributes", [])
            service_name = "unknown"
            for attr in attributes:
                if attr.get("key") in ("service.name", "service_name"):
                    service_name = attr.get("value", {}).get("stringValue", "unknown")

            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    span_id = span.get("spanId")
                    spans_by_id[span_id] = span
                    service_by_span[span_id] = service_name

        count = 0
        for span_id, span in spans_by_id.items():
            parent_id = span.get("parentSpanId")
            if parent_id and parent_id in service_by_span:
                caller = service_by_span[parent_id]
                callee = service_by_span[span_id]
                if caller and callee and caller != callee and caller != "unknown" and callee != "unknown":
                    self.storage.add_edge(
                        ServiceEdge(
                            source_id=caller,
                            target_id=callee,
                            dependency_type="http",
                            discovered_by="otel_traces",
                        )
                    )
                    count += 1

        return count
