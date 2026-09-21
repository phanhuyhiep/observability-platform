"""Slack Block Kit message builder and dispatcher."""

import logging
from typing import Any

import httpx

logger = logging.getLogger("rca.notification.slack")

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "warning": "🟡",
    "info": "🔵",
}


class SlackNotifier:
    """Formats and dispatches Slack Block Kit incident cards."""

    def build_payload(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str = "Unknown",
        confidence: float = 0.0,
        impacted_services: list[str] | None = None,
        estimated_user_impact: str = "low",
        grafana_url: str = "http://localhost:4000",
    ) -> dict[str, Any]:
        emoji = SEVERITY_EMOJI.get(severity.lower(), "⚪")
        impacted_str = ", ".join(impacted_services[:5]) if impacted_services else "None"
        if impacted_services and len(impacted_services) > 5:
            impacted_str += f" (+{len(impacted_services) - 5} more)"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Incident {incident_id} | {severity.upper()}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Root Cause:*\n`{root_cause}` ({confidence * 100:.0f}% confidence)",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*User Impact:*\n`{estimated_user_impact.upper()}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Impacted Services:*\n{impacted_str}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Dashboard:*\n<{grafana_url}|View Grafana>",
                    },
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Acknowledge"},
                        "style": "primary",
                        "value": f"ack_{incident_id}",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Investigate in Grafana",
                        },
                        "url": grafana_url,
                    },
                ],
            },
        ]
        return {"blocks": blocks}

    async def send(self, webhook_url: str, payload: dict[str, Any]) -> bool:
        """Send message via Slack incoming webhook."""
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(webhook_url, json=payload)
                if res.status_code == 200:
                    logger.info("Successfully sent Slack notification")
                    return True
                logger.warning(
                    "Slack webhook returned status %d: %s", res.status_code, res.text
                )
        except Exception as e:
            logger.error("Error sending Slack notification: %s", e)
        return False
