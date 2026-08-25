# Phase 5 – AI Enhancement

> Nâng cao khả năng phát hiện và phân tích bằng ML/AI: unsupervised anomaly detection, dynamic baseline forecasting, LLM summarization, AI-assisted investigation.

| | |
|---|---|
| **Phase** | 5 / 5 |
| **Trạng thái** | Chưa bắt đầu |
| **Phụ thuộc** | Phase 4 hoàn thành, có đủ historical data (≥ 30 ngày) |
| **Output chính** | ML-based anomaly detection, dynamic baselines, LLM incident summary, investigation recommendations |

> [!IMPORTANT]
> Phase này chỉ nên bắt đầu khi đã có đủ historical data từ Phase 1-4. Statistical detection + rules thường đem lại giá trị nhanh hơn và dễ giải thích. ML/AI là lớp bổ sung, không thay thế.

---

## 1. Mục tiêu

- Triển khai Isolation Forest / unsupervised anomaly detection cho multivariate detection.
- Xây dựng Forecasting & Dynamic Baseline thay thế static baseline.
- Tích hợp LLM (Large Language Model) để tạo incident summary tự nhiên.
- AI-assisted investigation: đề xuất hành động điều tra dựa trên pattern lịch sử.

---

## 2. Kiến trúc Phase 5

```
Historical Telemetry Data
         │
    ┌────┴────┐
    │         │
Training   Inference
    │         │
    ▼         ▼
┌─────────────────────┐
│   ML/AI Service      │
│                     │
│  Isolation Forest   │──── Multivariate anomaly detection
│  Forecasting        │──── Prophet / ARIMA / LSTM
│  Dynamic Baseline   │──── Seasonal-aware baselines
│  Pattern Matching   │──── Similar historical incidents
│         │           │
└─────────┤           │
          │           │
┌─────────┴───────────┐
│   LLM Integration    │
│                     │
│  Incident Summary   │──── Natural language summary
│  Investigation Rec. │──── Suggested actions
│  Runbook Matching   │──── Match to known runbooks
└─────────┬───────────┘
          │
          ▼
   Enriched Incidents
```

---

## 3. Tasks chi tiết

### 3.1. Isolation Forest / Unsupervised Anomaly Detection

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.1.1 | Feature matrix builder | Tạo multivariate feature matrix per entity (CPU, memory, latency, error_rate, ...) |
| 3.1.2 | Isolation Forest training pipeline | Train model per service/entity, scheduled retraining |
| 3.1.3 | Inference pipeline | Score new data points, emit anomaly nếu score > threshold |
| 3.1.4 | Model storage & versioning | Lưu trained models, track version |
| 3.1.5 | Comparison với statistical detectors | So sánh precision/recall với Z-score, EWMA |
| 3.1.6 | One-Class SVM (optional) | Alternative unsupervised detector |

**Feature matrix example**:

```
Entity: payment-service
Time: 2026-08-24T10:00:00Z

Features:
  cpu_usage:        0.45
  memory_usage:     0.72
  p95_latency:      4200    ← anomalous
  error_rate:       0.08    ← anomalous
  request_rate:     1200
  db_latency:       2100    ← anomalous
  active_connections: 95

Isolation Forest score: 0.92 → anomaly
```

**Training pipeline**:

```
Schedule: Daily at 02:00 UTC (hoặc weekly)

1. Query historical features (past 30 days)
2. Filter out known anomaly periods
3. Train Isolation Forest per entity
   - n_estimators: 100
   - contamination: 0.01 (1% expected anomaly rate)
4. Validate on holdout set
5. Store model artifact
6. Update model registry
```

---

### 3.2. Forecasting & Dynamic Baseline

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.2.1 | Time-series forecasting | Dự đoán expected value cho metric tại thời điểm T+1 |
| 3.2.2 | Prophet / ARIMA integration | Seasonal decomposition, trend detection |
| 3.2.3 | Dynamic baseline update | Thay static mean/std bằng forecasted value ± confidence interval |
| 3.2.4 | Seasonality handling | Detect daily/weekly patterns (ví dụ: traffic thấp ban đêm) |
| 3.2.5 | Anomaly = actual vs predicted | `anomaly_score = abs(actual - predicted) / predicted_std` |
| 3.2.6 | Fallback to static baseline | Nếu forecast model chưa ready → dùng static baseline |

