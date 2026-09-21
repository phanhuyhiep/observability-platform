"""Unit tests for Notification Dispatcher, Slack, and Telegram formatters."""

from datetime import datetime, timezone
import pytest

from src.config import NotificationConfig
from src.models import BlastRadius, IncidentDetail, RootCauseCandidate, ScoreBreakdown
from src.notification.notifier import NotificationCoordinator
from src.notification.slack import SlackNotifier
from src.notification.telegram import TelegramNotifier


@pytest.fixture
def sample_incident():
    return IncidentDetail(
        incident_id="INC-1001",
        title="High latency on redis-cart cascading to cartservice",
        severity="critical",
        status="OPEN",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        impacted_entities=["redis-cart", "cartservice", "frontend"],
        root_causes=[
            RootCauseCandidate(
                rank=1,
                entity_id="redis-cart",
                description="Primary root cause",
                score=0.92,
                confidence=0.88,
                scores_breakdown=ScoreBreakdown(),
            )
        ],
        blast_radius=BlastRadius(
            root_entity="redis-cart",
            direct_impact=["cartservice"],
            indirect_impact=["frontend"],
            total_impacted=2,
            user_facing_services=["frontend"],
            estimated_user_impact="high",
        ),
    )


def test_slack_payload_builder():
    notifier = SlackNotifier()
    payload = notifier.build_payload(
        incident_id="INC-1001",
        title="Cascading latency test",
        severity="critical",
        root_cause="redis-cart",
        confidence=0.92,
        impacted_services=["redis-cart", "cartservice"],
        estimated_user_impact="high",
    )

    blocks = payload.get("blocks", [])
    assert len(blocks) == 4
    # Header block
    assert "INC-1001" in blocks[0]["text"]["text"]
    assert "CRITICAL" in blocks[0]["text"]["text"]
    # Section fields
    fields = blocks[2]["fields"]
    root_field = fields[0]["text"]
    assert "redis-cart" in root_field
    assert "92%" in root_field


def test_telegram_message_builder():
    notifier = TelegramNotifier()
    msg = notifier.build_message(
        incident_id="INC-1001",
        title="Cascading latency test",
        severity="critical",
        root_cause="redis-cart",
        confidence=0.85,
        impacted_services=["redis-cart", "cartservice"],
        estimated_user_impact="high",
    )

    assert "INCIDENT ALERT: INC-1001" in msg
    assert "CRITICAL" in msg
    assert "redis-cart" in msg
    assert "85%" in msg
    assert "HIGH" in msg


@pytest.mark.asyncio
async def test_notification_coordinator_dedup(sample_incident):
    config = NotificationConfig(
        enabled=True,
        slack_webhook_url=None,  # mock mode
        telegram_bot_token=None,
        telegram_chat_id=None,
        dedup_window_minutes=15,
    )
    coord = NotificationCoordinator(config=config)

    # First dispatch -> should dispatch (via mock)
    res1 = await coord.dispatch(sample_incident)
    assert res1["status"] == "dispatched"
    assert "slack_mock" in res1["channels"]
    assert "telegram_mock" in res1["channels"]

    # Immediate second dispatch without changes -> should be deduplicated
    res2 = await coord.dispatch(sample_incident)
    assert res2["status"] == "deduplicated"
    assert res2["channels"] == []

    # Severity escalation -> should bypass dedup
    sample_incident.severity = "high"
    res3 = await coord.dispatch(sample_incident)
    assert res3["status"] == "dispatched"
