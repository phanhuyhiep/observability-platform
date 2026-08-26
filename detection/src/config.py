"""Configuration loader for Detection Service."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class DetectionConfig(BaseModel):
    interval: str = "2m"
    batch_size: int = 50
    namespace: str = "default"


class FeatureEngineConfig(BaseModel):
    default_window: str = "5m"
    baseline_window: str = "7d"
    baseline_update_interval: str = "1h"


class ZScoreThresholds(BaseModel):
    warning: float = 3.0
    high: float = 5.0
    critical: float = 10.0


class EWMAThresholds(BaseModel):
    warning: float = 2.0
    high: float = 3.0
    critical: float = 5.0


class RuleDetectorConfig(BaseModel):
    enabled: bool = True
    rules_path: str = "./rules/"


class ZScoreDetectorConfig(BaseModel):
    enabled: bool = True
    thresholds: ZScoreThresholds = ZScoreThresholds()
    min_data_points: int = 100


class EWMADetectorConfig(BaseModel):
    enabled: bool = True
    alpha: float = 0.1
    thresholds: EWMAThresholds = EWMAThresholds()


class DetectorsConfig(BaseModel):
    rule: RuleDetectorConfig = RuleDetectorConfig()
    zscore: ZScoreDetectorConfig = ZScoreDetectorConfig()
    ewma: EWMADetectorConfig = EWMADetectorConfig()


class DeduplicationConfig(BaseModel):
    window: str = "15m"
    resolution_window: str = "10m"


class StorageConfig(BaseModel):
    database_url: str = "postgresql://detection:detection2026@localhost:5432/detection_db"
    retention_days: int = 30


class PrometheusConfig(BaseModel):
    url: str = "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"


class LokiConfig(BaseModel):
    url: str = "http://loki.observability.svc.cluster.local:3100"


class AppConfig(BaseModel):
    detection: DetectionConfig = DetectionConfig()
    feature_engine: FeatureEngineConfig = FeatureEngineConfig()
    detectors: DetectorsConfig = DetectorsConfig()
    deduplication: DeduplicationConfig = DeduplicationConfig()
    storage: StorageConfig = StorageConfig()
    prometheus: PrometheusConfig = PrometheusConfig()
    loki: LokiConfig = LokiConfig()


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = os.environ.get(
            "DETECTION_CONFIG_PATH",
            str(Path(__file__).parent.parent.parent / "config" / "detection-config.yaml"),
        )

    config_dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config_dict = yaml.safe_load(f) or {}

    # Environment variable overrides
    env_overrides = {
        "PROMETHEUS_URL": ("prometheus", "url"),
        "LOKI_URL": ("loki", "url"),
        "DATABASE_URL": ("storage", "database_url"),
        "DETECTION_INTERVAL": ("detection", "interval"),
        "DETECTION_NAMESPACE": ("detection", "namespace"),
    }

    for env_var, (section, key) in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            config_dict.setdefault(section, {})[key] = value

    return AppConfig(**config_dict)


# Singleton
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global configuration singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
