"""Detection orchestrator – coordinates feature extraction and detection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import asyncpg

from .config import AppConfig
from .models import AnomalyContext, AnomalyDetection, AnomalyEntity, AnomalyEvent, AnomalyValues
from .query.prometheus_client import PrometheusClient
from .query.loki_client import LokiClient
from .features.metric_features import compute_metric_features
from .features.log_features import compute_log_features
from .baseline.calculator import BaselineCalculator, BaselineStorage
from .detectors.rule_detector import RuleDetector
from .detectors.zscore_detector import ZScoreDetector
from .detectors.ewma_detector import EWMADetector

logger = logging.getLogger(__name__)


class DetectionOrchestrator:
    """Orchestrates the detection loop: discover → extract → detect → store."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.prom = PrometheusClient(config.prometheus.url)
        self.loki = LokiClient(config.loki.url)

        # Baseline
        self.baseline_storage = BaselineStorage(config.storage.database_url)
        self.baseline_calculator = BaselineCalculator(self.baseline_storage)

        # Detectors
        self.rule_detector = RuleDetector(config.detectors.rule.rules_path)
        self.zscore_detector = ZScoreDetector(
            warning_threshold=config.detectors.zscore.thresholds.warning,
            high_threshold=config.detectors.zscore.thresholds.high,
            critical_threshold=config.detectors.zscore.thresholds.critical,
        )
        self.ewma_detector = EWMADetector(
            alpha=config.detectors.ewma.alpha,
            warning_k=config.detectors.ewma.thresholds.warning,
            high_k=config.detectors.ewma.thresholds.high,
            critical_k=config.detectors.ewma.thresholds.critical,
        )

        self._db_pool: asyncpg.Pool | None = None
        self._active_anomalies: dict[str, AnomalyEvent] = {}

    async def initialize(self) -> None:
        """Initialize database connections."""
        await self.baseline_storage.connect()
        self._db_pool = await asyncpg.create_pool(
            self.config.storage.database_url, min_size=2, max_size=10
        )
        logger.info("Detection orchestrator initialized")

    async def shutdown(self) -> None:
        """Cleanup connections."""
        await self.baseline_storage.close()
        if self._db_pool:
            await self._db_pool.close()

    async def run_detection_cycle(self) -> list[AnomalyEvent]:
        """Execute one full detection cycle.

        1. Discover services
        2. For each service: extract features, run detectors
        3. Deduplicate and store anomaly events
        """
        namespace = self.config.detection.namespace
        logger.info("Starting detection cycle for namespace: %s", namespace)

        # 1. Discover services
        services = await self.prom.discover_services(namespace)
        if not services:
            logger.warning("No services discovered in namespace: %s", namespace)
            return []

        logger.info("Discovered %d services: %s", len(services), services)

        all_anomalies: list[AnomalyEvent] = []

        # 2. Process each service
        for service in services:
            try:
                anomalies = await self._process_service(service, namespace)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.error("Error processing service %s: %s", service, e, exc_info=True)

        # 3. Store anomalies
        for anomaly in all_anomalies:
            if not self._is_duplicate(anomaly):
                await self._store_anomaly(anomaly)
                self._active_anomalies[self._anomaly_key(anomaly)] = anomaly

        # 4. Resolve expired anomalies
        await self._resolve_expired()

        logger.info(
            "Detection cycle complete: %d anomalies detected", len(all_anomalies)
        )
        return all_anomalies

    async def _process_service(
        self, service: str, namespace: str
    ) -> list[AnomalyEvent]:
        """Process a single service: extract features and run detectors."""
        anomalies: list[AnomalyEvent] = []

        # Define metrics to check for this service
        metrics_queries = {
            "cpu_usage_percent": (
                f'100 * sum(rate(container_cpu_usage_seconds_total'
                f'{{namespace="{namespace}", pod=~"{service}.*"}}[5m])) / '
                f'sum(kube_pod_container_resource_limits{{namespace="{namespace}", '
                f'pod=~"{service}.*", resource="cpu"}})'
            ),
            "memory_usage_percent": (
                f'100 * sum(container_memory_working_set_bytes'
                f'{{namespace="{namespace}", pod=~"{service}.*"}}) / '
                f'sum(kube_pod_container_resource_limits{{namespace="{namespace}", '
                f'pod=~"{service}.*", resource="memory"}})'
            ),
            "pod_restart_count": (
                f'sum(kube_pod_container_status_restarts_total'
                f'{{namespace="{namespace}", pod=~"{service}.*"}})'
            ),
        }

        for metric, query in metrics_queries.items():
            try:
                # Get current values
                values = await self.prom.get_metric_values(query, window_minutes=5)
                if not values:
                    continue

                # Get baseline
                baseline = await self.baseline_storage.get_baseline(
                    "service", service, metric, namespace
                )

                # Compute features
                feature_vector = compute_metric_features(
                    values=values,
                    entity_type="service",
                    entity_id=service,
                    metric=metric,
                    baseline_mean=baseline.mean if baseline else None,
                    baseline_std=baseline.std if baseline else None,
                    baseline_window=baseline.window if baseline else None,
                )

                # Run detectors
                anomalies.extend(
                    self._run_detectors(feature_vector, service, namespace, metric)
                )

            except Exception as e:
                logger.error(
                    "Error processing metric %s for service %s: %s",
                    metric, service, e,
                )

        # Log features (error count)
        try:
            error_count = await self.loki.get_error_count(service, namespace)
            burst_rate = await self.loki.get_log_burst_rate(service, namespace)

            baseline = await self.baseline_storage.get_baseline(
                "service", service, "error_count", namespace
            )

            feature_vector = compute_log_features(
                error_count=error_count,
                burst_rate=burst_rate,
                entity_type="service",
                entity_id=service,
                baseline_mean=baseline.mean if baseline else None,
                baseline_std=baseline.std if baseline else None,
                baseline_window=baseline.window if baseline else None,
            )

            anomalies.extend(
                self._run_detectors(feature_vector, service, namespace, "error_count")
            )
        except Exception as e:
            logger.error("Error processing logs for service %s: %s", service, e)

        return anomalies

    def _run_detectors(
        self, feature_vector, service: str, namespace: str, metric: str
    ) -> list[AnomalyEvent]:
        """Run all enabled detectors on a feature vector."""
        anomalies: list[AnomalyEvent] = []

        # Rule detector
        if self.config.detectors.rule.enabled:
            rule_results = self.rule_detector.evaluate(feature_vector)
            for result in rule_results:
                if result.is_anomaly:
                    anomalies.append(
                        self._create_anomaly_event(
                            feature_vector, result, service, namespace
                        )
                    )

        # Z-Score detector
        if self.config.detectors.zscore.enabled:
            zscore_result = self.zscore_detector.evaluate(feature_vector)
            if zscore_result.is_anomaly:
                anomalies.append(
                    self._create_anomaly_event(
                        feature_vector, zscore_result, service, namespace
                    )
                )

        # EWMA detector
        if self.config.detectors.ewma.enabled:
            ewma_result = self.ewma_detector.evaluate(feature_vector)
            if ewma_result.is_anomaly:
                anomalies.append(
                    self._create_anomaly_event(
                        feature_vector, ewma_result, service, namespace
                    )
                )

        return anomalies

    def _create_anomaly_event(
        self, feature_vector, result, service: str, namespace: str
    ) -> AnomalyEvent:
        """Create a standardized AnomalyEvent from a detector result."""
        return AnomalyEvent(
            timestamp=feature_vector.timestamp,
            entity=AnomalyEntity(
                type=feature_vector.entity_type,
                id=service,
                namespace=namespace,
            ),
            detection=AnomalyDetection(
                detector=result.detector,
                category=result.details.get("category", feature_vector.metric),
                signal=feature_vector.metric,
                severity=result.severity or "warning",
                score=result.score,
                confidence=result.confidence,
            ),
            values=AnomalyValues(
                current=feature_vector.current_value,
                baseline_mean=feature_vector.features.baseline_mean,
                baseline_std=feature_vector.features.baseline_std,
                z_score=result.details.get("z_score"),
                threshold_used=result.details.get("threshold"),
            ),
            context=AnomalyContext(
                window=feature_vector.window,
                baseline_window=feature_vector.features.baseline_window,
                rule_id=result.details.get("rule_id"),
            ),
            metadata={"labels": result.details},
        )

    def _anomaly_key(self, anomaly: AnomalyEvent) -> str:
        """Generate deduplication key for an anomaly."""
        return f"{anomaly.entity.id}:{anomaly.detection.signal}:{anomaly.detection.detector}"

    def _is_duplicate(self, anomaly: AnomalyEvent) -> bool:
        """Check if an equivalent anomaly is already active."""
        key = self._anomaly_key(anomaly)
        if key in self._active_anomalies:
            existing = self._active_anomalies[key]
            # Duplicate if within deduplication window (default 15 minutes)
            age = (anomaly.detected_at - existing.detected_at).total_seconds()
            window_seconds = self._parse_duration(self.config.deduplication.window)
            return age < window_seconds
        return False

    async def _store_anomaly(self, anomaly: AnomalyEvent) -> None:
        """Persist anomaly event to PostgreSQL."""
        if not self._db_pool:
            return

        try:
            await self._db_pool.execute(
                """
                INSERT INTO anomaly_events (
                    anomaly_id, version, timestamp, detected_at,
                    entity_type, entity_id, namespace,
                    detector, category, signal, severity, score, confidence,
                    current_value, baseline_mean, baseline_std, z_score,
                    rule_id, time_window, baseline_window,
                    status, metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
                )
                """,
                anomaly.anomaly_id,
                anomaly.version,
                anomaly.timestamp,
                anomaly.detected_at,
                anomaly.entity.type,
                anomaly.entity.id,
                anomaly.entity.namespace,
                anomaly.detection.detector,
                anomaly.detection.category,
                anomaly.detection.signal,
                anomaly.detection.severity,
                anomaly.detection.score,
                anomaly.detection.confidence,
                anomaly.values.current,
                anomaly.values.baseline_mean,
                anomaly.values.baseline_std,
                anomaly.values.z_score,
                anomaly.context.rule_id,
                anomaly.context.window,
                anomaly.context.baseline_window,
                anomaly.status,
                "{}",  # metadata as JSON string
            )
            logger.info(
                "Stored anomaly: %s [%s] %s → %s",
                anomaly.entity.id,
                anomaly.detection.signal,
                anomaly.detection.detector,
                anomaly.detection.severity,
            )
        except Exception as e:
            logger.error("Failed to store anomaly: %s", e)

    async def _resolve_expired(self) -> None:
        """Mark anomalies as resolved if they've been normal long enough."""
        resolution_seconds = self._parse_duration(
            self.config.deduplication.resolution_window
        )
        now = datetime.utcnow()

        keys_to_remove = []
        for key, anomaly in self._active_anomalies.items():
            age = (now - anomaly.detected_at).total_seconds()
            if age > resolution_seconds:
                keys_to_remove.append(key)
                if self._db_pool:
                    await self._db_pool.execute(
                        """
                        UPDATE anomaly_events SET status = 'resolved', resolved_at = now()
                        WHERE anomaly_id = $1
                        """,
                        anomaly.anomaly_id,
                    )

        for key in keys_to_remove:
            del self._active_anomalies[key]

    @staticmethod
    def _parse_duration(duration: str) -> int:
        """Parse duration string (e.g., '15m', '1h', '7d') to seconds."""
        if not duration:
            return 0
        unit = duration[-1]
        value = int(duration[:-1])
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return value * multipliers.get(unit, 60)
