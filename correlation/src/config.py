"""Configuration loader for Correlation Engine."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class CorrelationEvalConfig(BaseModel):
    evaluation_interval_seconds: int = 30


class TemporalConfig(BaseModel):
    window_size_seconds: int = 300
    max_window_extension_seconds: int = 900
    min_anomalies_for_group: int = 2
    inactivity_timeout_seconds: int = 600


class TopologyConfig(BaseModel):
    graph_rebuild_interval_seconds: int = 900
    max_hop_depth: int = 3
    edge_ttl_hours: int = 24
    tempo_url: str = "http://tempo.observability.svc.cluster.local:3200"
    query_range_minutes: int = 60


class DeploymentConfig(BaseModel):
    correlation_window_seconds: int = 1800


class IncidentConfig(BaseModel):
    auto_create: bool = True
    min_anomalies: int = 2
    critical_auto_create: bool = True
    merge_window_seconds: int = 600
    suppression_window_seconds: int = 1800


class StorageConfig(BaseModel):
    database_url: str = "postgresql://detection:detection2026@detection-postgres:5432/detection_db"


class AppConfig(BaseModel):
    correlation: CorrelationEvalConfig = CorrelationEvalConfig()
    temporal: TemporalConfig = TemporalConfig()
    topology: TopologyConfig = TopologyConfig()
    deployment: DeploymentConfig = DeploymentConfig()
    incident: IncidentConfig = IncidentConfig()
    storage: StorageConfig = StorageConfig()


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = os.environ.get(
            "CORRELATION_CONFIG_PATH",
            str(Path(__file__).parent.parent / "config" / "correlation-config.yaml"),
        )

    config_dict: dict[str, Any] = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}

    # Environment variable overrides
    env_overrides = {
        "DATABASE_URL": ("storage", "database_url"),
        "TEMPO_URL": ("topology", "tempo_url"),
        "CORRELATION_INTERVAL": ("correlation", "evaluation_interval_seconds"),
    }

    for env_var, (section, key) in env_overrides.items():
        val = os.environ.get(env_var)
        if val:
            if key.endswith("_seconds") and val.isdigit():
                config_dict.setdefault(section, {})[key] = int(val)
            else:
                config_dict.setdefault(section, {})[key] = val

    return AppConfig(**config_dict)


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get global configuration singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
