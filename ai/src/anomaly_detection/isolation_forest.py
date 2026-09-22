"""Isolation Forest Anomaly Detector with scikit-learn & NumPy implementations."""

from __future__ import annotations

import math
import numpy as np
from typing import Any


# Average path length of unsuccessful search in BST: c(n)
def _c(n: int) -> float:
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    euler_mascheroni = 0.5772156649
    return 2.0 * (math.log(n - 1) + euler_mascheroni) - (2.0 * (n - 1) / n)


class _ITreeNode:
    def __init__(
        self,
        left: _ITreeNode | None = None,
        right: _ITreeNode | None = None,
        split_feature: int | None = None,
        split_value: float | None = None,
        size: int = 0,
    ):
        self.left = left
        self.right = right
        self.split_feature = split_feature
        self.split_value = split_value
        self.size = size

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


class _NumPyIsolationTree:
    """Single Isolation Tree using recursive binary partitioning."""

    def __init__(self, max_depth: int, rng: np.random.RandomState):
        self.max_depth = max_depth
        self.rng = rng
        self.root: _ITreeNode | None = None

    def fit(self, X: np.ndarray, current_depth: int = 0) -> _ITreeNode:
        n_samples, n_features = X.shape

        if current_depth >= self.max_depth or n_samples <= 1:
            return _ITreeNode(size=n_samples)

        # Pick random feature
        feat = self.rng.randint(0, n_features)
        min_val = X[:, feat].min()
        max_val = X[:, feat].max()

        if min_val == max_val:
            return _ITreeNode(size=n_samples)

        # Pick random split between min and max
        split = self.rng.uniform(min_val, max_val)

        left_mask = X[:, feat] < split
        right_mask = ~left_mask

        left_node = self.fit(X[left_mask], current_depth + 1)
        right_node = self.fit(X[right_mask], current_depth + 1)

        return _ITreeNode(
            left=left_node,
            right=right_node,
            split_feature=feat,
            split_value=split,
            size=n_samples,
        )

    def path_length(self, x: np.ndarray, node: _ITreeNode, current_depth: int = 0) -> float:
        if node.is_leaf:
            return current_depth + _c(node.size)

        feat = node.split_feature
        val = node.split_value
        if feat is None or val is None:
            return current_depth + _c(node.size)

        if x[feat] < val:
            return self.path_length(x, node.left, current_depth + 1)
        else:
            return self.path_length(x, node.right, current_depth + 1)


class NumPyIsolationForest:
    """Vectorized NumPy fallback for Isolation Forest."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_samples: int = 256,
        contamination: float = 0.02,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.contamination = contamination
        self.random_state = random_state
        self.trees: list[_NumPyIsolationTree] = []
        self.n_samples_train = 0
        self.threshold = 0.5

    def fit(self, X: np.ndarray) -> NumPyIsolationForest:
        n_samples = X.shape[0]
        self.n_samples_train = n_samples
        subsample_size = min(self.max_samples, n_samples)
        max_depth = int(math.ceil(math.log2(max(subsample_size, 2))))
        rng = np.random.RandomState(self.random_state)

        self.trees = []
        for _ in range(self.n_estimators):
            tree_rng = np.random.RandomState(rng.randint(0, 1000000))
            itree = _NumPyIsolationTree(max_depth=max_depth, rng=tree_rng)
            indices = tree_rng.choice(n_samples, size=subsample_size, replace=False)
            itree.root = itree.fit(X[indices])
            self.trees.append(itree)

        # Calibrate threshold on training data
        scores = self.score_samples(X)
        self.threshold = max(0.60, float(np.percentile(scores, 100 * (1 - self.contamination))))
        return self

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Compute anomaly score s in [0, 1]. High score (>0.5) indicates anomaly."""
        c_factor = _c(self.max_samples)
        if c_factor <= 0:
            c_factor = 1.0

        n_samples = X.shape[0]
        scores = np.zeros(n_samples)

        for i in range(n_samples):
            x = X[i]
            paths = [t.path_length(x, t.root) for t in self.trees if t.root is not None]
            avg_h = np.mean(paths) if paths else c_factor
            score = 2.0 ** (- (avg_h / c_factor))
            scores[i] = score

        return scores

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Returns 1 for normal, -1 for anomaly."""
        scores = self.score_samples(X)
        return np.where(scores >= self.threshold, -1, 1)


class IsolationForestDetector:
    """Unified detector: automatically selects sklearn if installed or falls back to NumPy."""

    def __init__(
        self,
        n_estimators: int = 100,
        contamination: float = 0.02,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.random_state = random_state
        self.model: Any = None
        self.is_sklearn = False
        self.is_fitted = False
        self.threshold = 0.55

    def fit(self, X: np.ndarray) -> IsolationForestDetector:
        try:
            from sklearn.ensemble import IsolationForest as SklearnIF
            self.model = SklearnIF(
                n_estimators=self.n_estimators,
                contamination=self.contamination,
                random_state=self.random_state,
            )
            self.model.fit(X)
            self.is_sklearn = True
        except ImportError:
            self.model = NumPyIsolationForest(
                n_estimators=self.n_estimators,
                contamination=self.contamination,
                random_state=self.random_state,
            )
            self.model.fit(X)
            self.is_sklearn = False

        self.is_fitted = True
        return self

    def score(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (anomaly_scores in [0, 1], binary_is_anomaly bool array)."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before scoring.")

        if self.is_sklearn:
            # decision_function: higher is normal, negative is anomalous
            raw_scores = self.model.decision_function(X)
            # Convert to [0, 1] where 1.0 is anomaly
            norm_scores = 1.0 / (1.0 + np.exp(raw_scores * 5.0))
            preds = self.model.predict(X)
            is_anomaly = (preds == -1)
        else:
            norm_scores = self.model.score_samples(X)
            preds = self.model.predict(X)
            is_anomaly = (preds == -1)

        return norm_scores, is_anomaly

    def compute_feature_attribution(
        self,
        x: np.ndarray,
        feature_names: list[str],
        baseline: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Calculates feature importance/attribution to the anomaly using perturbation."""
        if not self.is_fitted or len(x.shape) != 1:
            return {f: 0.0 for f in feature_names}

        base_score, _ = self.score(x.reshape(1, -1))
        base_s = float(base_score[0])

        attributions: dict[str, float] = {}
        # Sensitivity analysis by feature replacement with baseline mean
        default_means = [0.15, 0.30, 50.0, 0.0, 100.0, 20.0]

        for i, name in enumerate(feature_names):
            x_perturbed = x.copy()
            ref_val = baseline[i] if (baseline is not None and i < len(baseline)) else (default_means[i] if i < len(default_means) else 0.0)
            x_perturbed[i] = ref_val
            perturbed_score, _ = self.score(x_perturbed.reshape(1, -1))
            diff = max(0.0, base_s - float(perturbed_score[0]))
            attributions[name] = float(diff)

        # Normalize attributions
        total = sum(attributions.values())
        if total > 0:
            for k in attributions:
                attributions[k] = round(attributions[k] / total, 3)
        else:
            uniform = round(1.0 / max(len(feature_names), 1), 3)
            for k in attributions:
                attributions[k] = uniform

        return attributions
