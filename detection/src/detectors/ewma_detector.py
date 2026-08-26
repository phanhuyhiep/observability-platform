"""EWMA (Exponentially Weighted Moving Average) anomaly detector."""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

from ..models import DetectorResult, FeatureVector

logger = logging.getLogger(__name__)


class EWMADetector:
    """Detects anomalies using Exponentially Weighted Moving Average.

    EWMA_t = α * x_t + (1 - α) * EWMA_{t-1}

    Anomaly condition:
        deviation = |current - EWMA|
        if deviation > k * EWMA_std → anomaly

    The detector maintains internal state per (entity, metric) pair
    to track the running EWMA.
    """

    name = "ewma"

    def __init__(
        self,
        alpha: float = 0.1,
        warning_k: float = 2.0,
        high_k: float = 3.0,
        critical_k: float = 5.0,
    ):
        self.alpha = alpha
        self.warning_k = warning_k
        self.high_k = high_k
        self.critical_k = critical_k

        # Internal state: running EWMA and variance per entity/metric
        self._ewma: dict[str, float] = {}
        self._ewma_var: dict[str, float] = {}
        self._initialized: dict[str, bool] = defaultdict(lambda: False)

    def _key(self, entity_id: str, metric: str) -> str:
        return f"{entity_id}:{metric}"

    def update(self, entity_id: str, metric: str, value: float) -> None:
        """Update internal EWMA state with a new value."""
        key = self._key(entity_id, metric)

        if not self._initialized[key]:
            self._ewma[key] = value
            self._ewma_var[key] = 0.0
            self._initialized[key] = True
            return

        prev_ewma = self._ewma[key]
        new_ewma = self.alpha * value + (1 - self.alpha) * prev_ewma
        diff = value - prev_ewma
        new_var = (1 - self.alpha) * (self._ewma_var[key] + self.alpha * diff * diff)

        self._ewma[key] = new_ewma
        self._ewma_var[key] = new_var

    def evaluate(self, feature_vector: FeatureVector) -> DetectorResult:
        """Evaluate using EWMA deviation."""
        key = self._key(feature_vector.entity_id, feature_vector.metric)
        current = feature_vector.current_value

        # Update EWMA state
        self.update(feature_vector.entity_id, feature_vector.metric, current)

        if not self._initialized[key] or self._ewma_var.get(key, 0) == 0:
            return DetectorResult(
                is_anomaly=False,
                detector=self.name,
                details={"reason": "insufficient_data"},
            )

        ewma = self._ewma[key]
        ewma_std = float(np.sqrt(self._ewma_var[key]))
        deviation = abs(current - ewma)

        if ewma_std == 0:
            return DetectorResult(
                is_anomaly=False,
                detector=self.name,
                details={"reason": "zero_variance"},
            )

        # Compute k-factor: deviation / ewma_std
        k_factor = deviation / ewma_std

        # Determine severity
        severity = None
        if k_factor > self.critical_k:
            severity = "critical"
        elif k_factor > self.high_k:
            severity = "high"
        elif k_factor > self.warning_k:
            severity = "warning"

        is_anomaly = severity is not None
        score = min(k_factor / self.critical_k, 1.0) if is_anomaly else 0.0
        confidence = min(k_factor / (self.critical_k * 2), 1.0) if is_anomaly else 0.0

        return DetectorResult(
            is_anomaly=is_anomaly,
            detector=self.name,
            severity=severity,
            score=round(score, 4),
            confidence=round(confidence, 4),
            details={
                "ewma": round(ewma, 4),
                "ewma_std": round(ewma_std, 4),
                "deviation": round(deviation, 4),
                "k_factor": round(k_factor, 4),
                "current": current,
                "alpha": self.alpha,
            },
        )

    def reset(self, entity_id: str | None = None, metric: str | None = None) -> None:
        """Reset EWMA state. If entity_id/metric provided, reset only that key."""
        if entity_id and metric:
            key = self._key(entity_id, metric)
            self._ewma.pop(key, None)
            self._ewma_var.pop(key, None)
            self._initialized.pop(key, None)
        else:
            self._ewma.clear()
            self._ewma_var.clear()
            self._initialized.clear()
