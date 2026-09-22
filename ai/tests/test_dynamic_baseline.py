"""Unit tests for DynamicBaselineEngine and seasonality."""

from datetime import datetime, timezone
import pytest

from ai.src.forecasting.dynamic_baseline import DynamicBaselineEngine
from ai.src.forecasting.seasonality import SeasonalDecomposer


def test_seasonal_decomposer_day_night():
    decomposer = SeasonalDecomposer()
    night_dt = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)  # 03:00 UTC (night)
    peak_dt = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)  # 14:00 UTC (afternoon peak)

    night_factor = decomposer.get_seasonal_multiplier(night_dt)
    peak_factor = decomposer.get_seasonal_multiplier(peak_dt)

    assert peak_factor > night_factor
    assert night_factor < 1.0
    assert peak_factor > 1.0


def test_dynamic_baseline_expected_values():
    engine = DynamicBaselineEngine(anomaly_z_threshold=3.0)
    night_dt = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)
    peak_dt = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)

    res_night = engine.get_dynamic_baseline("cartservice", "request_throughput", query_time=night_dt)
    res_peak = engine.get_dynamic_baseline("cartservice", "request_throughput", query_time=peak_dt)

    assert res_peak.expected_mean > res_night.expected_mean
    assert res_peak.upper_bound > res_night.upper_bound


def test_dynamic_baseline_anomaly_detection():
    engine = DynamicBaselineEngine(anomaly_z_threshold=3.0)
    now = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)

    # Normal latency (45 ms vs expected ~45-60 ms)
    res_normal = engine.get_dynamic_baseline("cartservice", "p95_latency_ms", query_time=now, current_value=48.0)
    assert res_normal.is_anomalous is False
    assert abs(res_normal.z_score) < 3.0

    # Extreme latency spike (2500 ms)
    res_anom = engine.get_dynamic_baseline("cartservice", "p95_latency_ms", query_time=now, current_value=2500.0)
    assert res_anom.is_anomalous is True
    assert res_anom.z_score > 3.0
