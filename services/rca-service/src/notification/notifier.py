"""Notification Coordinator: handles channel routing, deduplication, and persistence."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from src.config import NotificationConfig
from src.models import IncidentDetail
from src.notification.slack import SlackNotifier
from src.notification.telegram import TelegramNotifier

logger = logging.getLogger("rca.notification.coordinator")


class NotificationCoordinator:
    """Dispatches formatted alerts to Slack, Telegram, and audit logs."""

    def __init__(self, config: NotificationConfig, pool: asyncpg.Pool | None = None):
        self.config = config
        self.pool = pool
        self.slack = SlackNotifier()
        self.telegram = TelegramNotifier()
        self._last_sent: dict[str, dict[str, Any]] = {}
        self.dedup_delta = timedelta(minutes=config.dedup_window_minutes)

    def should_dispatch(self, incident: IncidentDetail) -> bool:
        """Check if notification should be sent or suppressed by deduplication."""
        last_info = self._last_sent.get(incident.incident_id)
        if not last_info:
            return True

        now = datetime.now(timezone.utc)
        last_ts = last_info["timestamp"]
        if now - last_ts < self.dedup_delta:
            # Check if severity or status escalated
            if (
                last_info["severity"] == incident.severity
                and last_info["status"] == incident.status
            ):
                return False

        return True

    async def dispatch(self, incident: IncidentDetail) -> dict[str, Any]:
        """Format and send notification across configured channels."""
        if not self.should_dispatch(incident):
            logger.debug("Suppressed duplicate notification for %s", incident.incident_id)
            return {"status": "deduplicated", "channels": []}

        root_cause = "Unknown"
        confidence = 0.0
        if incident.root_causes:
            top = incident.root_causes[0]
            root_cause = top.entity_id
            confidence = top.confidence

        user_impact = incident.blast_radius.estimated_user_impact if incident.blast_radius else "low"
        dispatched_channels = []

        # 1. Slack
        slack_payload = self.slack.build_payload(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity,
            root_cause=root_cause,
            confidence=confidence,
            impacted_services=incident.impacted_entities,
            estimated_user_impact=user_impact,
        )

        if self.config.slack_webhook_url:
            ok = await self.slack.send(self.config.slack_webhook_url, slack_payload)
            if ok:
                dispatched_channels.append("slack")
                await self._record_history(incident.incident_id, "slack", "sent", slack_payload)
        else:
            logger.info("[MOCK SLACK ALERT] %s: %s (Root cause: %s, %s)", incident.incident_id, incident.title, root_cause, incident.severity)
            dispatched_channels.append("slack_mock")
            await self._record_history(incident.incident_id, "slack", "mocked", slack_payload)

        # 2. Telegram
        tg_text = self.telegram.build_message(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity,
            root_cause=root_cause,
            confidence=confidence,
            impacted_services=incident.impacted_entities,
            estimated_user_impact=user_impact,
        )

        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            ok = await self.telegram.send(self.config.telegram_bot_token, self.config.telegram_chat_id, tg_text)
            if ok:
                dispatched_channels.append("telegram")
                await self._record_history(incident.incident_id, "telegram", "sent", {"text": tg_text})
        else:
            logger.info("[MOCK TELEGRAM ALERT] %s: %s (Root: %s)", incident.incident_id, incident.title, root_cause)
            dispatched_channels.append("telegram_mock")
            await self._record_history(incident.incident_id, "telegram", "mocked", {"text": tg_text})

        # Update deduplication cache
        self._last_sent[incident.incident_id] = {
            "timestamp": datetime.now(timezone.utc),
            "severity": incident.severity,
            "status": incident.status,
            "root_cause": root_cause,
        }

        return {"status": "dispatched", "channels": dispatched_channels}

    async def _record_history(self, incident_id: str, channel: str, status: str, payload: dict[str, Any]) -> None:
        """Persist notification record into PostgreSQL."""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_history (incident_id, timestamp, channel, status, payload)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    incident_id,
                    datetime.now(timezone.utc),
                    channel,
                    status,
                    json.dumps(payload),
                )
        except Exception as e:
            logger.error("Failed to record notification history: %s", e)
