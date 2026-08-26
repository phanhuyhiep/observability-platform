"""Z-Score based anomaly detector."""

from __future__ import annotations

import logging

from ..models import DetectorResult, FeatureVector

logger = logging.getLogger(__name__)


class ZScoreDetector:
    """Detects anomalies when current value deviates significantly from baseline.

    z = (current - baseline_mean) / baseline_std

    Severity mapping:
        |z| > warning_threshold  → warning
        |z| > high_threshold     → high
        |z| > critical_threshold → critical
    """

    name = "z_score"

    def __init__(
        self,
        warning_threshold: float = 3.0,
        high_threshold: float = 5.0,
        critical_threshold: float = 10.0,
        min_data_points: int = 100,
    ):
        self.warning_threshold = warning_threshold
        self.high_threshold = high_threshold
        self.critical_threshold = critical_threshold
        self.min_data_points = min_data_points

    def evaluate(self, feature_vector: FeatureVector) -> DetectorResult:
        """Evaluate feature vector using Z-score against baseline."""
        features = feature_vector.features

        # Check prerequisites
        if features.baseline_mean is None or features.baseline_std is None:
            return DetectorResult(
                is_anomaly=False,
                detector=self.name,
                details={"reason": "no_baseline"},
            )

        if features.baseline_std == 0:
            # Constant metric – any deviation is anomalous
            if feature_vector.current_value != features.baseline_mean:
                return DetectorResult(
                    is_anomaly=True,
                    detector=self.name,
                    severity="warning",
                    score=0.5,
                    confidence=0.5,
                    details={
                        "reason": "constant_metric_deviation",
                        "z_score": None,
                        "current": feature_vector.current_value,
                        "baseline_mean": features.baseline_mean,
                    },
                )
            return DetectorResult(
                is_anomaly=False,
                detector=self.name,
                details={"reason": "constant_metric_normal"},
            )

        # Compute Z-score
        z = (feature_vector.current_value - features.baseline_mean) / features.baseline_std
        abs_z = abs(z)

        # Determine severity
        severity = None
        if abs_z > self.critical_threshold:
            severity = "critical"
        elif abs_z > self.high_threshold:
            severity = "high"
        elif abs_z > self.warning_threshold:
            severity = "warning"

        is_anomaly = severity is not None

        # Score: normalized to [0, 1] based on critical threshold
        score = min(abs_z / self.critical_threshold, 1.0) if is_anomaly else 0.0

        # Confidence based on how far above the threshold
        confidence = 0.0
        if is_anomaly:
            confidence = min(abs_z / (self.critical_threshold * 2), 1.0)

        return DetectorResult(
            is_anomaly=is_anomaly,
            detector=self.name,
            severity=severity,
            score=round(score, 4),
            confidence=round(confidence, 4),
            details={
                "z_score": round(z, 4),
                "abs_z": round(abs_z, 4),
                "current": feature_vector.current_value,
                "baseline_mean": features.baseline_mean,
                "baseline_std": features.baseline_std,
                "warning_threshold": self.warning_threshold,
                "high_threshold": self.high_threshold,
                "critical_threshold": self.critical_threshold,
            },
        )
