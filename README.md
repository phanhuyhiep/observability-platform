# AI-Powered Observability & Incident Intelligence Platform

> Nền tảng giám sát Kubernetes/microservices thông minh – phát hiện bất thường, tương quan sự kiện, suy luận nguyên nhân gốc và quản lý incident tự động.

---

## Tổng quan

Hệ thống được thiết kế như một nền tảng **Observability Intelligence** dành cho môi trường Kubernetes và kiến trúc microservices. Khác với mô hình monitoring truyền thống chỉ dựa trên ngưỡng cố định, hệ thống kết hợp **Metrics**, **Logs** và **Traces** để:

- **Phát hiện bất thường** bằng Rule-based, Statistical (Z-Score, EWMA) và ML/AI
- **Liên kết các triệu chứng** có quan hệ nhân quả với nhau
- **Xác định nguyên nhân gốc** (Root Cause Analysis) tự động
- **Tạo Incident** có ngữ cảnh đầy đủ thay vì gửi hàng chục alert rời rạc
- **Gửi thông báo** có khả năng hành động qua Slack/Telegram

### Bài toán giải quyết

| Vấn đề | Giải pháp |
|---|---|
| **Alert fatigue** – 1 lỗi hạ tầng tạo hàng trăm alert | Correlation Engine gộp thành 1 Incident |
| **Thiếu ngữ cảnh** – alert chỉ nói metric vượt ngưỡng | RCA Engine cung cấp root cause + evidence + blast radius |
| **Ngưỡng tĩnh** – không phù hợp workload seasonal | Dynamic Baseline + EWMA thích ứng theo pattern |
| **Điều tra thủ công** – SRE phải mở Grafana, log, trace | Evidence Aggregation + LLM Summary tự động |
| **Khó xác định phạm vi ảnh hưởng** | Service Dependency Graph + Blast Radius Calculation |

---

## Kiến trúc tổng thể

```
Kubernetes Cluster / Applications
            |
    +-------+--------+--------+
    |       |        |        |
 Metrics   Logs    Traces   Events
    |       |        |        |
Prometheus Loki  OpenTelemetry K8s API
    \       |        |       /
     +------ Data Normalization ------+
                    |
              Feature Engine
                    |
        +-----------+-----------+
        |           |           |
      Rules    Statistical     ML/AI
        \           |           /
         +---- Anomaly Events --+
                    |
            Correlation Engine
                    |
        Service Graph / Temporal Graph
                    |
             RCA / Root Cause
                    |
             Incident Engine
                    |
       +------------+-------------+
       |            |             |
    Grafana    Alertmanager   Slack/Telegram
```

---

## Roadmap – 5 Phases

| Phase | Tên | Trạng thái | Mô tả |
|:---:|---|:---:|---|
| 1 | **Observability Foundation** | ✅ Hoàn thành | Prometheus, Loki, Tempo, OTel Collector, Grafana |
| 2 | **Anomaly Detection** | ✅ Hoàn thành | Feature Engine, Rule/Z-Score/EWMA Detectors, PostgreSQL |
| 3 | **Correlation Engine** | 🔲 Chưa bắt đầu | Temporal/Topology Correlation, Service Graph, Incident Grouping |
| 4 | **Root Cause Analysis** | 🔲 Chưa bắt đầu | RCA Scoring, Blast Radius, Evidence Aggregation, Notifications |
| 5 | **AI Enhancement** | 🔲 Chưa bắt đầu | Isolation Forest, Dynamic Baseline, LLM Summarization |

> Chi tiết từng phase xem tại [docs/roadmap/](docs/roadmap/)

---

## Cấu trúc dự án

