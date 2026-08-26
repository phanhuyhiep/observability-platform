"""Log feature extraction from Loki data."""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import FeatureValues, FeatureVector

logger = logging.getLogger(__name__)


def compute_log_features(
    error_count: int,
    burst_rate: float,
    entity_type: str,
    entity_id: str,
    window: str = "5m",
    baseline_mean: float | None = None,
    baseline_std: float | None = None,
    baseline_window: str | None = None,
) -> FeatureVector:
    """Compute log-based features.

    Args:
        error_count: Number of error-level log entries in the window.
        burst_rate: Maximum log rate (logs/sec) in the window.
        entity_type: Entity type.
        entity_id: Entity identifier.
        window: Time window.
        baseline_mean: Baseline mean error count.
        baseline_std: Baseline std for error count.
        baseline_window: Baseline window period.

    Returns:
        FeatureVector with log statistics.
    """
    current_value = float(error_count)

    z_score = None
    if baseline_mean is not None and baseline_std is not None and baseline_std > 0:
        z_score = (current_value - baseline_mean) / baseline_std

    features = FeatureValues(
        mean=current_value,
        std=0.0,
        min=current_value,
        max=current_value,
        slope=0.0,
        rate_of_change=burst_rate,
        z_score=round(z_score, 4) if z_score is not None else None,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        baseline_window=baseline_window,
    )

    return FeatureVector(
        entity_type=entity_type,
        entity_id=entity_id,
        metric="error_count",
        timestamp=datetime.utcnow(),
        current_value=current_value,
        window=window,
        features=features,
    )
