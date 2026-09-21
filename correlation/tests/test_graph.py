"""Unit tests for Service Dependency Graph and GraphQuery."""

from src.graph.graph_query import GraphQuery
from src.graph.graph_storage import GraphStorage
from src.models import ServiceEdge, ServiceNode


def setup_test_graph() -> GraphQuery:
    storage = GraphStorage()

    # Nodes: frontend -> checkoutservice -> paymentservice -> postgresql
    for s in ["frontend", "checkoutservice", "paymentservice", "postgresql"]:
        storage.add_node(ServiceNode(node_id=s))

    storage.add_edge(ServiceEdge(source_id="frontend", target_id="checkoutservice"))
    storage.add_edge(ServiceEdge(source_id="checkoutservice", target_id="paymentservice"))
    storage.add_edge(ServiceEdge(source_id="paymentservice", target_id="postgresql"))

    return GraphQuery(storage)


def test_downstream_query():
    query = setup_test_graph()
    downstream = query.get_downstream("frontend", max_depth=3)
    assert "checkoutservice" in downstream
    assert "paymentservice" in downstream
    assert "postgresql" in downstream


def test_upstream_query():
    query = setup_test_graph()
    upstream = query.get_upstream("postgresql", max_depth=3)
    assert "paymentservice" in upstream
    assert "checkoutservice" in upstream
    assert "frontend" in upstream


def test_find_path():
    query = setup_test_graph()
    path = query.find_path("frontend", "postgresql", max_depth=3)
    assert path == ["frontend", "checkoutservice", "paymentservice", "postgresql"]


def test_relationship_detection():
    query = setup_test_graph()
    # frontend calls paymentservice (indirectly)
    rel1 = query.find_relationship("frontend", "paymentservice")
    assert rel1 is not None
    direction, path = rel1
    assert direction == "downstream"
    assert path == ["frontend", "checkoutservice", "paymentservice"]

    # paymentservice is called by frontend
    rel2 = query.find_relationship("paymentservice", "frontend")
    assert rel2 is not None
    direction, path = rel2
    assert direction == "upstream"
    assert path == ["frontend", "checkoutservice", "paymentservice"]
