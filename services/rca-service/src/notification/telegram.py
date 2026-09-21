import html
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
    """Formats and dispatches Telegram HTML incident alerts."""

    def build_message(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str = "Unknown",
        confidence: float = 0.0,
        impacted_services: list[str] | None = None,
        estimated_user_impact: str = "low",
        grafana_url: str = "http://localhost:30300",
    ) -> str:
        emoji = SEVERITY_EMOJI.get(severity.lower(), "📢")
        impacted_str = ", ".join(impacted_services[:6]) if impacted_services else "None"
        if impacted_services and len(impacted_services) > 6:
            impacted_str += f" (+{len(impacted_services) - 6} more)"

        lines = [
            f"{emoji} <b>INCIDENT ALERT: {html.escape(incident_id)}</b>",
            f"<b>Severity:</b> <code>{html.escape(severity.upper())}</code>",
            f"<b>Summary:</b> {html.escape(title)}",
            "",
            f"🎯 <b>Root Cause:</b> <code>{html.escape(root_cause)}</code>",
            f"📊 <b>Confidence:</b> <code>{confidence * 100:.0f}%</code>",
            f"🌐 <b>User Impact:</b> <code>{html.escape(estimated_user_impact.upper())}</code>",
            f"🔗 <b>Impacted Services:</b> <code>{html.escape(impacted_str)}</code>",
            "",
            f"👉 <a href='{grafana_url}'>Open Incident Dashboard in Grafana</a>",
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
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    logger.info("Successfully sent Telegram notification to chat %s", chat_id)
                    return True
                logger.warning("Telegram API returned status %d: %s", res.status_code, res.text)
        except Exception as e:
            logger.error("Error sending Telegram notification: %s", e)
        return False
