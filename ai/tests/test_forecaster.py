"""Unit tests for TimeSeriesForecaster."""

from datetime import datetime, timedelta, timezone
import pytest

from ai.src.forecasting.forecaster import TimeSeriesForecaster


def test_forecaster_projection():
    forecaster = TimeSeriesForecaster()
    now = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)

    # Synthetic series
    timestamps = [now - timedelta(hours=i) for i in range(24, 0, -1)]
    values = [100.0 + (i % 5) * 5.0 for i in range(len(timestamps))]

    forecaster.fit(timestamps, values)
    points = forecaster.forecast(start_time=now, horizon_minutes=30, interval_minutes=5)

    assert len(points) == 6  # 30 / 5 = 6
    for p in points:
        assert p.predicted_value > 0.0
        assert p.upper_bound >= p.predicted_value
        assert p.lower_bound <= p.predicted_value
        assert p.std > 0.0


def test_forecaster_horizon_uncertainty_expansion():
    forecaster = TimeSeriesForecaster()
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    points = forecaster.forecast(start_time=now, horizon_minutes=60, interval_minutes=15)

    assert len(points) == 4
    # Uncertainty / std should expand as we forecast further out into the future
    assert points[-1].std >= points[0].std
