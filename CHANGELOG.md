# Changelog

Tất cả thay đổi đáng chú ý của dự án sẽ được ghi nhận tại đây.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [0.3.0] – 2026-09-21

### Added – Phase 3: Correlation Engine & Incident Intelligence
- **Temporal Correlator** (`temporal_correlator.py`): sliding time-window grouping (5m), dynamic extension (15m), and inactivity timeouts.
- **Service Dependency Graph** (`graph_storage.py`, `graph_builder.py`, `graph_query.py`):
  - Directed NetworkX in-memory representation with PostgreSQL persistence.
  - Auto-discovery of caller ➔ callee relationships from OpenTelemetry traces via Tempo.
  - Pre-seeded microservices-demo topology with multi-hop upstream/downstream traversals.
- **Topology Correlator** (`topology_correlator.py`):
  - Cascading failure path identification.
  - Root entity candidate determination (`root_entity_candidate`) and topology confidence scoring.
- **Deployment Correlator** (`deployment_correlator.py`):
  - Proximity correlation with recent deployment/rollout events within a 30-minute window.
  - Webhook endpoint for CI/CD and K8s rollout event ingestion.
- **Incident Engine** (`incident_grouper.py`, `incident_merger.py`, `incident_suppression.py`):
  - Automatic conversion of correlated groups to formal Incidents (`INC-XXXX`).
  - Intelligent incident title generation based on root cause or deployment context.
  - Incident deduplication, merge, and suppression to minimize alert fatigue.
- **REST API** (`routes.py`): full endpoints for `/topology/services`, `/correlations`, `/incidents`, `/deployments`.
- **Database Schema**: migration `002_create_correlation_tables.sql` for nodes, edges, correlation groups, and incidents.
- **Automated Tests**: 17 unit and integration tests passing with 100% coverage.

---

## [Unreleased]

### Added
- Auto baseline computation: tự tính baseline mỗi ~20 phút từ 1h data gần nhất (`orchestrator.py`)
- EWMA warm-up guard: yêu cầu tối thiểu 5 observations trước khi trigger anomaly (`ewma_detector.py`)
- Metadata đầy đủ: lưu detector details (ewma, k_factor, deviation, threshold) vào anomaly metadata
- JSON serialization cho metadata field trong PostgreSQL

### Changed
- EWMA detector không còn false positive khi cold start

---

## [0.2.1] – 2026-08-26

### Fixed
- **Prometheus 400 Bad Request**: chuyển từ ISO timestamp sang Unix timestamp trong query API (`prometheus_client.py`)
- **Service discovery**: ưu tiên `kube_deployment_status_replicas_available` thay vì `up` metric để tìm microservices chính xác hơn
- **Graceful error handling**: range query trả về empty list thay vì crash khi Prometheus trả 400
- **PostgreSQL reserved keyword**: rename column `window` → `time_window` trong `anomaly_events` và `baselines` tables (`001_create_anomaly_events.sql`)
- **Import error**: fix `from .models` → `from ..models` trong `routes.py` (crash container khi start)

---

## [0.2.0] – 2026-08-26

### Added – Phase 2: Anomaly Detection Engine

#### Core Architecture
- **Detection Orchestrator** (`orchestrator.py`): coordinator chạy detection cycle mỗi 2 phút
  - Discover services → Extract features → Run detectors → Deduplicate → Store
- **Feature Engine**: extract statistical features từ raw telemetry
  - `metric_features.py`: CPU, memory stats (mean, std, slope, rate of change, z-score)
  - `latency_features.py`: P50/P95/P99 latency analysis
  - `log_features.py`: error count, burst rate từ Loki
- **Baseline Calculator** (`calculator.py`): tính và lưu baseline statistics (mean, std, min, max) per entity/metric

#### Detectors
- **Rule Detector** (`rule_detector.py`): YAML-driven threshold rules
  - 7 built-in rules: CPU > 90%, Memory > 90%, P95 Latency > 2000ms, 5xx > 5/min, Pod Restart, OOMKilled, Error Logs > 50/5min
- **Z-Score Detector** (`zscore_detector.py`): phát hiện deviation so với baseline
  - Configurable thresholds: warning (3σ), high (5σ), critical (10σ)
- **EWMA Detector** (`ewma_detector.py`): Exponentially Weighted Moving Average trend detection
  - Configurable alpha, k-factor thresholds

#### Query Layer
- **Prometheus Client** (`prometheus_client.py`): PromQL instant + range queries, service discovery
- **Loki Client** (`loki_client.py`): LogQL queries cho error count, burst rate

#### REST API (FastAPI)
- `GET /api/v1/health` – service health + detector status
- `GET /api/v1/anomalies` – list anomalies với filters (entity, severity, category, detector, status)
- `GET /api/v1/anomalies/{id}` – anomaly detail
- `PATCH /api/v1/anomalies/{id}` – update status (resolve, suppress)
- `GET /api/v1/rules` – list detection rules
- `POST /api/v1/rules` – create custom rule
- `DELETE /api/v1/rules/{id}` – delete rule
- `GET /api/v1/baselines` – list baselines

#### Database
- PostgreSQL schema: `anomaly_events`, `baselines`, `detection_rules`
- Migration: `001_create_anomaly_events.sql`

#### Deployment
- `Dockerfile`: Python 3.12-slim multi-stage build
- `docker-compose.yaml`: local development với PostgreSQL
- `detection-deployment.yaml`: Kubernetes manifests (Deployment, Service, ConfigMap, PVC)
- `detection-config.yaml`: YAML configuration với env var overrides

#### Tests
- `test_detectors.py`: unit tests cho Z-Score + EWMA detectors
- `test_features.py`: unit tests cho feature extraction

#### Documentation
- `detection/README.md`: deployment guide, API reference, configuration, troubleshooting

---

## [0.1.0] – 2026-08-24

### Added – Phase 1: Observability Foundation

#### Infrastructure
- **Prometheus** (kube-prometheus-stack): metrics collection cho tất cả K8s workloads
- **Loki** + Promtail: log aggregation từ tất cả pods
- **Tempo**: distributed tracing backend
- **OTel Collector**: OpenTelemetry collector nhận traces OTLP
- **Grafana**: visualization + datasource tích hợp (Prometheus, Loki, Tempo)

#### Configuration
- `infrastructure/metrics/`: Prometheus Helm values
- `infrastructure/logging/`: Loki + Promtail Helm values
- `infrastructure/tracing/`: Tempo + OTel Collector Helm values
- `infrastructure/grafana/`: Grafana Helm values

### Fixed
- **Tempo OOMKilled**: giảm `memBallastSizeMbs` từ 1024 → 64, tăng memory limit lên 768Mi

---

## [0.0.1] – 2026-08-24

### Added
- Project structure và technical design document
- Roadmap 5 phases:
  - Phase 1: Observability Foundation
  - Phase 2: Anomaly Detection
  - Phase 3: Correlation Engine
  - Phase 4: Root Cause Analysis
  - Phase 5: AI Enhancement
- `.gitignore` cho Python/Docker/K8s project
- `README.md` tổng quan dự án
