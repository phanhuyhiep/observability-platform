"""Unit tests for metric feature extraction."""

import pytest
from datetime import datetime
from src.features.metric_features import compute_metric_features


class TestMetricFeatures:
    """Test suite for metric feature computation."""

    def test_basic_statistics(self):
        """Test mean, std, min, max computation."""
        values = [10, 20, 30, 40, 50]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="cpu_usage",
        )

        assert fv.current_value == 50.0
        assert fv.features.mean == 30.0
        assert fv.features.min == 10.0
        assert fv.features.max == 50.0
        assert fv.features.std > 0

    def test_slope_positive(self):
        """Increasing values should produce positive slope."""
        values = [10, 20, 30, 40, 50]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="requests",
        )
        assert fv.features.slope > 0

    def test_slope_negative(self):
        """Decreasing values should produce negative slope."""
        values = [50, 40, 30, 20, 10]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="requests",
        )
        assert fv.features.slope < 0

    def test_rate_of_change(self):
        """Rate of change = (last - first) / |first| * 100."""
        values = [100, 110, 120, 130, 150]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="latency",
        )
        # (150 - 100) / 100 * 100 = 50%
        assert fv.features.rate_of_change == 50.0

    def test_z_score_with_baseline(self):
        """Z-score should be computed when baseline is provided."""
        values = [100, 200, 300]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="latency",
            baseline_mean=100.0,
            baseline_std=50.0,
            baseline_window="7d",
        )
        # z = (300 - 100) / 50 = 4.0
        assert fv.features.z_score == 4.0

    def test_z_score_without_baseline(self):
        """Z-score should be None when no baseline provided."""
        values = [100, 200, 300]
        fv = compute_metric_features(
            values=values,
            entity_type="service",
            entity_id="test-svc",
            metric="latency",
        )
        assert fv.features.z_score is None

    def test_empty_values(self):
        """Empty input should return zero-value feature vector."""
        fv = compute_metric_features(
            values=[],
            entity_type="service",
            entity_id="test-svc",
            metric="cpu",
        )
        assert fv.current_value == 0.0
        assert fv.features.mean == 0.0

    def test_single_value(self):
        """Single value should still produce valid features."""
        fv = compute_metric_features(
            values=[42.0],
            entity_type="pod",
            entity_id="pod-1",
            metric="memory",
        )
        assert fv.current_value == 42.0
        assert fv.features.mean == 42.0
        assert fv.features.std == 0.0
        assert fv.features.slope == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
