"""Unit tests for Blast Radius Calculator."""

import networkx as nx
import pytest

from src.blast_radius.calculator import BlastRadiusCalculator


@pytest.fixture
def topology_graph():
    """Graph: frontend -> cartservice -> redis-cart
              frontend -> checkoutservice -> paymentservice
    """
    g = nx.DiGraph()
    g.add_edge("frontend", "cartservice")
    g.add_edge("cartservice", "redis-cart")
    g.add_edge("frontend", "checkoutservice")
    g.add_edge("checkoutservice", "paymentservice")
    return g


def test_blast_radius_from_leaf_database(topology_graph):
    calculator = BlastRadiusCalculator(user_facing_services=["frontend"])
    
    # redis-cart fails -> direct impact on cartservice, indirect impact on frontend
    blast = calculator.calculate("redis-cart", topology_graph)

    assert blast.root_entity == "redis-cart"
    assert "cartservice" in blast.direct_impact
    assert "frontend" in blast.indirect_impact
    assert blast.total_impacted >= 2
    assert "frontend" in blast.user_facing_services
    # Because user-facing service is indirectly impacted, impact is high
    assert blast.estimated_user_impact in ("high", "critical")


def test_blast_radius_from_intermediate_service(topology_graph):
    calculator = BlastRadiusCalculator(user_facing_services=["frontend"])
    
    # cartservice fails -> direct caller is frontend, downstream callee is redis-cart
    blast = calculator.calculate("cartservice", topology_graph)

    assert blast.root_entity == "cartservice"
    assert "frontend" in blast.direct_impact
    assert "redis-cart" in blast.direct_impact
    # Since frontend is in direct impact, estimated_user_impact is critical!
    assert blast.estimated_user_impact == "critical"


def test_blast_radius_unknown_entity(topology_graph):
    calculator = BlastRadiusCalculator()
    blast = calculator.calculate("unknown-service", topology_graph)

    assert blast.root_entity == "unknown-service"
    assert blast.total_impacted == 0
    assert blast.estimated_user_impact == "low"
