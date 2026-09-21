"""Telegram Bot message builder and dispatcher."""

import logging

import httpx

logger = logging.getLogger("rca.notification.telegram")

SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "⚠️",
    "warning": "⚡",
    "info": "ℹ️",
}


class TelegramNotifier:
    """Formats and dispatches Telegram markdown incident alerts."""

    def build_message(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str = "Unknown",
        confidence: float = 0.0,
        impacted_services: list[str] | None = None,
        estimated_user_impact: str = "low",
    ) -> str:
        emoji = SEVERITY_EMOJI.get(severity.lower(), "📢")
        impacted_str = ", ".join(impacted_services[:5]) if impacted_services else "None"

        lines = [
            f"{emoji} *INCIDENT ALERT: {incident_id}*",
            f"*Severity:* `{severity.upper()}`",
            f"*Summary:* {title}",
            "",
            f"🎯 *Root Cause Candidate:* `{root_cause}`",
            f"📊 *Confidence:* `{confidence * 100:.0f}%`",
            f"🌐 *User Impact:* `{estimated_user_impact.upper()}`",
            f"🔗 *Impacted Services:* `{impacted_str}`",
            "",
            "👉 _Please acknowledge or investigate in Grafana._",
        ]
        return "\n".join(lines)

    async def send(self, bot_token: str, chat_id: str, message: str) -> bool:
        """Send message via Telegram Bot API."""
        if not bot_token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    logger.info("Successfully sent Telegram notification")
                    return True
                logger.warning("Telegram API returned status %d: %s", res.status_code, res.text)
        except Exception as e:
            logger.error("Error sending Telegram notification: %s", e)
        return False
