# Phase 2 – Anomaly Detection

> Xây dựng Detection Engine phát hiện bất thường từ telemetry data, sử dụng chiến lược hybrid: Rule-based + Statistical.

| | |
|---|---|
| **Phase** | 2 / 5 |
| **Trạng thái** | Đang triển khai |
| **Phụ thuộc** | Phase 1 hoàn thành (Metrics, Logs, Traces đã thu thập và chuẩn hóa) |
| **Output chính** | Detection Service phát hiện anomaly và emit standardized Anomaly Events |

---

## 1. Mục tiêu

- Xây dựng Feature Engine chuyển raw telemetry thành feature vectors.
- Triển khai Rule Engine cho các điều kiện bất thường đã biết.
- Triển khai Statistical Detection (Z-score, Moving Average, EWMA) cho baseline-aware detection.
- Chuẩn hóa Anomaly Event schema versioned.
- Lưu trữ và expose Anomaly Events qua API.
- Cung cấp baseline management cho từng service/metric.

---

## 2. Kiến trúc Phase 2

```
Prometheus / Loki / Tempo
         |
    Telemetry Query
         |
   Feature Engine
   ├── Metric Features (mean, std, slope, rate_of_change)
   ├── Latency Features (p50, p95, p99, tail increase)
   ├── Log Features (error_count, burst_rate, new_pattern)
   └── Baseline Calculator
         |
   Detection Engine
   ├── Rule Detector
   ├── Z-Score Detector
   ├── Moving Average Detector
   └── EWMA Detector
         |
   Anomaly Event (standardized schema)
         |
   ┌─────┴─────┐
   │           │
PostgreSQL   Event Bus (internal)
(storage)    (→ Phase 3 Correlation)
```

---

## 3. Tasks chi tiết

### 3.1. Feature Engine

**Mục tiêu**: Chuyển raw metrics/logs thành feature vectors có thể sử dụng cho mọi loại detector.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.1.1 | Thiết kế Feature Engine interface | Interface/contract rõ ràng: input (entity, metric, time_range) → output (feature vector) |
| 3.1.2 | Metric feature extraction | Tính `mean`, `std`, `min`, `max`, `slope`, `rate_of_change` cho sliding window |
| 3.1.3 | Latency feature extraction | Tính `p50`, `p95`, `p99`, `tail_latency_increase` từ histogram metrics |
| 3.1.4 | Log feature extraction | Tính `error_count`, `exception_frequency`, `burst_rate` từ Loki query |
| 3.1.5 | Baseline calculator | Tính và lưu baseline (mean, std) per (entity, metric) với configurable window (7d, 30d) |
| 3.1.6 | Baseline storage | Lưu baseline vào PostgreSQL, update theo schedule |
| 3.1.7 | Feature vector output format | Output theo schema chuẩn (xem bên dưới) |

**Feature Vector schema**:

```json
{
  "entity_type": "service",
  "entity_id": "payment-service",
  "metric": "p95_latency",
  "timestamp": "2026-08-24T10:02:00Z",
  "current_value": 4200,
  "window": "5m",
  "features": {
    "mean": 220,
    "std": 80,
    "min": 180,
    "max": 4200,
    "slope": 18.2,
    "rate_of_change": 19.09,
    "z_score": 49.75,
    "baseline_mean": 220,
    "baseline_std": 80,
    "baseline_window": "7d"
  }
}
```

**Cấu trúc thư mục**:

```
detection/
└── feature-engine/
    ├── README.md
    ├── src/
    │   ├── main.py              # hoặc main.go
    │   ├── features/
    │   │   ├── metric_features.py
    │   │   ├── latency_features.py
    │   │   └── log_features.py
    │   ├── baseline/
    │   │   ├── calculator.py
    │   │   └── storage.py
    │   └── query/
    │       ├── prometheus_client.py
    │       └── loki_client.py
    ├── tests/
    │   ├── test_metric_features.py
    │   ├── test_latency_features.py
    │   └── test_baseline.py
    └── config/
        └── feature-config.yaml
```

---

### 3.2. Rule Engine

**Mục tiêu**: Phát hiện anomaly dựa trên ngưỡng cố định đã biết. Đây là lớp detection đơn giản nhất, cho kết quả ngay lập tức.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.2.1 | Thiết kế rule format (YAML/JSON) | Rule có thể define: metric, operator, threshold, severity, entity scope |
| 3.2.2 | Rule evaluation engine | Load rules, evaluate against feature vectors, emit anomaly events |
| 3.2.3 | Built-in rules | Bộ rules mặc định cho Kubernetes workload |
| 3.2.4 | Custom rule API | CRUD API cho rules: tạo, sửa, xóa, enable/disable |
| 3.2.5 | Rule testing | Dry-run mode: evaluate rule against historical data |