**Dynamic Baseline concept**:

```
Static baseline:
  mean = 220ms (all time average)
  std  = 80ms

Dynamic baseline (10:00 Monday):
  predicted = 180ms  (Monday morning pattern)
  confidence_interval = [140, 220]

Dynamic baseline (14:00 Friday):
  predicted = 350ms  (Friday afternoon peak)
  confidence_interval = [280, 420]

→ Dynamic baseline giảm false positives cho workload có seasonality
```

---

### 3.3. LLM Incident Summarization

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.3.1 | Prompt engineering | Thiết kế prompt template cho incident summarization |
| 3.3.2 | LLM integration | Tích hợp OpenAI API / self-hosted LLM (Llama, Mistral) |
| 3.3.3 | Incident context builder | Tổng hợp anomalies, RCA, evidence, timeline thành context |
| 3.3.4 | Summary generation | Tạo natural language summary cho incident |
| 3.3.5 | Summary caching | Cache summary, regenerate khi incident updated |
| 3.3.6 | Human review | Summary là suggestion, không phải kết luận cuối cùng |

**Prompt template example**:

```
You are an SRE assistant analyzing a production incident.

Incident: {incident_id}
Severity: {severity}
Started: {started_at}

Root Cause Analysis:
{root_causes_ranked}

Impacted Services:
{impacted_entities}

Evidence Timeline:
{evidence_timeline}

Generate a concise incident summary that:
1. Describes what happened
2. Explains the likely root cause
3. Lists impacted services and blast radius
4. Suggests immediate actions
```

**Output example**:

```
## Incident Summary — INC-1024

At 10:00 UTC, PostgreSQL query latency increased from 45ms to 2100ms
(p95), triggering a cascade of failures across the payment and order
processing pipeline.

**Root Cause (92% confidence):** PostgreSQL performance degradation,
likely caused by lock contention or missing index on a frequently
queried table.

**Impact:** 4 services affected — payment-service (direct),
order-service (direct), api-gateway (indirect), affecting all
user-facing API endpoints.

**Suggested Actions:**
1. Check PostgreSQL slow query log for queries > 1000ms
2. Review pg_stat_activity for lock waits
3. Consider scaling PostgreSQL read replicas
4. Check if recent schema migration added without proper indexing
```

---

### 3.4. AI-Assisted Investigation Recommendation

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.4.1 | Historical incident pattern matching | Tìm incidents tương tự trong lịch sử |
| 3.4.2 | Investigation step recommendation | Đề xuất các bước điều tra dựa trên root cause type |
| 3.4.3 | Runbook matching | Map incident type → existing runbook |
| 3.4.4 | Resolution suggestion | Đề xuất giải pháp dựa trên past resolutions |
| 3.4.5 | Feedback loop | Cho phép SRE đánh giá quality của recommendations |

**Investigation recommendation example**:

```json
{
  "incident_id": "INC-1024",
  "recommendations": [
    {
      "step": 1,
      "action": "Check PostgreSQL slow queries",
      "command": "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10",
      "reason": "Root cause indicates DB performance degradation"
    },
    {
      "step": 2,
      "action": "Check lock contention",
      "command": "SELECT * FROM pg_locks WHERE NOT granted",
      "reason": "High latency often caused by lock waits"
    },
    {
      "step": 3,
      "action": "Review recent deployments",
      "grafana_link": "http://grafana/d/deployments",
      "reason": "Check if schema migration or config change caused regression"
    }
  ],
  "similar_incidents": [
    {
      "incident_id": "INC-0892",
      "date": "2026-07-15",
      "similarity": 0.87,
      "resolution": "Added missing index on payments.user_id column"
    }
  ],
  "runbooks": [
    {
      "name": "PostgreSQL Performance Troubleshooting",
      "url": "https://wiki/runbooks/postgresql-perf"
    }
  ]
}
```

---

## 4. Cấu trúc thư mục

