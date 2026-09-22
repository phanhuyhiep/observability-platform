"""Feature matrix builder for multivariate anomaly detection."""

from __future__ import annotations

import numpy as np
from typing import Sequence


DEFAULT_FEATURES = [
    "cpu_usage",
    "memory_usage",
    "p95_latency_ms",
    "error_rate",
    "request_throughput",
    "dependency_latency_ms",
]

# Standard baseline defaults if a metric is missing
FEATURE_DEFAULTS = {
    "cpu_usage": 0.15,               # 15% CPU
    "memory_usage": 0.30,            # 30% memory
    "p95_latency_ms": 50.0,          # 50 ms
    "error_rate": 0.0,               # 0% 5xx
    "request_throughput": 100.0,     # 100 req/s
    "dependency_latency_ms": 20.0,   # 20 ms
}


class FeatureMatrixBuilder:
    """Extracts, validates, and normalizes multivariate telemetry vectors."""

    def __init__(self, feature_names: Sequence[str] | None = None):
        self.feature_names = list(feature_names or DEFAULT_FEATURES)

    def extract_vector(self, raw_sample: dict[str, float]) -> np.ndarray:
        """Convert a single entity metric dictionary into an ordered 1D array."""
        vector = []
        for name in self.feature_names:
            val = raw_sample.get(name)
            if val is None or np.isnan(val):
                val = FEATURE_DEFAULTS.get(name, 0.0)
            vector.append(float(val))
        return np.array(vector, dtype=np.float64)

    def build_matrix(self, samples: Sequence[dict[str, float]]) -> np.ndarray:
        """Convert a list of metric dictionaries into an (N, D) feature matrix."""
        if not samples:
            return np.empty((0, len(self.feature_names)), dtype=np.float64)
        return np.array([self.extract_vector(s) for s in samples], dtype=np.float64)

    def generate_synthetic_baseline(
        self,
        n_samples: int = 100,
        noise_level: float = 0.25,
        random_seed: int = 42,
    ) -> np.ndarray:
        """Generate realistic baseline telemetry matrix for cold-start training."""
        rng = np.random.RandomState(random_seed)
        matrix = np.zeros((n_samples, len(self.feature_names)), dtype=np.float64)

        for i, name in enumerate(self.feature_names):
            base = FEATURE_DEFAULTS.get(name, 1.0)
            std = max(base * noise_level, 0.01)
            # Sample normal distribution around baseline
            vals = rng.normal(loc=base, scale=std, size=n_samples)
            # Clip non-negative metrics
            if "rate" in name or "usage" in name or "latency" in name:
                vals = np.maximum(vals, 0.0)
            if "usage" in name or "rate" in name:
                vals = np.minimum(vals, 1.0)
            matrix[:, i] = vals

        return matrix
