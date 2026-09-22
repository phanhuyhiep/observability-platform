"""Unit tests for FeatureMatrixBuilder."""

import numpy as np
import pytest

from ai.src.anomaly_detection.feature_matrix import FeatureMatrixBuilder, DEFAULT_FEATURES


def test_extract_vector_complete():
    builder = FeatureMatrixBuilder()
    sample = {
        "cpu_usage": 0.45,
        "memory_usage": 0.60,
        "p95_latency_ms": 120.0,
        "error_rate": 0.02,
        "request_throughput": 250.0,
        "dependency_latency_ms": 35.0,
    }
    vec = builder.extract_vector(sample)
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (len(DEFAULT_FEATURES),)
    assert vec[0] == 0.45
    assert vec[2] == 120.0


def test_extract_vector_impute_missing():
    builder = FeatureMatrixBuilder()
    # Missing p95_latency_ms and dependency_latency_ms
    sample = {
        "cpu_usage": 0.20,
    }
    vec = builder.extract_vector(sample)
    assert vec.shape == (len(DEFAULT_FEATURES),)
    assert vec[0] == 0.20
    assert vec[2] == 50.0  # Default p95 latency


def test_build_matrix():
    builder = FeatureMatrixBuilder()
    samples = [
        {"cpu_usage": 0.1, "error_rate": 0.0},
        {"cpu_usage": 0.2, "error_rate": 0.01},
        {"cpu_usage": 0.3, "error_rate": 0.02},
    ]
    mat = builder.build_matrix(samples)
    assert mat.shape == (3, len(DEFAULT_FEATURES))


def test_generate_synthetic_baseline():
    builder = FeatureMatrixBuilder()
    mat = builder.generate_synthetic_baseline(n_samples=50, random_seed=123)
    assert mat.shape == (50, len(DEFAULT_FEATURES))
    # Check all values are non-negative
    assert np.all(mat >= 0.0)