```
ai/
├── README.md
├── anomaly-detection/
│   ├── src/
│   │   ├── isolation_forest.py
│   │   ├── one_class_svm.py
│   │   ├── feature_matrix.py
│   │   ├── training_pipeline.py
│   │   └── inference.py
│   ├── models/                     # Trained model artifacts
│   ├── tests/
│   └── config/
│       └── ml-config.yaml
├── forecasting/
│   ├── src/
│   │   ├── prophet_forecaster.py
│   │   ├── dynamic_baseline.py
│   │   └── seasonality.py
│   ├── tests/
│   └── config/
│       └── forecast-config.yaml
├── llm/
│   ├── src/
│   │   ├── summarizer.py
│   │   ├── investigation_recommender.py
│   │   ├── runbook_matcher.py
│   │   └── prompt_templates/
│   │       ├── incident_summary.j2
│   │       └── investigation_steps.j2
│   ├── tests/
│   └── config/
│       └── llm-config.yaml
├── Dockerfile
└── docker-compose.yaml
```

---

## 5. API Endpoints

```
# ML Detection
GET  /api/v1/ml/anomalies                         # ML-detected anomalies
GET  /api/v1/ml/models                             # List trained models
POST /api/v1/ml/models/retrain                     # Trigger model retraining

# Forecasting
GET  /api/v1/forecast/{entity}/{metric}            # Get forecast for metric
GET  /api/v1/baselines/dynamic/{entity}/{metric}   # Dynamic baseline

# LLM
GET  /api/v1/incidents/{id}/summary                # AI-generated summary
POST /api/v1/incidents/{id}/summary/regenerate      # Force regenerate
GET  /api/v1/incidents/{id}/recommendations         # Investigation recommendations
GET  /api/v1/incidents/{id}/similar                 # Similar historical incidents

# Feedback
POST /api/v1/feedback/recommendations/{id}          # Rate recommendation quality
```

---

## 6. Configuration

```yaml
# ml-config.yaml
isolation_forest:
  enabled: true
  n_estimators: 100
  contamination: 0.01
  retrain_schedule: "0 2 * * *"     # Daily 02:00 UTC
  min_training_days: 30
  features:
    - cpu_usage
    - memory_usage
    - p95_latency
    - error_rate
    - request_rate

forecasting:
  enabled: true
  engine: "prophet"                  # prophet | arima
  forecast_horizon: "1h"
  seasonality:
    daily: true
    weekly: true
  retrain_schedule: "0 3 * * 0"     # Weekly Sunday 03:00

llm:
  enabled: true
  provider: "openai"                 # openai | self-hosted
  model: "gpt-4"
  api_key_env: "OPENAI_API_KEY"
  max_tokens: 1000
  cache_ttl: "30m"
  
  # Self-hosted alternative:
  # provider: "self-hosted"
  # endpoint: "http://llm-service:8080/v1"
  # model: "llama-3-8b"
```

---

## 7. Deliverables

- [ ] Isolation Forest: training pipeline + inference per entity.
- [ ] Dynamic Baseline: Prophet/ARIMA forecasting, seasonal-aware.
- [ ] LLM Summarization: natural language incident summary.
- [ ] Investigation Recommendations: suggested actions, similar incidents, runbook matching.
- [ ] Feedback Loop: SRE có thể rate recommendations.
- [ ] REST API: ML anomalies, forecasts, summaries, recommendations.
- [ ] Model versioning và storage.
- [ ] Comparison report: ML detection vs statistical detection.

---

## 8. Rủi ro & Lưu ý

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Insufficient historical data | Cao | Đợi ≥ 30 ngày data trước khi train, dùng static baseline làm fallback |
| ML model drift | Trung bình | Scheduled retraining, monitor model performance |
| LLM hallucination | Cao | Summary là suggestion, luôn đính kèm raw evidence |
| LLM API cost | Trung bình | Cache summaries, rate limiting, batch requests |
| Explainability | Cao | Isolation Forest có feature importance; luôn show evidence bên cạnh ML score |

---

## 9. Definition of Done

1. ✅ Isolation Forest phát hiện multivariate anomaly mà statistical detector bỏ sót.
2. ✅ Dynamic Baseline xử lý đúng seasonal patterns, giảm false positives.
3. ✅ LLM tạo incident summary chính xác, dễ hiểu cho SRE.
4. ✅ Investigation recommendations hữu ích, match đúng runbooks.
5. ✅ Feedback loop hoạt động, data được thu thập để improve model.
6. ✅ Fallback mechanism: nếu ML/LLM fail → system vẫn hoạt động bình thường với statistical detection.
