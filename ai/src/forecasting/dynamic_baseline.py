"""Dynamic seasonal-aware baseline calculation engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .forecaster import TimeSeriesForecaster
from .seasonality import SeasonalDecomposer
from ..models import DynamicBaselineResponse


# Default typical baseline parameters per metric category
STATIC_METRIC_PROFILES = {
    "cpu_usage": {"base": 0.20, "std": 0.05, "min_val": 0.0, "max_val": 1.0},
    "memory_usage": {"base": 0.40, "std": 0.08, "min_val": 0.0, "max_val": 1.0},
    "p95_latency_ms": {"base": 45.0, "std": 12.0, "min_val": 0.0, "max_val": 10000.0},
    "error_rate": {"base": 0.005, "std": 0.002, "min_val": 0.0, "max_val": 1.0},
    "request_throughput": {"base": 150.0, "std": 35.0, "min_val": 0.0, "max_val": 100000.0},
    "dependency_latency_ms": {"base": 25.0, "std": 8.0, "min_val": 0.0, "max_val": 10000.0},
}


class DynamicBaselineEngine:
    """Computes time-of-day and day-of-week adjusted dynamic thresholds."""

    def __init__(self, anomaly_z_threshold: float = 3.0):
        self.anomaly_z_threshold = anomaly_z_threshold
        self.decomposer = SeasonalDecomposer()
        self.forecasters: dict[str, TimeSeriesForecaster] = {}

    def get_dynamic_baseline(
        self,
        entity_id: str,
        metric: str,
        query_time: datetime | None = None,
        current_value: float | None = None,
    ) -> DynamicBaselineResponse:
        """Compute the dynamic expectation and boundaries for an entity metric at a given moment."""
        now = query_time or datetime.now(timezone.utc)
        profile = STATIC_METRIC_PROFILES.get(metric, {"base": 50.0, "std": 10.0, "min_val": 0.0, "max_val": None})

        # Calculate seasonal multiplier for query time
        seasonal_mult = self.decomposer.get_seasonal_multiplier(now)

        # Expected dynamic mean
        expected_mean = profile["base"] * seasonal_mult
        dynamic_std = profile["std"] * math.sqrt(seasonal_mult)

        # 3-sigma dynamic boundaries
        lower = max(profile["min_val"], expected_mean - (self.anomaly_z_threshold * dynamic_std))
        upper = expected_mean + (self.anomaly_z_threshold * dynamic_std)
        if profile["max_val"] is not None:
            upper = min(profile["max_val"], upper)

        is_anom: bool | None = None
        z_score: float | None = None

        if current_value is not None:
            z_score = (current_value - expected_mean) / max(dynamic_std, 0.001)
            is_anom = abs(z_score) >= self.anomaly_z_threshold

        return DynamicBaselineResponse(
            entity_id=entity_id,
            metric=metric,
            timestamp=now,
            expected_mean=round(expected_mean, 3),
            lower_bound=round(lower, 3),
            upper_bound=round(upper, 3),
            std=round(dynamic_std, 3),
            current_value=round(current_value, 3) if current_value is not None else None,
            is_anomalous=is_anom,
            z_score=round(z_score, 2) if z_score is not None else None,
        )

    def get_forecaster(self, entity_id: str, metric: str) -> TimeSeriesForecaster:
        """Get or create forecaster for an entity-metric pair."""
        key = f"{entity_id}:{metric}"
        if key not in self.forecasters:
            f = TimeSeriesForecaster()
            profile = STATIC_METRIC_PROFILES.get(metric, {"base": 50.0, "std": 10.0})
            f.level = profile["base"]
            f.residual_std = profile["std"]
            self.forecasters[key] = f
        return self.forecasters[key]
