"""Time-series forecaster with seasonal Holt-Winters smoothing and prediction intervals."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
import numpy as np

from .seasonality import SeasonalDecomposer
from ..models import ForecastPoint


class TimeSeriesForecaster:
    """Predicts future metric trajectory with confidence bands using seasonal smoothing."""

    def __init__(
        self,
        alpha: float = 0.2,       # Level smoothing factor
        beta: float = 0.05,       # Trend smoothing factor
        confidence_z: float = 1.96, # 95% confidence interval
    ):
        self.alpha = alpha
        self.beta = beta
        self.confidence_z = confidence_z
        self.decomposer = SeasonalDecomposer()
        self.level = 100.0
        self.trend = 0.0
        self.residual_std = 15.0

    def fit(self, timestamps: list[datetime], values: list[float]) -> TimeSeriesForecaster:
        """Fit level, trend, residual variance, and seasonal profile on historical data."""
        if not values:
            return self

        self.decomposer.fit_from_series(timestamps, values)

        # De-seasonalize series to estimate base level and trend
        deseasonalized = []
        for ts, val in zip(timestamps, values):
            m = self.decomposer.get_seasonal_multiplier(ts)
            deseasonalized.append(val / max(m, 0.1))

        # Holt's linear smoothing on de-seasonalized series
        self.level = deseasonalized[0]
        self.trend = deseasonalized[1] - deseasonalized[0] if len(deseasonalized) > 1 else 0.0

        residuals = []
        for val in deseasonalized[1:]:
            last_level = self.level
            self.level = self.alpha * val + (1.0 - self.alpha) * (self.level + self.trend)
            self.trend = self.beta * (self.level - last_level) + (1.0 - self.beta) * self.trend
            residuals.append(val - (last_level + self.trend))

        if residuals:
            self.residual_std = float(max(np.std(residuals), 0.5))

        return self

    def forecast(
        self,
        start_time: datetime,
        horizon_minutes: int = 60,
        interval_minutes: int = 5,
        base_value: float | None = None,
    ) -> list[ForecastPoint]:
        """Project future values across the specified horizon."""
        current_level = base_value if base_value is not None else self.level
        steps = max(1, horizon_minutes // interval_minutes)
        points: list[ForecastPoint] = []

        curr_time = start_time
        for i in range(1, steps + 1):
            curr_time = curr_time + timedelta(minutes=interval_minutes)
            seasonal_factor = self.decomposer.get_seasonal_multiplier(curr_time)

            # Expected unadjusted base value with trend
            base_pred = current_level + (i * self.trend)
            # Apply seasonality
            predicted_val = max(0.0, base_pred * seasonal_factor)

            # Prediction interval expands with forecast horizon
            horizon_uncertainty = self.residual_std * math.sqrt(i) * seasonal_factor
            margin = self.confidence_z * horizon_uncertainty
            lower = max(0.0, predicted_val - margin)
            upper = predicted_val + margin

            points.append(
                ForecastPoint(
                    timestamp=curr_time,
                    predicted_value=round(predicted_val, 2),
                    lower_bound=round(lower, 2),
                    upper_bound=round(upper, 2),
                    std=round(horizon_uncertainty, 2),
                )
            )

        return points
