"""Investigation recommendation engine generating actionable remediation commands."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from ..models import InvestigationStep

logger = logging.getLogger("ai.llm.recommender")

RUNBOOK_CATALOG = {
    "redis": {
        "name": "Redis Crash & Cache Unavailability Runbook",
        "url": "https://github.com/phanhuyhiep/observability-platform/blob/main/docs/runbooks/redis-troubleshooting.md",
        "steps": [
            {
                "action": "Xác nhận trạng thái Pod redis-cart",
                "command": "kubectl get pods -l app=redis-cart -n default",
                "reasoning": "Kiểm tra xem pod có ở trạng thái CrashLoopBackOff, OOMKilled hay bị scale về 0.",
            },
            {
                "action": "Soi log lỗi của dịch vụ CartService phụ thuộc",
                "command": "kubectl logs -l app=cartservice --tail=50",
                "reasoning": "CartService là client trực tiếp; log sẽ chỉ ra địa chỉ Redis hoặc socket connection timeout.",
            },
            {
                "action": "Khôi phục Replicas nếu pod bị scale 0",
                "command": "kubectl scale deployment/redis-cart --replicas=1",
                "reasoning": "Đưa instance redis-cart hoạt động trở lại để giải phóng hàng đợi request.",
            },
            {
                "action": "Kiểm tra độ trễ mạng và TCP connection tới Redis",
                "command": "kubectl exec deployment/cartservice -- nc -zv redis-cart 6379",
                "reasoning": "Xác nhận kết nối mạng tầng 4 (TCP handshake) giữa cartservice và redis-cart đã thông.",
            },
        ],
    },
    "cartservice": {
        "name": "CartService Exception & Rollout Failure Runbook",
        "url": "https://github.com/phanhuyhiep/observability-platform/blob/main/docs/runbooks/cartservice-troubleshooting.md",
        "steps": [
            {
                "action": "Kiểm tra biến môi trường REDIS_ADDR",
                "command": "kubectl describe deployment/cartservice | grep -A 5 Environment",
                "reasoning": "Xác nhận cấu hình kết nối Redis không bị sai địa chỉ host hoặc port.",
            },
            {
                "action": "Kiểm tra log gần nhất xem có StackTrace hay không",
                "command": "kubectl logs -l app=cartservice --tail=100 | grep -i Exception",
                "reasoning": "Phân tích nguyên nhân Exception từ mã nguồn hoặc thư viện client.",
            },
            {
                "action": "Khởi động lại Pod cartservice (Graceful Restart)",
                "command": "kubectl rollout restart deployment/cartservice -n default",
                "reasoning": "Xóa sạch các thread pool bị tắc nghẽn hoặc socket bị treo.",
            },
        ],
    },
    "loadgenerator": {
        "name": "Traffic Surge & Load Generator Runbook",
        "url": "https://github.com/phanhuyhiep/observability-platform/blob/main/docs/runbooks/traffic-surge.md",
        "steps": [
            {
                "action": "Kiểm tra số lượng replicas của loadgenerator",
                "command": "kubectl get deployment/loadgenerator -o jsonpath='{.spec.replicas}'",
                "reasoning": "Xác định xem có đợt scale đột biến bất thường do test tải hay không.",
            },
            {
                "action": "Giảm tải về mức an toàn",
                "command": "kubectl scale deployment/loadgenerator --replicas=1",
                "reasoning": "Hạ lưu lượng truy cập để các service hạ lưu giải phóng CPU và hàng đợi request.",
            },
        ],
    },
    "default": {
        "name": "Microservices General Incident Runbook",
        "url": "https://github.com/phanhuyhiep/observability-platform/blob/main/docs/runbooks/general-incident.md",
        "steps": [
            {
                "action": "Kiểm tra tài nguyên CPU/RAM trên Kubernetes Node",
                "command": "kubectl top nodes && kubectl top pods -A",
                "reasoning": "Đảm bảo cluster không bị cạn kiệt tài nguyên phần cứng làm pod bị throttling.",
            },
            {
                "action": "Soi Trace phân tán trên Grafana Tempo",
                "command": "Mở Grafana -> Explore -> Tempo -> Lọc theo service gây lỗi",
                "reasoning": "Quan sát waterfall trace để định vị chính xác span gây nghẽn.",
            },
            {
                "action": "Đóng sự cố trên SRE Operations CLI",
                "command": "python3 scripts/sre_ops.py --resolve {incident_id}",
                "reasoning": "Ghi nhận sự cố đã được khắc phục và tính toán thời gian phục hồi MTTR.",
            },
        ],
    },
}


class InvestigationRecommender:
    """Generates ordered action steps and runbooks based on incident root causes."""

    def __init__(self, pool: asyncpg.Pool | None = None):
        self.pool = pool

    def generate_recommendations(
        self,
        incident_id: str,
        root_cause: str,
    ) -> list[InvestigationStep]:
        """Produce concrete, ordered investigation actions."""
        target_catalog = RUNBOOK_CATALOG["default"]
        for key in RUNBOOK_CATALOG:
            if key != "default" and key in root_cause.lower():
                target_catalog = RUNBOOK_CATALOG[key]
                break

        steps: list[InvestigationStep] = []
        for i, s in enumerate(target_catalog["steps"], start=1):
            cmd = s["command"].replace("{incident_id}", incident_id) if s.get("command") else None
            steps.append(
                InvestigationStep(
                    step_order=i,
                    action_title=s["action"],
                    command=cmd,
                    reasoning=s["reasoning"],
                    runbook_url=target_catalog["url"],
                )
            )

        return steps

    def get_matched_runbooks(self, root_cause: str) -> list[dict[str, str]]:
        """Return matching runbook documents."""
        matched = []
        for key, rb in RUNBOOK_CATALOG.items():
            if key in root_cause.lower() or key == "default":
                matched.append({"name": rb["name"], "url": rb["url"]})
        return matched

    async def persist_recommendations(self, incident_id: str, steps: list[InvestigationStep]) -> None:
        """Save steps to database."""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                for s in steps:
                    await conn.execute(
                        """
                        INSERT INTO ai_investigation_recommendations (
                            incident_id, step_order, action_title, command, reasoning, runbook_url
                        ) VALUES ($1, $2, $3, $4, $5, $6);
                        """,
                        incident_id,
                        s.step_order,
                        s.action_title,
                        s.command,
                        s.reasoning,
                        s.runbook_url,
                    )
        except Exception as e:
            logger.warning("Could not persist recommendations: %s", e)
