"""Abstract base class for all detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import DetectorResult, FeatureVector


class DetectorInterface(ABC):
    """Base interface that all detectors must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return detector name (e.g., 'rule', 'z_score', 'ewma')."""
        ...

    @abstractmethod
    def evaluate(self, feature_vector: FeatureVector) -> DetectorResult:
        """Evaluate a feature vector and return detection result.

        Args:
            feature_vector: Computed features for an entity/metric pair.

        Returns:
            DetectorResult indicating whether an anomaly was detected.
        """
        ...
