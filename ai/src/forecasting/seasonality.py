"""Seasonal pattern decomposition for microservice workloads."""

from __future__ import annotations

import math
from datetime import datetime
import numpy as np


class SeasonalDecomposer:
    """Models diurnal (24h) and weekly (7d) cyclic patterns in microservices telemetry."""

    def __init__(self):
        # Default diurnal multipliers for hours 0..23 (normalized around 1.0)
        # Low traffic at 02:00-05:00 (~0.4), peak traffic at 14:00-16:00 (~1.6)
        self.hourly_profile = [
            0.50, 0.42, 0.38, 0.35, 0.40, 0.55,   # 00:00 - 05:00
            0.75, 0.95, 1.20, 1.35, 1.45, 1.50,   # 06:00 - 11:00
            1.40, 1.55, 1.60, 1.55, 1.45, 1.30,   # 12:00 - 17:00
            1.25, 1.35, 1.40, 1.20, 0.90, 0.70    # 18:00 - 23:00
        ]
        # Normalize to mean = 1.0
        mean_p = sum(self.hourly_profile) / 24.0
        self.hourly_profile = [p / mean_p for p in self.hourly_profile]

        # Day-of-week multipliers (0=Monday .. 6=Sunday)
        self.weekday_profile = [1.10, 1.15, 1.18, 1.12, 1.05, 0.75, 0.65]
        mean_w = sum(self.weekday_profile) / 7.0
        self.weekday_profile = [w / mean_w for w in self.weekday_profile]

    def get_seasonal_multiplier(self, dt: datetime) -> float:
        """Returns the composite seasonal scaling factor for a specific timestamp."""
        hour_factor = self.hourly_profile[dt.hour]
        day_factor = self.weekday_profile[dt.weekday()]
        return hour_factor * day_factor

    def fit_from_series(self, timestamps: list[datetime], values: list[float]) -> None:
        """Update hourly profile empirically from historical observations."""
        if len(values) < 24:
            return

        hourly_buckets: dict[int, list[float]] = {h: [] for h in range(24)}
        for ts, val in zip(timestamps, values):
            hourly_buckets[ts.hour].append(val)

        overall_mean = np.mean(values)
        if overall_mean <= 0:
            return

        new_profile = []
        for h in range(24):
            vals = hourly_buckets[h]
            h_mean = np.mean(vals) if vals else overall_mean
            new_profile.append(h_mean / overall_mean)

        mean_p = sum(new_profile) / 24.0
        self.hourly_profile = [p / mean_p for p in new_profile]
