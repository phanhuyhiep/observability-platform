"""Incident summarization engine producing natural-language RCA reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .client import LLMClient
from ..models import IncidentSummaryResponse

logger = logging.getLogger("ai.llm.summarizer")

SYSTEM_PROMPT = """You are an expert SRE (Site Reliability Engineer) AI Copilot specializing in Kubernetes microservices observability.
Your goal is to synthesize incident telemetry (metrics, root causes, blast radius, and logs) into a clear, executive-grade Root Cause Analysis (RCA) summary.
Keep your response concise, professional, actionable, and structured with:
1. Executive Overview
2. Root Cause Technical Explanation
3. Immediate Suggested Actions
"""


class IncidentSummarizer:
    """Generates and caches AI-driven Root Cause Analysis narratives."""

    def __init__(self, llm_client: LLMClient, pool: asyncpg.Pool | None = None):
        self.llm_client = llm_client
        self.pool = pool
        self._cache: dict[str, IncidentSummaryResponse] = {}

    async def summarize(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str,
        confidence: float,
        impacted_services: list[str],
        blast_radius: dict[str, Any] | None = None,
        anomalies: list[dict[str, Any]] | None = None,
        force_regenerate: bool = False,
    ) -> IncidentSummaryResponse:
        """Generate or retrieve cached natural-language RCA summary."""
        if not force_regenerate and incident_id in self._cache:
            return self._cache[incident_id]

        # Check DB cache
        if not force_regenerate and self.pool:
            db_summary = await self._load_from_db(incident_id)
            if db_summary:
                self._cache[incident_id] = db_summary
                return db_summary

        # Build prompt
        user_prompt = self._build_prompt(
            incident_id=incident_id,
            title=title,
            severity=severity,
            root_cause=root_cause,
            confidence=confidence,
            impacted_services=impacted_services,
            blast_radius=blast_radius,
            anomalies=anomalies,
        )

        raw_output, provider, tokens = await self.llm_client.generate(SYSTEM_PROMPT, user_prompt)

        # Parse output into structured fields
        if provider == "sre_expert":
            summary = self._generate_sre_expert_summary(
                incident_id=incident_id,
                title=title,
                severity=severity,
                root_cause=root_cause,
                confidence=confidence,
                impacted_services=impacted_services,
                blast_radius=blast_radius,
            )
        else:
            summary = self._parse_llm_output(
                incident_id=incident_id,
                raw_text=raw_output,
                provider=provider,
                tokens=tokens,
                root_cause=root_cause,
            )

        self._cache[incident_id] = summary

        # Persist to DB
        if self.pool:
            await self._save_to_db(summary)

        return summary

    def _build_prompt(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str,
        confidence: float,
        impacted_services: list[str],
        blast_radius: dict[str, Any] | None,
        anomalies: list[dict[str, Any]] | None,
    ) -> str:
        user_impact = blast_radius.get("estimated_user_impact", "high") if blast_radius else "high"
        direct = blast_radius.get("direct_impact", []) if blast_radius else []
        indirect = blast_radius.get("indirect_impact", []) if blast_radius else []

        return f"""Analyze incident {incident_id}:
- Title: {title}
- Severity: {severity.upper()}
- Predicted Root Cause: {root_cause} (Confidence: {confidence * 100:.0f}%)
- Impacted Services: {', '.join(impacted_services)}
- Direct Downstream: {', '.join(direct) if direct else 'None'}
- Indirect Downstream: {', '.join(indirect) if indirect else 'None'}
- Estimated User Impact: {user_impact.upper()}
- Anomaly Count: {len(anomalies) if anomalies else len(impacted_services)}

