"""Configuration loader for RCA Service & Incident Lifecycle."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RCAWeights(BaseModel):
    temporal: float = 0.25
    topology: float = 0.25
    propagation: float = 0.20
    severity: float = 0.10
    deployment: float = 0.10
    evidence: float = 0.10


class RCAConfig(BaseModel):
    evaluation_interval_seconds: int = 30
    weights: RCAWeights = RCAWeights()


class BlastRadiusConfig(BaseModel):
    max_depth: int = 4
    user_facing_services: list[str] = Field(
        default_factory=lambda: ["frontend", "api-gateway", "web", "ingress"]
    )


class EvidenceConfig(BaseModel):
    prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"
    loki_url: str = "http://loki.observability.svc.cluster.local:3100"
    tempo_url: str = "http://tempo.observability.svc.cluster.local:3200"
    lookback_window_minutes: int = 15


class LifecycleConfig(BaseModel):
    auto_resolve_minutes: int = 15


class NotificationConfig(BaseModel):
    enabled: bool = True
    slack_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    alertmanager_url: str | None = None
    dedup_window_minutes: int = 30


class StorageConfig(BaseModel):
    database_url: str = "postgresql://detection:detection2026@detection-postgres:5432/detection_db"


class AppConfig(BaseModel):
    rca: RCAConfig = RCAConfig()
    blast_radius: BlastRadiusConfig = BlastRadiusConfig()
    evidence: EvidenceConfig = EvidenceConfig()
    lifecycle: LifecycleConfig = LifecycleConfig()
    notification: NotificationConfig = NotificationConfig()
    storage: StorageConfig = StorageConfig()


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = os.environ.get(
            "RCA_CONFIG_PATH",
            str(Path(__file__).parent.parent / "config" / "rca-config.yaml"),
        )

    config_dict: dict[str, Any] = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}

    # Environment variable overrides
    env_overrides = {
        "DATABASE_URL": ("storage", "database_url"),
        "PROMETHEUS_URL": ("evidence", "prometheus_url"),
        "LOKI_URL": ("evidence", "loki_url"),
        "TEMPO_URL": ("evidence", "tempo_url"),
        "SLACK_WEBHOOK_URL": ("notification", "slack_webhook_url"),
        "TELEGRAM_BOT_TOKEN": ("notification", "telegram_bot_token"),
        "TELEGRAM_CHAT_ID": ("notification", "telegram_chat_id"),
    }

    for env_var, (section, key) in env_overrides.items():
        val = os.environ.get(env_var)
        if val:
            config_dict.setdefault(section, {})[key] = val

    return AppConfig(**config_dict)


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get global configuration singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
