"""Latency feature extraction from Prometheus histogram metrics."""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from ..models import FeatureValues, FeatureVector

logger = logging.getLogger(__name__)


def compute_latency_features(
    p50_values: list[float],
    p95_values: list[float],
    p99_values: list[float],
    entity_type: str,
    entity_id: str,
    window: str = "5m",
    baseline_mean: float | None = None,
    baseline_std: float | None = None,
    baseline_window: str | None = None,
) -> FeatureVector:
    """Compute latency-specific features from percentile time series.

    The primary metric tracked is P95 latency, with tail increase
    calculated as the ratio between P99 and P50.
    """
    if not p95_values:
        return FeatureVector(
            entity_type=entity_type,
            entity_id=entity_id,
            metric="p95_latency",
            timestamp=datetime.utcnow(),
            current_value=0.0,
            window=window,
        )

    p95_arr = np.array(p95_values, dtype=np.float64)
    current_p95 = float(p95_arr[-1])

    mean = float(np.mean(p95_arr))
    std = float(np.std(p95_arr))

    # Tail latency increase: P99/P50 ratio
    tail_increase = 0.0
    if p50_values and p99_values:
        current_p50 = p50_values[-1] if p50_values[-1] > 0 else 1.0
        current_p99 = p99_values[-1]
        tail_increase = current_p99 / current_p50

    # Slope of P95
    if len(p95_arr) > 1:
        x = np.arange(len(p95_arr), dtype=np.float64)
        slope = float(np.polyfit(x, p95_arr, 1)[0])
    else:
        slope = 0.0

    # Rate of change
    if len(p95_arr) > 1 and p95_arr[0] != 0:
        rate_of_change = float((p95_arr[-1] - p95_arr[0]) / abs(p95_arr[0]) * 100)
    else:
        rate_of_change = 0.0

    # Z-score against baseline
    z_score = None
    if baseline_mean is not None and baseline_std is not None and baseline_std > 0:
        z_score = (current_p95 - baseline_mean) / baseline_std

    features = FeatureValues(
        mean=round(mean, 4),
        std=round(std, 4),
        min=round(float(np.min(p95_arr)), 4),
        max=round(float(np.max(p95_arr)), 4),
        slope=round(slope, 4),
        rate_of_change=round(rate_of_change, 4),
        z_score=round(z_score, 4) if z_score is not None else None,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        baseline_window=baseline_window,
    )

    return FeatureVector(
        entity_type=entity_type,
        entity_id=entity_id,
        metric="p95_latency",
        timestamp=datetime.utcnow(),
        current_value=round(current_p95, 4),
        window=window,
        features=features,
    )
