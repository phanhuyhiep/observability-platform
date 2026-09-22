"""Unit tests for IsolationForestDetector."""

import numpy as np
import pytest

from ai.src.anomaly_detection.feature_matrix import FeatureMatrixBuilder
from ai.src.anomaly_detection.isolation_forest import IsolationForestDetector, NumPyIsolationForest


def test_numpy_isolation_forest_basic():
    rng = np.random.RandomState(42)
    # 80 normal points clustered around (0.5, 0.5)
    normal_data = rng.normal(loc=0.5, scale=0.05, size=(80, 4))
    # 5 extreme outliers around (5.0, 5.0)
    outliers = rng.uniform(low=4.0, high=6.0, size=(5, 4))
    X = np.vstack([normal_data, outliers])

    forest = NumPyIsolationForest(n_estimators=50, contamination=0.05, random_state=42)
    forest.fit(X)

    normal_scores = forest.score_samples(normal_data[:10])
    outlier_scores = forest.score_samples(outliers)

    # Outliers should have significantly higher anomaly scores than normal data
    assert np.mean(outlier_scores) > np.mean(normal_scores)


def test_detector_unified_fit_and_score():
    builder = FeatureMatrixBuilder()
    baseline = builder.generate_synthetic_baseline(n_samples=100, random_seed=42)

    detector = IsolationForestDetector(n_estimators=40, contamination=0.05, random_state=42)
    detector.fit(baseline)
    assert detector.is_fitted

    # Test normal vector
    normal_vec = builder.extract_vector({
        "cpu_usage": 0.15,
        "memory_usage": 0.30,
        "p95_latency_ms": 50.0,
        "error_rate": 0.0,
        "request_throughput": 100.0,
        "dependency_latency_ms": 20.0,
    })
    scores, is_anom = detector.score(normal_vec.reshape(1, -1))
    assert scores[0] < 0.70

    # Test extreme anomaly vector (massive latency spike + 5xx error explosion)
    anom_vec = builder.extract_vector({
        "cpu_usage": 0.98,
        "memory_usage": 0.95,
        "p95_latency_ms": 4800.0,
        "error_rate": 0.65,
        "request_throughput": 10.0,
        "dependency_latency_ms": 2500.0,
    })
    scores_anom, is_anom_flag = detector.score(anom_vec.reshape(1, -1))
    assert scores_anom[0] > scores[0]


def test_feature_attribution():
    builder = FeatureMatrixBuilder()
    baseline = builder.generate_synthetic_baseline(n_samples=80, random_seed=42)

    detector = IsolationForestDetector(n_estimators=40, contamination=0.05, random_state=42)
    detector.fit(baseline)

    # Anomaly primarily caused by p95_latency_ms (4500ms vs normal 50ms)
    anom_vec = builder.extract_vector({
        "cpu_usage": 0.15,
        "memory_usage": 0.30,
        "p95_latency_ms": 4500.0,
        "error_rate": 0.0,
        "request_throughput": 100.0,
        "dependency_latency_ms": 20.0,
    })

    attributions = detector.compute_feature_attribution(
        x=anom_vec,
        feature_names=builder.feature_names,
        baseline=np.mean(baseline, axis=0),
    )

    assert "p95_latency_ms" in attributions
    assert attributions["p95_latency_ms"] > 0.0
    # Sum of attributions should normalize to ~1.0
    assert abs(sum(attributions.values()) - 1.0) < 0.05
