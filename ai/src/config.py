"""Configuration loader for AI Enhancement Service."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8083


class StorageConfig(BaseModel):
    database_url: str = "postgresql://detection:detection2026@detection-postgres:5432/detection_db"


class TelemetryConfig(BaseModel):
    prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"
    loki_url: str = "http://loki.observability.svc.cluster.local:3100"
    tempo_url: str = "http://tempo.observability.svc.cluster.local:3200"
    rca_service_url: str = "http://rca-service:8082"


class IsolationForestConfig(BaseModel):
    enabled: bool = True
    n_estimators: int = 100
    contamination: float = 0.02
    random_state: int = 42
    features: list[str] = Field(
        default_factory=lambda: [
            "cpu_usage",
            "memory_usage",
            "p95_latency_ms",
            "error_rate",
            "request_throughput",
            "dependency_latency_ms",
        ]
    )
    retrain_interval_hours: int = 24
    min_samples_to_train: int = 20


class ForecastingConfig(BaseModel):
    enabled: bool = True
    horizon_minutes: int = 60
    interval_minutes: int = 5
    daily_seasonality_points: int = 288
    confidence_level: float = 0.95
    anomaly_z_threshold: float = 3.0


class LLMConfig(BaseModel):
    enabled: bool = True
    provider: str = "sre_expert"  # gemini, openai, sre_expert
    model: str = "gemini-1.5-flash"
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1200
    cache_ttl_seconds: int = 1800


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    storage: StorageConfig = StorageConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    isolation_forest: IsolationForestConfig = IsolationForestConfig()
    forecasting: ForecastingConfig = ForecastingConfig()
    llm: LLMConfig = LLMConfig()


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = os.environ.get(
            "AI_CONFIG_PATH",
            str(Path(__file__).parent.parent / "config" / "ai-config.yaml"),
        )

    config_dict: dict[str, Any] = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}

    # Environment variable overrides
    env_overrides = {
        "DATABASE_URL": ("storage", "database_url"),
        "PROMETHEUS_URL": ("telemetry", "prometheus_url"),
        "LOKI_URL": ("telemetry", "loki_url"),
        "TEMPO_URL": ("telemetry", "tempo_url"),
        "RCA_SERVICE_URL": ("telemetry", "rca_service_url"),
        "LLM_PROVIDER": ("llm", "provider"),
        "GEMINI_API_KEY": ("llm", "gemini_api_key"),
        "OPENAI_API_KEY": ("llm", "openai_api_key"),
        "AI_PORT": ("server", "port"),
    }

    for env_var, (section, key) in env_overrides.items():
        val = os.environ.get(env_var)
        if val is not None:
            if key == "port":
                try:
                    val = int(val)
                except ValueError:
                    continue
            config_dict.setdefault(section, {})[key] = val

    return AppConfig(**config_dict)


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Singleton getter for application configuration."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