```
observability-platform/
│
├── infrastructure/                # Phase 1 – Observability Stack
│   ├── metrics/                   #   Prometheus + kube-prometheus-stack
│   ├── logging/                   #   Loki + Promtail
│   ├── tracing/                   #   Tempo + OTel Collector
│   └── grafana/                   #   Grafana dashboards
│
├── detection/                     # Phase 2 – Anomaly Detection ✅
│   ├── src/
│   │   ├── main.py               #   FastAPI + APScheduler
│   │   ├── orchestrator.py       #   Detection loop coordinator
│   │   ├── features/             #   Feature Engine (metric, latency, log)
│   │   ├── detectors/            #   Rule, Z-Score, EWMA detectors
│   │   ├── baseline/             #   Baseline calculator + storage
│   │   ├── query/                #   Prometheus + Loki HTTP clients
│   │   └── api/                  #   REST API endpoints
│   ├── rules/                    #   YAML detection rules
│   ├── migrations/               #   PostgreSQL schema
│   ├── k8s/                      #   Kubernetes manifests
│   ├── Dockerfile
│   └── docker-compose.yaml
│
├── correlation/                   # Phase 3 – Correlation Engine
│   └── (planned)                 #   Temporal, Topology, Deployment correlators
│
├── services/                      # Phase 4 – RCA & Incident Engine
│   └── (planned)                 #   Root Cause Scoring, Blast Radius, Notifications
│
├── incident-engine/               # Phase 4 – Incident Lifecycle
│   └── (planned)                 #   State machine, auto-resolve, timeline
│
├── ai/                            # Phase 5 – ML/AI Enhancement
│   └── (planned)                 #   Isolation Forest, Forecasting, LLM
│
├── docs/
│   ├── AI_Observability_Incident_Intelligence_Technical_Design.md
│   └── roadmap/
│       ├── phase-1-observability-foundation.md
│       ├── phase-2-anomaly-detection.md
│       ├── phase-3-correlation-engine.md
│       ├── phase-4-root-cause-analysis.md
│       └── phase-5-ai-enhancement.md
│
└── deployments/                   # Kubernetes deployment manifests
```

---

## Phase 1 – Observability Foundation ✅

Stack giám sát đã được deploy trên Kubernetes:

| Component | Công cụ | Chức năng |
|---|---|---|
| Metrics | **Prometheus** (kube-prometheus-stack) | Thu thập CPU, memory, latency, error rate |
| Logs | **Loki** + Promtail | Aggregation logs từ tất cả pods |
| Traces | **Tempo** + OTel Collector | Distributed tracing giữa microservices |
| Dashboard | **Grafana** | Visualization + datasource tích hợp |

```bash
# Verify stack
kubectl get pods -n observability
```

---

## Phase 2 – Anomaly Detection ✅

Detection Service chạy trong cluster, tự động phát hiện bất thường mỗi 2 phút.

### Detection Pipeline

```
Prometheus/Loki → Query Layer → Feature Engine → Detectors → PostgreSQL
                                     ↓               ↓
                                Baselines        Rule / Z-Score / EWMA
```

### Built-in Detection Rules

| Rule | Metric | Threshold | Severity |
|---|---|---|---|
| High CPU Usage | `cpu_usage_percent` | > 90% | warning |
| High Memory Usage | `memory_usage_percent` | > 90% | warning |
| High P95 Latency | `p95_latency` | > 2000ms | high |
| HTTP 5xx Spike | `http_5xx_rate` | > 5/min | critical |
| Pod Restart | `pod_restart_count` | ≥ 1 | warning |
| OOMKilled | `oomkill_count` | ≥ 1 | critical |
| Error Log Count | `error_count` | > 50/5min | warning |

### API Endpoints

```
GET    /api/v1/health                    # Service health
GET    /api/v1/anomalies                 # List anomalies
GET    /api/v1/anomalies/{id}            # Get anomaly detail
PATCH  /api/v1/anomalies/{id}            # Update status
GET    /api/v1/rules                     # List rules
POST   /api/v1/rules                     # Create rule
DELETE /api/v1/rules/{id}                # Delete rule
GET    /api/v1/baselines                 # List baselines
```

> Xem chi tiết tại [detection/README.md](detection/README.md)

---

## Yêu cầu hệ thống

### Infrastructure

| Component | Version | Bắt buộc |
|---|---|---|
| Kubernetes | 1.25+ | ✅ |
| Helm | 3.x | ✅ |
| Docker | 20.x+ | ✅ |
| kubectl | 1.25+ | ✅ |
| Minikube (lab) | 1.30+ | Tùy chọn |