Provide:
1. Executive Overview (2-3 sentences)
2. Root Cause Technical Explanation
3. 3-4 Specific Bulleted Remediation Actions
"""

    def _generate_sre_expert_summary(
        self,
        incident_id: str,
        title: str,
        severity: str,
        root_cause: str,
        confidence: float,
        impacted_services: list[str],
        blast_radius: dict[str, Any] | None,
    ) -> IncidentSummaryResponse:
        """Domain-expert template generation for deterministic SRE reports."""
        user_impact = (blast_radius.get("estimated_user_impact") if blast_radius else "CRITICAL").upper()
        conf_pct = int(confidence * 100)
        impact_str = ", ".join(impacted_services) if impacted_services else "services"

        if "redis" in root_cause.lower():
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) bắt nguồn từ việc cụm in-memory cache/database '{root_cause}' "
                f"bị gián đoạn hoặc sập hoàn toàn. Tình trạng này đã kéo theo chuỗi sụp đổ domino (cascading failure) "
                f"lên các dịch vụ phụ thuộc: {impact_str}, gây ảnh hưởng nghiêm trọng tới trải nghiệm người dùng ({user_impact})."
            )
            explanation = (
                f"Dịch vụ '{root_cause}' là leaf dependency quan trọng. Khi nó không phản hồi, cartservice liên tục văng "
                f"ConnectionTimeoutException và mất kết nối socket. Lỗi này lập tức lan truyền ngược dòng lên frontend, "
                f"khiến tỷ lệ HTTP 500 error rate tăng vọt và làm tê liệt giỏ hàng/thanh toán."
            )
            actions = [
                f"Kiểm tra trạng thái pod: kubectl get pods -l app={root_cause} -n default",
                f"Xem log lỗi của dịch vụ phụ thuộc: kubectl logs -l app=cartservice --tail=50",
                f"Scale phục hồi pod redis-cart: kubectl scale deployment/{root_cause} --replicas=1",
                f"Soi trace phân tán trong Grafana Tempo để xác nhận không còn HTTP 500",
            ]
        elif "cart" in root_cause.lower():
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) phát sinh từ vi dịch vụ trung tâm '{root_cause}'. "
                f"Lỗi logic hoặc cấu hình sai đã làm suy giảm nghiêm trọng khả năng xử lý giỏ hàng, lan truyền lỗi ngược dòng lên {impact_str} "
                f"với mức độ tác động người dùng: {user_impact}."
            )
            explanation = (
                f"Dịch vụ '{root_cause}' gặp lỗi cấu hình kết nối (REDIS_ADDR sai) hoặc cạn kiệt thread pool kết nối. "
                f"Bản rollout gần nhất đã đưa cấu hình bất thường vào runtime, khiến các lời gọi gRPC GetCart/AddItem thất bại liên tục."
            )
            actions = [
                f"Kiểm tra cấu hình biến môi trường: kubectl describe deployment/{root_cause} | grep -A 5 Environment",
                f"Xem stack trace lỗi: kubectl logs -l app={root_cause} --tail=100 | grep -i Exception",
                f"Thực hiện rollback hoặc graceful restart: kubectl rollout restart deployment/{root_cause} -n default",
                f"Soi trace phân tán trên Grafana Tempo để xác nhận độ trễ giảm về mức an toàn",
            ]
        elif "loadgenerator" in root_cause.lower():
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) do hiện tượng quá tải lưu lượng đột biến xuất phát từ '{root_cause}'. "
                f"Lưu lượng tăng vọt đã tạo nghẽn cổ chai (traffic spike) trên các dịch vụ hạ lưu: {impact_str} ({user_impact})."
            )
            explanation = (
                f"Lượng request throughput trên '{root_cause}' tăng đột biến gấp nhiều lần mức baseline thông thường. "
                f"Các dịch vụ hạ lưu (frontend, cartservice, adservice) bị cạn kiệt connection pool và bão hòa CPU/RAM dẫn tới tăng vọt độ trễ p95."
            )
            actions = [
                f"Kiểm tra số lượng replica loadgenerator: kubectl get deployment/{root_cause} -o jsonpath='{{.spec.replicas}}'",
                f"Hạ tải về ngưỡng an toàn: kubectl scale deployment/{root_cause} --replicas=1",
                f"Theo dõi biểu đồ p95 latency và error rate trên Grafana Dashboard",
                f"Đóng sự cố sau khi lưu lượng ổn định: python3 scripts/sre_ops.py --resolve {incident_id}",
            ]
        elif "checkout" in root_cause.lower():
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) xảy ra tại trung tâm thanh toán & đơn hàng '{root_cause}'. "
                f"Quy trình thanh toán (Checkout Pipeline) bị tê liệt, ảnh hưởng trực tiếp tới giao dịch mua sắm của người dùng: {user_impact}."
            )
            explanation = (
                f"Dịch vụ '{root_cause}' là nút giao thoa phức tạp gọi đồng thời emailservice, paymentservice, shippingservice và cartservice. "
                f"Sự cố tắc nghẽn gRPC hoặc lỗi xác thực thanh toán đã gây dồn ứ request tại hàng đợi checkout."
            )
            actions = [
                f"Kiểm tra nhật ký giao dịch thanh toán: kubectl logs -l app={root_cause} --tail=100",
                f"Kiểm tra tính sẵn sàng của paymentservice: kubectl get pods -l app=paymentservice",
                f"Kiểm tra gRPC error rate trên Grafana Service Mesh dashboard",
                f"Xác nhận đơn hàng mẫu sau khi khắc phục để kiểm tra tính toàn vẹn hệ thống",
            ]
        elif "frontend" in root_cause.lower():
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) phát sinh tại cổng giao tiếp Ingress/Frontend '{root_cause}'. "
                f"Giao diện người dùng bị gián đoạn hoặc tỷ lệ HTTP 500 tăng cao, ảnh hưởng trực tiếp tới toàn bộ người dùng ({user_impact})."
            )
            explanation = (
                f"Frontend gateway bị quá tải worker threads hoặc gặp lỗi kết nối tới các dịch vụ backend hạ tầng. "
                f"Người dùng truy cập trang chủ gặp màn hình lỗi hoặc thời gian tải trang vượt ngưỡng timeout chuẩn."
            )
            actions = [
                f"Kiểm tra log lỗi HTTP 500: kubectl logs -l app={root_cause} --tail=100 | grep -E '500|Error'",
                f"Kiểm tra kết nối mạng nội bộ: kubectl exec deployment/{root_cause} -- wget -qO- http://localhost:8080",
                f"Khởi động lại frontend pods: kubectl rollout restart deployment/{root_cause} -n default",
                f"Xác nhận lại trạng thái hoạt động trên trình duyệt: http://172.16.20.26:8888",
            ]
        else:
            overview = (
                f"Sự cố {incident_id} ({severity.upper()}) được phát hiện với nguyên nhân gốc tiềm tàng là '{root_cause}' "
                f"(độ tin cậy {conf_pct}%). Sự cố đã lan truyền và ảnh hưởng tới các dịch vụ: {impact_str}, "
                f"với mức độ tác động người dùng: {user_impact}."
            )
            explanation = (
                f"Thuật toán phân tích đồ thị quan hệ dịch vụ (Topology & Temporal Scoring) xác định '{root_cause}' "
                f"có thời điểm phát sinh bất thường sớm nhất và đứng ở vị trí thượng nguồn (upstream-most) của chuỗi lan truyền lỗi."
            )
            actions = [
                f"Kiểm tra telemetry và CPU/RAM của {root_cause} trên Grafana",
                f"Kiểm tra nhật ký log lỗi: kubectl logs -l app={root_cause} --tail=100",
                f"Kiểm tra lịch sử rollout/deployment gần nhất của {root_cause}",
                f"Xác nhận trạng thái sau khi khắc phục bằng cách chạy: python3 scripts/sre_ops.py --resolve {incident_id}",
            ]

        full_text = f"### Tóm tắt sự cố {incident_id}\n\n**Tổng quan:** {overview}\n\n**Nguyên nhân gốc:** {explanation}\n\n**Hành động đề xuất:**\n" + "\n".join([f"- {a}" for a in actions])

        return IncidentSummaryResponse(
            incident_id=incident_id,
            provider="sre_expert",
            model_name="deterministic-sre-engine-v1",
            summary_text=full_text,
            root_cause_explanation=explanation,
            executive_overview=overview,
            suggested_actions=actions,
            tokens_used=len(full_text.split()),
            created_at=datetime.now(timezone.utc),
        )

    def _parse_llm_output(
        self,
        incident_id: str,
        raw_text: str,
        provider: str,
        tokens: int,
        root_cause: str,
    ) -> IncidentSummaryResponse:
        lines = raw_text.strip().split("\n")
        actions = []
        for line in lines:
            if line.strip().startswith(("-", "*", "1.", "2.", "3.", "4.")):
                clean_act = line.strip().lstrip("-*0123456789. ")
                if len(clean_act) > 5:
                    actions.append(clean_act)

        return IncidentSummaryResponse(
            incident_id=incident_id,
            provider=provider,
            model_name=self.llm_client.config.model,
            summary_text=raw_text,
            root_cause_explanation=f"AI determined root cause to be '{root_cause}' based on multi-signal evidence.",
            executive_overview=lines[0] if lines else raw_text[:200],
            suggested_actions=actions[:4],
            tokens_used=tokens,
            created_at=datetime.now(timezone.utc),
        )

    async def _load_from_db(self, incident_id: str) -> IncidentSummaryResponse | None:
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM incident_ai_summaries WHERE incident_id = $1 ORDER BY created_at DESC LIMIT 1",
                    incident_id,
                )
                if row:
                    acts = row["suggested_actions"]
                    if isinstance(acts, str):
                        acts = json.loads(acts)
                    return IncidentSummaryResponse(
                        incident_id=row["incident_id"],
                        provider=row["provider"],
                        model_name=row["model_name"],
                        summary_text=row["summary_text"],
                        root_cause_explanation=row["root_cause_explanation"],
                        executive_overview=row["executive_overview"] or "",
                        suggested_actions=acts or [],
                        tokens_used=row.get("tokens_used", 0),
                        created_at=row["created_at"],
                    )
        except Exception as e:
            logger.warning("Error loading summary from DB: %s", e)
        return None

    async def _save_to_db(self, summary: IncidentSummaryResponse) -> None:
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO incident_ai_summaries (
                        incident_id, provider, model_name, summary_text, root_cause_explanation,
                        suggested_actions, executive_overview, tokens_used
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8
                    ) ON CONFLICT (incident_id, provider) DO UPDATE SET
                        summary_text = EXCLUDED.summary_text,
                        root_cause_explanation = EXCLUDED.root_cause_explanation,
                        suggested_actions = EXCLUDED.suggested_actions,
                        updated_at = now();
                    """,
                    summary.incident_id,
                    summary.provider,
                    summary.model_name,
                    summary.summary_text,
                    summary.root_cause_explanation,
                    json.dumps(summary.suggested_actions),
                    summary.executive_overview,
                    summary.tokens_used,
                )
        except Exception as e:
            logger.warning("Error persisting summary to DB: %s", e)