**Rule format đề xuất**:

```yaml
rules:
  - id: "rule-cpu-high"
    name: "High CPU Usage"
    description: "CPU usage exceeds 90%"
    metric: "cpu_usage_percent"
    entity_scope: "pod"
    condition:
      operator: ">"
      threshold: 90
    duration: "5m"            # phải vượt ngưỡng liên tục trong 5 phút
    severity: "warning"
    category: "resource"
    enabled: true

  - id: "rule-5xx-spike"
    name: "HTTP 5xx Spike"
    metric: "http_5xx_rate"
    entity_scope: "service"
    condition:
      operator: ">"
      threshold: 5
    duration: "2m"
    severity: "critical"
    category: "error_rate"
    enabled: true

  - id: "rule-pod-restart"
    name: "Pod Restart Detected"
    metric: "pod_restart_count"
    entity_scope: "pod"
    condition:
      operator: "increased"
      min_increase: 1
    duration: "0m"
    severity: "warning"
    category: "stability"
    enabled: true

  - id: "rule-p95-latency"
    name: "High P95 Latency"
    metric: "p95_latency_ms"
    entity_scope: "service"
    condition:
      operator: ">"
      threshold: 2000
    duration: "3m"
    severity: "high"
    category: "latency"
    enabled: true

  - id: "rule-memory-high"
    name: "High Memory Usage"
    metric: "memory_usage_percent"
    entity_scope: "pod"
    condition:
      operator: ">"
      threshold: 90
    duration: "5m"
    severity: "warning"
    category: "resource"
    enabled: true

  - id: "rule-oomkilled"
    name: "OOMKilled Detected"
    metric: "oomkill_count"
    entity_scope: "pod"
    condition:
      operator: "increased"
      min_increase: 1
    duration: "0m"
    severity: "critical"
    category: "stability"
    enabled: true
```

---

### 3.3. Statistical Detection – Z-Score

**Mục tiêu**: Phát hiện anomaly khi giá trị hiện tại lệch đáng kể so với baseline thống kê.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.3.1 | Implement Z-score detector | `z = (current - mean) / std`, emit anomaly nếu `|z| > threshold` |
| 3.3.2 | Configurable Z-score threshold | Default: `z > 3` (warning), `z > 5` (high), `z > 10` (critical) |
| 3.3.3 | Áp dụng cho multiple metrics | CPU, memory, latency, error rate, request rate |
| 3.3.4 | Handle edge cases | std = 0 (constant metric), insufficient data, cold start |
| 3.3.5 | Unit tests với synthetic data | Test correct z-score calculation, severity mapping |

**Thuật toán**:

```
Input:
  current_value = 4200
  baseline_mean = 220
  baseline_std  = 80

z_score = (current_value - baseline_mean) / baseline_std
z_score = (4200 - 220) / 80 = 49.75

Severity mapping:
  |z| > 3   → warning
  |z| > 5   → high
  |z| > 10  → critical

Result: severity = critical, score = min(|z| / 10, 1.0) = 1.0
```

---

### 3.4. Statistical Detection – Moving Average / EWMA

**Mục tiêu**: Phát hiện trend bất thường bằng cách so sánh giá trị hiện tại với giá trị trung bình trượt.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.4.1 | Implement Simple Moving Average (SMA) detector | SMA với configurable window size |
| 3.4.2 | Implement EWMA detector | EWMA với configurable alpha (decay factor) |
| 3.4.3 | Deviation threshold | Emit anomaly khi `abs(current - ewma) > k * ewma_std` |
| 3.4.4 | Áp dụng cho latency và error rate | Latency trend, error rate trend |
| 3.4.5 | Comparison tests | So sánh SMA vs EWMA trên cùng synthetic dataset |

**EWMA formula**:

```
EWMA_t = α * x_t + (1 - α) * EWMA_{t-1}

α = 2 / (span + 1)    # ví dụ span=20 → α=0.095

Anomaly condition:
  deviation = |current - EWMA_t|
  if deviation > k * EWMA_std → anomaly
  
  k = 2 → warning
  k = 3 → high
  k = 5 → critical
```

---

### 3.5. Anomaly Event Schema

**Mục tiêu**: Định nghĩa schema chuẩn cho tất cả anomaly event, bất kể detector nào tạo ra.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.5.1 | Định nghĩa Anomaly Event schema v1 | Schema versioned, document mọi field |
| 3.5.2 | Tạo database table/model | PostgreSQL table cho anomaly events |
| 3.5.3 | Anomaly Event API | `POST /api/v1/anomalies`, `GET /api/v1/anomalies` |
| 3.5.4 | Query & filter | Filter by entity, severity, category, time range, detector |
| 3.5.5 | TTL / retention | Auto-cleanup events cũ hơn configurable threshold (ví dụ 30 ngày) |

