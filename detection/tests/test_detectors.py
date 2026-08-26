"""Unit tests for Z-Score and EWMA detectors with synthetic data."""

import pytest
from src.models import FeatureValues, FeatureVector
from src.detectors.zscore_detector import ZScoreDetector
from src.detectors.ewma_detector import EWMADetector
from datetime import datetime


class TestZScoreDetector:
    """Test suite for Z-Score detector."""

    def setup_method(self):
        self.detector = ZScoreDetector(
            warning_threshold=3.0,
            high_threshold=5.0,
            critical_threshold=10.0,
        )

    def _make_fv(self, current: float, mean: float, std: float) -> FeatureVector:
        """Helper to create a FeatureVector with baseline."""
        return FeatureVector(
            entity_type="service",
            entity_id="test-service",
            metric="cpu_usage",
            timestamp=datetime.utcnow(),
            current_value=current,
            features=FeatureValues(
                mean=mean,
                std=std,
                baseline_mean=mean,
                baseline_std=std,
                baseline_window="7d",
            ),
        )

    def test_normal_value_no_anomaly(self):
        """Value within 1 std – no anomaly."""
        fv = self._make_fv(current=55, mean=50, std=10)
        result = self.detector.evaluate(fv)
        assert not result.is_anomaly

    def test_warning_severity(self):
        """Value exceeds warning threshold (|z| > 3)."""
        # z = (85 - 50) / 10 = 3.5
        fv = self._make_fv(current=85, mean=50, std=10)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "warning"

    def test_high_severity(self):
        """Value exceeds high threshold (|z| > 5)."""
        # z = (110 - 50) / 10 = 6
        fv = self._make_fv(current=110, mean=50, std=10)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "high"

    def test_critical_severity(self):
        """Value exceeds critical threshold (|z| > 10)."""
        # z = (160 - 50) / 10 = 11
        fv = self._make_fv(current=160, mean=50, std=10)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "critical"
        assert result.score == 1.0  # Capped at 1.0

    def test_negative_deviation(self):
        """Negative deviation should also trigger anomaly."""
        # z = (10 - 50) / 10 = -4.0 → |z| = 4 → warning
        fv = self._make_fv(current=10, mean=50, std=10)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "warning"

    def test_no_baseline_no_anomaly(self):
        """Without baseline, detector should not trigger."""
        fv = FeatureVector(
            entity_type="service",
            entity_id="test-service",
            metric="cpu_usage",
            timestamp=datetime.utcnow(),
            current_value=100,
            features=FeatureValues(),
        )
        result = self.detector.evaluate(fv)
        assert not result.is_anomaly
        assert result.details.get("reason") == "no_baseline"

    def test_zero_std_deviation(self):
        """Constant metric (std=0) with deviation should flag warning."""
        fv = self._make_fv(current=55, mean=50, std=0)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "warning"

    def test_zero_std_normal(self):
        """Constant metric (std=0) at baseline should be normal."""
        fv = self._make_fv(current=50, mean=50, std=0)
        result = self.detector.evaluate(fv)
        assert not result.is_anomaly

    def test_extreme_spike(self):
        """Simulate the design doc example: payment-service P95 spike."""
        # z = (4200 - 220) / 80 = 49.75 → critical, score = 1.0
        fv = self._make_fv(current=4200, mean=220, std=80)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly
        assert result.severity == "critical"
        assert result.score == 1.0
        assert abs(result.details["z_score"] - 49.75) < 0.01


class TestEWMADetector:
    """Test suite for EWMA detector."""

    def setup_method(self):
        self.detector = EWMADetector(
            alpha=0.3,  # Higher alpha for faster test response
            warning_k=2.0,
            high_k=3.0,
            critical_k=5.0,
        )

    def _make_fv(self, entity_id: str, metric: str, value: float) -> FeatureVector:
        return FeatureVector(
            entity_type="service",
            entity_id=entity_id,
            metric=metric,
            timestamp=datetime.utcnow(),
            current_value=value,
        )

    def test_warmup_no_anomaly(self):
        """First data point should not trigger anomaly (insufficient data)."""
        fv = self._make_fv("svc-a", "cpu", 50)
        result = self.detector.evaluate(fv)
        assert not result.is_anomaly

    def test_stable_series_no_anomaly(self):
        """Stable values should not trigger anomaly."""
        for v in [50, 51, 49, 50, 52, 48, 50]:
            fv = self._make_fv("svc-b", "cpu", v)
            result = self.detector.evaluate(fv)

        # Last evaluation on a normal value
        assert not result.is_anomaly

    def test_sudden_spike_triggers_anomaly(self):
        """A sudden spike after stable period should trigger anomaly."""
        # Build stable baseline
        for v in [50] * 20:
            fv = self._make_fv("svc-c", "latency", v)
            self.detector.evaluate(fv)

        # Inject spike
        fv = self._make_fv("svc-c", "latency", 500)
        result = self.detector.evaluate(fv)
        assert result.is_anomaly

    def test_gradual_increase_no_anomaly(self):
        """Gradual increase should not trigger anomaly (EWMA follows)."""
        for i in range(50):
            fv = self._make_fv("svc-d", "requests", 50 + i * 0.5)
            result = self.detector.evaluate(fv)
        # Gradual: EWMA tracks it
        assert not result.is_anomaly

    def test_reset_clears_state(self):
        """Reset should clear internal state."""
        for v in [50] * 10:
            self.detector.evaluate(self._make_fv("svc-e", "cpu", v))

        self.detector.reset("svc-e", "cpu")

        # After reset, first point should be warmup
        result = self.detector.evaluate(self._make_fv("svc-e", "cpu", 50))
        assert not result.is_anomaly
        assert result.details.get("reason") == "insufficient_data"

    def test_independent_entity_tracking(self):
        """Different entities should be tracked independently."""
        # Stable for svc-f
        for v in [50] * 15:
            self.detector.evaluate(self._make_fv("svc-f", "cpu", v))

        # Spike for svc-g only
        for v in [50] * 15:
            self.detector.evaluate(self._make_fv("svc-g", "cpu", v))

        result_g = self.detector.evaluate(self._make_fv("svc-g", "cpu", 500))
        result_f = self.detector.evaluate(self._make_fv("svc-f", "cpu", 51))

        assert result_g.is_anomaly
        assert not result_f.is_anomaly


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
