"""Metric feature extraction from Prometheus data."""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from ..models import FeatureValues, FeatureVector

logger = logging.getLogger(__name__)


def compute_metric_features(
    values: list[float],
    entity_type: str,
    entity_id: str,
    metric: str,
    window: str = "5m",
    baseline_mean: float | None = None,
    baseline_std: float | None = None,
    baseline_window: str | None = None,
) -> FeatureVector:
    """Compute statistical features from a list of metric values.

    Args:
        values: Raw metric values from Prometheus range query.
        entity_type: Type of entity (service, pod, node).
        entity_id: Entity identifier.
        metric: Metric name.
        window: Time window for current values.
        baseline_mean: Pre-computed baseline mean (from Baseline table).
        baseline_std: Pre-computed baseline std (from Baseline table).
        baseline_window: Baseline window period (e.g., "7d").

    Returns:
        FeatureVector with computed statistics.
    """
    if not values:
        return FeatureVector(
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            timestamp=datetime.utcnow(),
            current_value=0.0,
            window=window,
        )

    arr = np.array(values, dtype=np.float64)
    current = float(arr[-1])

    mean = float(np.mean(arr))
    std = float(np.std(arr))
    min_val = float(np.min(arr))
    max_val = float(np.max(arr))

    # Slope: linear regression coefficient
    if len(arr) > 1:
        x = np.arange(len(arr), dtype=np.float64)
        slope = float(np.polyfit(x, arr, 1)[0])
    else:
        slope = 0.0

    # Rate of change: (last - first) / first * 100
    if len(arr) > 1 and arr[0] != 0:
        rate_of_change = float((arr[-1] - arr[0]) / abs(arr[0]) * 100)
    else:
        rate_of_change = 0.0

    # Z-score against baseline
    z_score = None
    if baseline_mean is not None and baseline_std is not None and baseline_std > 0:
        z_score = (current - baseline_mean) / baseline_std

    features = FeatureValues(
        mean=round(mean, 4),
        std=round(std, 4),
        min=round(min_val, 4),
        max=round(max_val, 4),
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
        metric=metric,
        timestamp=datetime.utcnow(),
        current_value=round(current, 4),
        window=window,
        features=features,
    )