**Anomaly Event schema v1**:

```json
{
  "anomaly_id": "a1b2c3d4-uuid",
  "version": 1,
  "timestamp": "2026-08-24T10:02:00Z",
  "detected_at": "2026-08-24T10:02:05Z",

  "entity": {
    "type": "service",
    "id": "payment-service",
    "namespace": "production",
    "cluster": "production-cluster"
  },

  "detection": {
    "detector": "z_score",
    "category": "latency",
    "signal": "p95_latency",
    "severity": "critical",
    "score": 0.94,
    "confidence": 0.92
  },

  "values": {
    "current": 4200,
    "baseline_mean": 220,
    "baseline_std": 80,
    "z_score": 49.75,
    "threshold_used": 3.0
  },

  "context": {
    "window": "5m",
    "baseline_window": "7d",
    "rule_id": null
  },

  "metadata": {
    "labels": {
      "pod": "payment-7b8c9d",
      "deployment": "payment-service-v2"
    }
  },

  "status": "active"
}
```

**Database schema**:

```sql
CREATE TABLE anomaly_events (
    anomaly_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         INT NOT NULL DEFAULT 1,
    timestamp       TIMESTAMPTZ NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Entity
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(255) NOT NULL,
    namespace       VARCHAR(255),
    cluster         VARCHAR(255),

    -- Detection
    detector        VARCHAR(50) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    signal          VARCHAR(100) NOT NULL,
    severity        VARCHAR(20) NOT NULL,
    score           DECIMAL(5,4),
    confidence      DECIMAL(5,4),

    -- Values
    current_value   DOUBLE PRECISION,
    baseline_mean   DOUBLE PRECISION,
    baseline_std    DOUBLE PRECISION,
    z_score         DOUBLE PRECISION,

    -- Context
    rule_id         VARCHAR(100),
    window          VARCHAR(20),
    baseline_window VARCHAR(20),

    -- Status
    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    -- Metadata (JSONB for flexibility)
    metadata        JSONB,

    -- Indexes
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_anomaly_entity ON anomaly_events(entity_type, entity_id);
CREATE INDEX idx_anomaly_timestamp ON anomaly_events(timestamp);
CREATE INDEX idx_anomaly_severity ON anomaly_events(severity);
CREATE INDEX idx_anomaly_category ON anomaly_events(category);
CREATE INDEX idx_anomaly_status ON anomaly_events(status);
CREATE INDEX idx_anomaly_detector ON anomaly_events(detector);
```

---

### 3.6. Detection Service

**Mục tiêu**: Service chạy detection loop, orchestrate Feature Engine + Detectors, output Anomaly Events.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.6.1 | Detection scheduler | Chạy detection cycle mỗi 1-5 phút (configurable) |
| 3.6.2 | Multi-detector orchestration | Chạy Rule + Z-score + EWMA cho mỗi entity/metric |
| 3.6.3 | Deduplication | Không tạo anomaly event trùng nếu anomaly vẫn đang active |
| 3.6.4 | Anomaly lifecycle | Active → Resolved khi metric trở về normal |
| 3.6.5 | Health check & metrics | `/health`, `/metrics` cho self-monitoring |
| 3.6.6 | Configuration hot-reload | Update rules, thresholds không cần restart |

**Detection loop flow**:

```
Every detection_interval:
  1. Fetch entity registry (services, pods, databases)
  2. For each (entity, metric):
     a. Query current values from Prometheus/Loki
     b. Feature Engine → feature vector
     c. Run all enabled detectors:
        - Rule Detector
        - Z-Score Detector
        - EWMA Detector
     d. Collect anomaly results
     e. Deduplicate against active anomalies
     f. Store new anomaly events → PostgreSQL
     g. Emit events → internal event bus
  3. Resolve expired anomalies
  4. Update detection metrics
```

---

## 4. Cấu trúc thư mục tổng thể Phase 2

```
detection/
├── README.md
├── feature-engine/
│   ├── src/
│   │   ├── features/
│   │   │   ├── metric_features.py
│   │   │   ├── latency_features.py
│   │   │   └── log_features.py
│   │   ├── baseline/
│   │   │   ├── calculator.py
│   │   │   └── storage.py
│   │   └── query/
│   │       ├── prometheus_client.py
│   │       └── loki_client.py
│   └── tests/
├── detectors/
│   ├── src/
│   │   ├── rule_detector.py
│   │   ├── zscore_detector.py
│   │   ├── moving_average_detector.py
│   │   ├── ewma_detector.py
│   │   └── detector_interface.py
│   └── tests/
├── service/
│   ├── src/
│   │   ├── main.py
│   │   ├── scheduler.py
│   │   ├── orchestrator.py
│   │   ├── deduplication.py
│   │   └── api/
│   │       ├── routes.py
│   │       └── models.py
│   └── tests/
├── rules/
│   └── default-rules.yaml
├── migrations/
│   └── 001_create_anomaly_events.sql
├── config/
│   └── detection-config.yaml
├── Dockerfile
└── docker-compose.yaml
```

