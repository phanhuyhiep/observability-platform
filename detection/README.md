# Phase 2 – Detection Service: Deployment Guide

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Option 1: Local Development (Docker Compose)](#option-1-local-development-docker-compose)
- [Option 2: Kubernetes Deployment](#option-2-kubernetes-deployment)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [Detection Rules](#detection-rules)
- [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## Overview

The Detection Service is an anomaly detection engine that continuously monitors Kubernetes workloads by querying telemetry data from **Prometheus** (metrics) and **Loki** (logs), extracting statistical features, and running multiple detectors to identify anomalies.

### Key Components

| Component | Role |
|---|---|
| **Feature Engine** | Extracts statistical features (mean, std, slope, z-score) from raw telemetry |
| **Rule Detector** | Evaluates YAML-defined threshold rules (CPU > 90%, OOMKilled, etc.) |
| **Z-Score Detector** | Detects deviations from historical baselines using z-score |
| **EWMA Detector** | Detects trend anomalies using Exponentially Weighted Moving Average |
| **PostgreSQL** | Persists anomaly events, baselines, and custom rules |
| **REST API** | CRUD endpoints for anomalies, rules, and baselines |

### Detection Flow

```
Prometheus/Loki → Query Layer → Feature Engine → Detectors → Anomaly Events → PostgreSQL
                                    ↓                ↓
                               Baselines        Rule/Z-Score/EWMA
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                         │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ Prometheus   │  │    Loki     │  │   Detection Service  │ │
│  │  (metrics)   │  │   (logs)    │  │  ┌────────────────┐  │ │
│  └──────┬───────┘  └──────┬──────┘  │  │ Feature Engine │  │ │
│         │                 │         │  ├────────────────┤  │ │
│         └────────┬────────┘         │  │  Rule Detector │  │ │
│                  │                  │  │ Z-Score Detect. │  │ │
│                  ▼                  │  │  EWMA Detector  │  │ │
│         ┌────────────────┐          │  ├────────────────┤  │ │
│         │  Query Layer   │◄─────────│  │   REST API     │  │ │
│         └────────────────┘          │  └────────┬───────┘  │ │
│                                     └───────────┼──────────┘ │
│                                                 │            │
│                                     ┌───────────▼──────────┐ │
│                                     │    PostgreSQL        │ │
│                                     │  (anomaly_events,    │ │
│                                     │   baselines, rules)  │ │
│                                     └──────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Infrastructure

| Component | Version | Purpose |
|---|---|---|
| **Kubernetes** | 1.25+ | Container orchestration |
| **Prometheus** | 2.x | Metrics collection (kube-prometheus-stack recommended) |
| **Loki** | 2.x+ | Log aggregation |
| **Docker** | 20.x+ | Image building |
| **kubectl** | 1.25+ | Cluster management |

### Required for Local Dev

| Component | Version |
|---|---|
| Docker Compose | 2.x+ |
| Python | 3.12+ (optional, for running tests) |

### Verify Observability Stack

Before deploying, ensure your observability stack is running:

```bash
# Check Prometheus
kubectl get pods -n observability | grep prometheus

# Check Loki
kubectl get pods -n observability | grep loki

# Verify Prometheus is scraping metrics
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n observability &
curl -s http://localhost:9090/api/v1/query?query=up | python3 -m json.tool | head -20
```

---

## Option 1: Local Development (Docker Compose)

Best for development and testing. Runs PostgreSQL locally and connects to an in-cluster Prometheus/Loki via port-forward.

### Step 1: Port-forward Prometheus & Loki

```bash
# In separate terminals or background:
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n observability &
kubectl port-forward svc/loki 3100:3100 -n observability &
```

### Step 2: Configure

Edit `detection/config/detection-config.yaml`:

```yaml
prometheus:
  url: "http://host.docker.internal:9090"    # Docker for Mac/Windows
  # url: "http://172.17.0.1:9090"            # Docker for Linux

loki:
  url: "http://host.docker.internal:3100"
  # url: "http://172.17.0.1:3100"

detection:
  namespace: "default"   # Namespace to monitor
```

### Step 3: Start

```bash
cd detection/
docker-compose up -d

# Check logs
docker-compose logs -f detection-service
```

### Step 4: Verify

```bash
# Health check
curl http://localhost:8080/api/v1/health

# Swagger UI
open http://localhost:8080/docs
```

### Stop

```bash
docker-compose down       # Keep data
docker-compose down -v    # Delete data
```

---

## Option 2: Kubernetes Deployment

Production-ready deployment within the Kubernetes cluster alongside your observability stack.

### Step 1: Build Docker Image

```bash
cd detection/

# For Minikube
eval $(minikube docker-env)
docker build -t detection-service:latest .

# For remote registry (production)
# docker build -t your-registry.com/detection-service:1.0.0 .
# docker push your-registry.com/detection-service:1.0.0
```

### Step 2: Create Database ConfigMap

```bash
kubectl create configmap detection-db-init \
  --from-file=001_create_anomaly_events.sql=migrations/001_create_anomaly_events.sql \
  -n observability
```

### Step 3: Deploy

```bash
kubectl apply -f k8s/detection-deployment.yaml
```

### Step 4: Run Database Migration

If PostgreSQL was already initialized (ConfigMap not picked up automatically):

```bash
kubectl exec -i deployment/detection-postgres -n observability -- \
  psql -U detection -d detection_db < migrations/001_create_anomaly_events.sql
```

### Step 5: Verify Deployment

```bash
# Check pods
kubectl get pods -n observability | grep detection

# Expected output:
# detection-postgres-xxxxx    1/1     Running   0          1m
# detection-service-xxxxx     1/1     Running   0          1m

# Check logs
kubectl logs -n observability deployment/detection-service --tail=20

# Expected: "Detection job complete: X anomalies"
```

### Step 6: Access API

```bash
# Port-forward
kubectl port-forward svc/detection-service 8080:8080 -n observability --address 0.0.0.0 &

# Health check
curl http://localhost:8080/api/v1/health

# Swagger UI
open http://localhost:8080/docs
```

### Updating the Service

```bash
# After code changes:
eval $(minikube docker-env)         # Minikube only
docker build -t detection-service:latest .
kubectl rollout restart deployment/detection-service -n observability
kubectl wait --for=condition=ready pod -l app=detection-service -n observability --timeout=60s
```

---

## Configuration Reference

Configuration is loaded from `config/detection-config.yaml` with environment variable overrides.

### Full Configuration

```yaml
detection:
  interval: "2m"              # Detection cycle interval
  batch_size: 50              # Entities per batch
  namespace: "default"        # Target namespace

feature_engine:
  default_window: "5m"        # Current value window
  baseline_window: "7d"       # Baseline calculation window
  baseline_update_interval: "1h"

detectors:
  rule:
    enabled: true
    rules_path: "./rules/"    # Path to YAML rule files

  zscore:
    enabled: true
    thresholds:
      warning: 3.0            # |z| > 3 → warning
      high: 5.0               # |z| > 5 → high
      critical: 10.0          # |z| > 10 → critical
    min_data_points: 100

  ewma:
    enabled: true
    alpha: 0.1                # Decay factor (0-1, lower = smoother)
    thresholds:
      warning: 2.0
      high: 3.0
      critical: 5.0

deduplication:
  window: "15m"               # Suppress duplicates within window
  resolution_window: "10m"    # Resolve after normal for this duration

storage:
  database_url: "postgresql://detection:detection2026@detection-postgres:5432/detection_db"
  retention_days: 30

prometheus:
  url: "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"

loki:
  url: "http://loki.observability.svc.cluster.local:3100"
```

### Environment Variable Overrides

| Variable | Config Path | Example |
|---|---|---|
| `DATABASE_URL` | `storage.database_url` | `postgresql://user:pass@host:5432/db` |
| `PROMETHEUS_URL` | `prometheus.url` | `http://prometheus:9090` |
| `LOKI_URL` | `loki.url` | `http://loki:3100` |
| `DETECTION_INTERVAL` | `detection.interval` | `5m` |
| `DETECTION_NAMESPACE` | `detection.namespace` | `production` |
| `DETECTION_CONFIG_PATH` | — | `/app/config/detection-config.yaml` |

---

## API Reference

Base URL: `http://<host>:8080/api/v1`

### Anomalies

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/anomalies` | List anomalies with filters |
| `GET` | `/anomalies/{anomaly_id}` | Get anomaly detail |
| `PATCH` | `/anomalies/{anomaly_id}?status=resolved` | Resolve an anomaly |

**Query Parameters for `GET /anomalies`:**

| Param | Type | Default | Description |
|---|---|---|---|
| `entity_type` | string | — | Filter by entity type (service, pod, node) |
| `entity_id` | string | — | Filter by entity name |
| `severity` | string | — | `warning`, `high`, `critical` |
| `category` | string | — | `resource`, `latency`, `error_rate`, `stability` |
| `detector` | string | — | `rule`, `z_score`, `ewma` |
| `status` | string | `active` | `active`, `resolved`, `suppressed` |
| `page` | int | 1 | Page number |
| `limit` | int | 50 | Items per page (max 200) |

**Example Response:**

```json
{
  "items": [
    {
      "anomaly_id": "a1b2c3d4-...",
      "timestamp": "2026-08-26T08:30:00Z",
      "entity": {
        "type": "service",
        "id": "payment-service",
        "namespace": "default"
      },
      "detection": {
        "detector": "z_score",
        "category": "latency",
        "signal": "p95_latency",
        "severity": "critical",
        "score": 1.0,
        "confidence": 0.85
      },
      "values": {
        "current": 4200,
        "baseline_mean": 220,
        "baseline_std": 80,
        "z_score": 49.75
      },
      "status": "active"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 50
}
```

### Rules

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/rules` | List all detection rules |
| `POST` | `/rules` | Create custom rule |
| `DELETE` | `/rules/{rule_id}` | Delete a rule |

**Create Rule Example:**

```bash
curl -X POST http://localhost:8080/api/v1/rules \
  -H "Content-Type: application/json" \
  -d '{
    "id": "rule-custom-latency",
    "name": "Custom Latency Alert",
    "description": "P95 latency exceeds 500ms for checkout-service",
    "metric": "p95_latency",
    "entity_scope": "service",
    "condition": {
      "operator": ">",
      "threshold": 500
    },
    "severity": "high",
    "category": "latency"
  }'
```

### Baselines

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/baselines` | List all baselines |
| `GET` | `/baselines/{entity_id}/{metric}` | Get specific baseline |

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health + detector status |

---

## Detection Rules

### Built-in Rules

| ID | Name | Metric | Threshold | Severity |
|---|---|---|---|---|
| `rule-cpu-high` | High CPU Usage | `cpu_usage_percent` | > 90% | warning |
| `rule-memory-high` | High Memory Usage | `memory_usage_percent` | > 90% | warning |
| `rule-p95-latency` | High P95 Latency | `p95_latency` | > 2000ms | high |
| `rule-5xx-spike` | HTTP 5xx Spike | `http_5xx_rate` | > 5/min | critical |
| `rule-pod-restart` | Pod Restart | `pod_restart_count` | ≥ 1 | warning |
| `rule-oomkilled` | OOMKilled | `oomkill_count` | ≥ 1 | critical |
| `rule-error-count-high` | High Error Logs | `error_count` | > 50/5min | warning |

### Custom Rule Format

Add YAML files to `rules/` directory:

```yaml
rules:
  - id: "rule-custom-example"
    name: "My Custom Rule"
    description: "Trigger when metric exceeds threshold"
    metric: "cpu_usage_percent"       # Metric name to evaluate
    entity_scope: "pod"               # pod, service, node
    condition:
      operator: ">"                   # >, <, >=, <=, ==, increased
      threshold: 85                   # Threshold value
      # min_increase: 1              # For "increased" operator
    duration: "5m"
    severity: "warning"               # warning, high, critical
    category: "resource"              # resource, latency, error_rate, stability
    enabled: true
```

---

## Monitoring & Troubleshooting

### Check Service Health

```bash
curl http://localhost:8080/api/v1/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "healthy",
  "database": "connected",
  "detectors": { "rule": true, "zscore": true, "ewma": true }
}
```

### View Detection Logs

```bash
# Kubernetes
kubectl logs -n observability deployment/detection-service --tail=50 -f

# Docker Compose
docker-compose logs -f detection-service
```

### Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `status: degraded` | DB not connected | Check PostgreSQL pod/container is running |
| `UndefinedTableError` | Tables not created | Run migration SQL manually |
| `No services discovered` | Prometheus can't find services | Check namespace config and Prometheus targets |
| `CrashLoopBackOff` | Python import error | Run `docker run --rm detection-service:latest python -c "from src.main import app"` |
| `0 anomalies` (always) | No services match PromQL queries | Check metric labels in Prometheus match the queries |

### Database Access

```bash
# Kubernetes
kubectl exec -it deployment/detection-postgres -n observability -- \
  psql -U detection -d detection_db

# Useful queries:
SELECT COUNT(*) FROM anomaly_events;
SELECT severity, COUNT(*) FROM anomaly_events GROUP BY severity;
SELECT entity_id, signal, severity, detected_at FROM anomaly_events ORDER BY detected_at DESC LIMIT 10;
SELECT * FROM baselines ORDER BY entity_id;
```

### Running Tests

```bash
cd detection/
pip install -r requirements.txt pytest
pytest tests/ -v
```

---

## Project Structure

```
detection/
├── config/
│   └── detection-config.yaml     # Main configuration
├── k8s/
│   └── detection-deployment.yaml # Kubernetes manifests
├── migrations/
│   └── 001_create_anomaly_events.sql  # DB schema
├── rules/
│   └── default-rules.yaml       # Built-in detection rules
├── src/
│   ├── main.py                  # FastAPI app + APScheduler
│   ├── config.py                # Config loader (YAML + env vars)
│   ├── models.py                # Pydantic models (AnomalyEvent, etc.)
│   ├── orchestrator.py          # Detection loop coordinator
│   ├── api/
│   │   └── routes.py            # REST API endpoints
│   ├── baseline/
│   │   └── calculator.py        # Baseline compute + PostgreSQL storage
│   ├── detectors/
│   │   ├── detector_interface.py # Abstract base class
│   │   ├── rule_detector.py     # YAML rule evaluation
│   │   ├── zscore_detector.py   # Z-score anomaly detection
│   │   └── ewma_detector.py     # EWMA trend detection
│   ├── features/
│   │   ├── metric_features.py   # CPU, memory stats extraction
│   │   ├── latency_features.py  # P50/P95/P99 analysis
│   │   └── log_features.py      # Error count, burst rate
│   └── query/
│       ├── prometheus_client.py  # PromQL HTTP client
│       └── loki_client.py       # LogQL HTTP client
├── tests/
│   ├── test_detectors.py        # Z-Score + EWMA tests
│   └── test_features.py         # Feature extraction tests
├── Dockerfile                   # Multi-stage build
├── docker-compose.yaml          # Local development
├── requirements.txt             # Python dependencies
└── README.md                    # Quick reference
```