### Observability Stack (Phase 1)

| Component | Version |
|---|---|
| Prometheus | 2.x (kube-prometheus-stack) |
| Loki | 2.x+ |
| Tempo | 2.x+ |
| Grafana | 10.x+ |
| OTel Collector | 0.90+ |

---

## Quick Start

### 1. Clone repository

```bash
git clone https://github.com/phanhuyhiep/observability-platform.git
cd observability-platform
```

### 2. Deploy Observability Stack (Phase 1)

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

# Create namespace
kubectl create namespace observability

# Deploy Prometheus
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n observability -f infrastructure/metrics/prometheus-values.yaml

# Deploy Loki + Promtail
helm install loki grafana/loki -n observability -f infrastructure/logging/loki-values.yaml
helm install promtail grafana/promtail -n observability -f infrastructure/logging/promtail-values.yaml

# Deploy Tempo + OTel Collector
helm install tempo grafana/tempo -n observability -f infrastructure/tracing/tempo-values.yaml
helm install otel-collector open-telemetry/opentelemetry-collector \
  -n observability -f infrastructure/tracing/otel-collector-values.yaml

# Deploy Grafana (nếu chưa có trong kube-prometheus-stack)
helm install grafana grafana/grafana -n observability -f infrastructure/grafana/grafana-values.yaml

# Verify
kubectl get pods -n observability
```

### 3. Deploy Detection Service (Phase 2)

```bash
cd detection/

# Build image (Minikube)
eval $(minikube docker-env)
docker build -t detection-service:latest .

# Create DB init ConfigMap
kubectl create configmap detection-db-init \
  --from-file=001_create_anomaly_events.sql=migrations/001_create_anomaly_events.sql \
  -n observability

# Deploy
kubectl apply -f k8s/detection-deployment.yaml

# Run migration (if needed)
kubectl exec -i deployment/detection-postgres -n observability -- \
  psql -U detection -d detection_db < migrations/001_create_anomaly_events.sql

# Verify
kubectl get pods -n observability | grep detection
kubectl logs -n observability deployment/detection-service --tail=10

# Access API
kubectl port-forward svc/detection-service 8080:8080 -n observability --address 0.0.0.0 &
curl http://localhost:8080/api/v1/health
```

### 4. Local Development (Docker Compose)

```bash
cd detection/

# Port-forward Prometheus & Loki
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n observability &
kubectl port-forward svc/loki 3100:3100 -n observability &

# Start locally
docker-compose up -d

# API: http://localhost:8080
# Swagger: http://localhost:8080/docs
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API Framework | FastAPI |
| Scheduler | APScheduler |
| Database | PostgreSQL 16 |
| Async DB | asyncpg |
| HTTP Client | httpx |
| Math/Stats | NumPy |
| Metrics Query | PromQL (Prometheus HTTP API) |
| Log Query | LogQL (Loki HTTP API) |
| Container | Docker (multi-stage) |
| Orchestration | Kubernetes / Minikube |
| Package Manager | Helm |

---

## Tài liệu

| Document | Mô tả |
|---|---|
| [Technical Design](docs/AI_Observability_Incident_Intelligence_Technical_Design.md) | Thiết kế kỹ thuật tổng thể |
| [Phase 1 – Observability](docs/roadmap/phase-1-observability-foundation.md) | Nền tảng thu thập telemetry |
| [Phase 2 – Detection](docs/roadmap/phase-2-anomaly-detection.md) | Anomaly Detection Engine |
| [Phase 3 – Correlation](docs/roadmap/phase-3-correlation-engine.md) | Correlation & Incident Grouping |
| [Phase 4 – RCA](docs/roadmap/phase-4-root-cause-analysis.md) | Root Cause Analysis & Notifications |
| [Phase 5 – AI](docs/roadmap/phase-5-ai-enhancement.md) | ML/AI Enhancement |
| [Detection Service](detection/README.md) | Hướng dẫn deploy & API reference |

---

## License

Private repository – Internal use only.