---

## 5. API Endpoints

```
# Anomaly Events
POST   /api/v1/anomalies                    # Internal: detector tạo anomaly
GET    /api/v1/anomalies                    # List anomalies (filter, pagination)
GET    /api/v1/anomalies/{anomaly_id}       # Get anomaly detail
PATCH  /api/v1/anomalies/{anomaly_id}       # Update status (resolve, suppress)

# Rules
GET    /api/v1/rules                        # List all rules
POST   /api/v1/rules                        # Create custom rule
PUT    /api/v1/rules/{rule_id}              # Update rule
DELETE /api/v1/rules/{rule_id}              # Delete rule
POST   /api/v1/rules/{rule_id}/test         # Dry-run rule against historical data

# Baselines
GET    /api/v1/baselines                    # List baselines
GET    /api/v1/baselines/{entity}/{metric}  # Get baseline for specific entity/metric
POST   /api/v1/baselines/recalculate        # Trigger baseline recalculation

# Health
GET    /health                              # Service health
GET    /metrics                             # Prometheus metrics
```

---

## 6. Configuration

```yaml
# detection-config.yaml
detection:
  interval: "2m"                    # Detection cycle interval
  batch_size: 50                    # Entities processed per batch

feature_engine:
  default_window: "5m"              # Current value window
  baseline_window: "7d"             # Baseline calculation window
  baseline_update_interval: "1h"    # How often to recalculate baselines

detectors:
  rule:
    enabled: true
    rules_path: "./rules/"

  zscore:
    enabled: true
    thresholds:
      warning: 3.0
      high: 5.0
      critical: 10.0
    min_data_points: 100            # Minimum baseline data points

  ewma:
    enabled: true
    alpha: 0.1                      # Decay factor
    thresholds:
      warning: 2.0
      high: 3.0
      critical: 5.0

deduplication:
  window: "15m"                     # Suppress duplicate anomaly within this window
  resolution_window: "10m"          # Mark anomaly resolved after normal for this duration

storage:
  database_url: "postgresql://..."
  retention_days: 30

prometheus:
  url: "http://prometheus:9090"

loki:
  url: "http://loki:3100"
```

---

## 7. Deliverables

- [ ] Feature Engine: tính feature vectors từ Prometheus và Loki.
- [ ] Baseline Calculator: tính và lưu baseline per (entity, metric).
- [ ] Rule Detector: evaluate rules từ YAML config.
- [ ] Z-Score Detector: phát hiện anomaly dựa trên baseline deviation.
- [ ] EWMA Detector: phát hiện trend anomaly.
- [ ] Anomaly Event schema v1: document và implement.
- [ ] PostgreSQL storage: table, indexes, migration scripts.
- [ ] Detection Service: scheduler, orchestrator, deduplication.
- [ ] REST API: anomaly CRUD, rule management, baseline query.
- [ ] Unit tests cho từng detector với synthetic data.
- [ ] Integration test: end-to-end từ metric query → anomaly event.

---

## 8. Rủi ro & Lưu ý

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Cold start: chưa có baseline khi deploy lần đầu | Cao | Cho phép configurable warm-up period, chỉ chạy Rule detector trong giai đoạn đầu |
| Query Prometheus quá nhiều gây tải | Trung bình | Batch queries, sử dụng recording rules, rate limiting |
| False positives cao | Trung bình | Cho phép tuning thresholds per metric, suppression rules |
| Metric cardinality cao (nhiều pods) | Trung bình | Aggregate theo service trước khi detect, không detect per-pod cho tất cả metrics |
| Baseline bị skew bởi incident trước đó | Thấp | Exclude anomaly periods khỏi baseline calculation |

---

## 9. Definition of Done

Phase 2 hoàn thành khi:

1. ✅ Feature Engine trả về feature vectors chính xác cho metrics và logs.
2. ✅ Rule Detector phát hiện đúng các vi phạm ngưỡng.
3. ✅ Z-Score Detector phát hiện deviation so với baseline.
4. ✅ EWMA Detector phát hiện trend bất thường.
5. ✅ Anomaly Events được lưu vào PostgreSQL với schema chuẩn.
6. ✅ API hoạt động: list, filter, query anomaly events.
7. ✅ Deduplication hoạt động: không tạo event trùng.
8. ✅ Detection loop chạy ổn định mỗi 2 phút.
9. ✅ Unit tests pass, coverage ≥ 80% cho detectors.
