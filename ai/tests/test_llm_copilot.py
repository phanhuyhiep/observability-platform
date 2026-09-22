"""Unit tests for LLM Incident Copilot & Investigation Recommender."""

import pytest
from ai.src.config import LLMConfig
from ai.src.llm import (
    HistoricalSimilarityEngine,
    IncidentSummarizer,
    InvestigationRecommender,
    LLMClient,
)


@pytest.mark.asyncio
async def test_offline_sre_expert_summarizer():
    config = LLMConfig(provider="sre_expert")
    client = LLMClient(config)
    summarizer = IncidentSummarizer(llm_client=client)

    summary = await summarizer.summarize(
        incident_id="INC-999999",
        title="[redis-cart] critical crash cascading to cartservice, frontend",
        severity="CRITICAL",
        root_cause="redis-cart",
        confidence=0.95,
        impacted_services=["redis-cart", "cartservice", "frontend"],
        blast_radius={"estimated_user_impact": "critical", "direct_impact": ["cartservice"]},
    )

    assert summary.incident_id == "INC-999999"
    assert summary.provider == "sre_expert"
    assert "redis-cart" in summary.summary_text
    assert len(summary.suggested_actions) >= 3
    assert any("kubectl" in act for act in summary.suggested_actions)


def test_investigation_recommender_redis():
    recommender = InvestigationRecommender()
    steps = recommender.generate_recommendations("INC-1001", "redis-cart")

    assert len(steps) >= 3
    # Step order should be 1, 2, 3...
    assert [s.step_order for s in steps] == list(range(1, len(steps) + 1))
    # Should include kubectl commands
    assert any("kubectl" in (s.command or "") for s in steps)
    # Runbook URL should be present
    assert steps[0].runbook_url is not None


@pytest.mark.asyncio
async def test_similarity_engine():
    similarity = HistoricalSimilarityEngine()
    similar = await similarity.find_similar(
        current_incident_id="INC-123456",
        root_cause="redis-cart",
        impacted_entities=["redis-cart", "cartservice", "frontend"],
        severity="critical",
    )

    assert len(similar) > 0
    assert similar[0].similarity_score > 0.5
    assert similar[0].incident_id != "INC-123456"
