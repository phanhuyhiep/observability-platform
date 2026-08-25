# TÀI LIỆU THIẾT KẾ KỸ THUẬT

## AI-Powered Observability, Anomaly Detection & Incident Intelligence Platform

| | |
|---|---|
| **Phiên bản** | 1.0 |
| **Mục tiêu** | Thiết kế nền tảng giám sát Kubernetes/microservices có khả năng phát hiện bất thường, tương quan sự kiện, suy luận nguyên nhân gốc và quản lý incident. |

---

## 1. Tổng quan hệ thống

Hệ thống được thiết kế như một nền tảng **Observability Intelligence** dành cho môi trường Kubernetes và kiến trúc microservices. Khác với mô hình monitoring truyền thống chỉ dựa trên ngưỡng cố định, hệ thống kết hợp **Metrics**, **Logs** và **Traces** để phát hiện bất thường, liên kết các triệu chứng có quan hệ với nhau và tạo ra Incident có ngữ cảnh.

### 1.1. Bài toán

- **Alert fatigue**: một lỗi hạ tầng có thể tạo ra hàng chục hoặc hàng trăm alert.
- **Thiếu ngữ cảnh**: alert chỉ cho biết một metric vượt ngưỡng, không giải thích quan hệ nguyên nhân – hậu quả.
- **Điều tra thủ công**: SRE/DevOps phải tự mở Grafana, log và trace để xác định root cause.
- **Ngưỡng tĩnh** không phù hợp với workload có tính mùa vụ hoặc biến động theo thời gian.
- **Khó xác định phạm vi ảnh hưởng** của một lỗi trong hệ thống microservices.

### 1.2. Mục tiêu

- Thu thập và chuẩn hóa Metrics, Logs, Traces, Kubernetes Events và Deployment Events.
- Phát hiện anomaly bằng Rule-based, Statistical và ML/AI.
- Xây dựng Service Dependency Graph.
- Correlation nhiều anomaly thành một nhóm sự kiện có ý nghĩa.
- Xếp hạng Root Cause dựa trên thời gian, topology và mức độ ảnh hưởng.
- Tạo Incident thay vì gửi alert rời rạc.
- Gửi thông báo có khả năng hành động qua Grafana/Alertmanager/Slack/Telegram.

---

## 2. Kiến trúc tổng thể

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

## 3. Tầng Data Collection & Observability

| Loại dữ liệu | Nguồn | Mục đích |
|---|---|---|
| Metrics | Prometheus / VictoriaMetrics | CPU, RAM, latency, error rate, traffic |
| Logs | Vector / Fluent Bit → Loki | Exception, error pattern, log burst |
| Traces | OpenTelemetry | Service dependency, critical path, latency propagation |
| Kubernetes Events | Kubernetes API | Pod restart, OOMKilled, scheduling failure |
| Deployment Events | CI/CD, ArgoCD, Kubernetes | Correlation anomaly sau rollout |
| Business Metrics | Application | Success rate, order count, payment success |

### 3.1. Metrics

Các nhóm metric cần theo dõi:

- **Resource**: CPU, memory, disk, network.
- **Application**: request rate, HTTP 4xx/5xx, error rate.
- **Latency**: p50, p95, p99, average latency.
- **Kubernetes**: pod restart, pending pod, OOMKilled, CrashLoopBackOff.
- **Database**: query latency, connection pool, locks, slow query count.
- **Network**: packet loss, retransmission, connection reset.

### 3.2. Logs

Logs được chuẩn hóa thành cấu trúc có thể truy vấn và correlation. Nên ưu tiên structured logging với các trường:

```
timestamp
level
service.name
service.instance.id
namespace
pod
trace_id
span_id
error.type
message
```

### 3.3. Distributed Tracing

Trace là nguồn quan trọng để xây dựng dependency graph. Mỗi request được biểu diễn dưới dạng chuỗi span, từ đó có thể xác định service nào gọi service nào, dependency nào chậm và critical path của request.

---

## 4. Data Normalization & Entity Model

Một trong những thành phần quan trọng nhất là **Entity Model**. Metrics, Logs và Traces chỉ có thể correlation hiệu quả khi chúng được ánh xạ về cùng một thực thể logic.

```
Entity
├── Cluster
├── Namespace
├── Node
├── Deployment
├── Pod
├── Service
├── Application
├── Database
└── External Dependency
```

| Field chuẩn | Ví dụ |
|---|---|
| `cluster` | `production-cluster` |
| `namespace` | `production` |
| `service.name` | `payment-service` |
| `deployment` | `payment-service-v2` |
| `pod` | `payment-7b8c9d` |
| `node` | `worker-01` |
| `trace_id` | `abc123` |
| `timestamp` | `2026-08-24T10:00:00Z` |

---

## 5. Feature Engine

Feature Engine chuyển raw telemetry thành các đặc trưng phục vụ anomaly detection và RCA.

| Nguồn | Feature tiêu biểu |
|---|---|
| Metrics | mean, std, min, max, slope, rate of change, baseline deviation |
| Latency | p50, p95, p99, tail latency increase |
| Logs | error count, exception frequency, new pattern, burst rate |
| Traces | critical path, dependency latency, error span rate |
| Deployment | time since rollout, version change, config change |

Ví dụ feature vector:

```json
{
  "service": "payment-service",
  "metric": "p95_latency",
  "current_value": 4200,
  "baseline_mean": 220,
  "baseline_std": 80,
  "z_score": 49.75,
  "change_rate": 18.2,
  "timestamp": "2026-08-24T10:02:00Z"
}
```

---

## 6. Anomaly Detection Engine

Engine sử dụng chiến lược **hybrid** gồm ba lớp.

### 6.1. Rule-based Detection

```
CPU > 90%
memory_usage > 90%
http_5xx_rate > 5%
p95_latency > 2000ms
pod_restart_count increased
```

**Ưu điểm**: dễ triển khai, minh bạch, phù hợp với các điều kiện đã biết.

### 6.2. Statistical Detection

Các thuật toán phù hợp cho MVP:

- **Z-score**
- **Moving Average**
- **EWMA** (Exponentially Weighted Moving Average)
- **IQR** (Interquartile Range)
- **Change Point Detection**
- **Seasonal Baseline**

Ví dụ:

```
mean = 40
std  = 5
current = 70

z_score = (70 - 40) / 5 = 6

=> anomaly mạnh
```

### 6.3. ML/AI Detection

- **Isolation Forest**: anomaly detection trên nhiều feature.
- **One-Class SVM**: học vùng hành vi bình thường.
- **Autoencoder**: reconstruction error.
- **Forecasting**: dự đoán giá trị kỳ vọng.
- **Clustering**: phát hiện pattern mới hoặc nhóm hành vi bất thường.

> [!IMPORTANT]
> Không nên đưa Deep Learning vào MVP nếu chưa có đủ historical data. Statistical detection + rules thường đem lại giá trị nhanh hơn và dễ giải thích.

---

## 7. Chuẩn hóa Anomaly Event

Tất cả detector nên trả về một schema chung:

```json
{
  "anomaly_id": "uuid",
  "timestamp": "...",
  "entity_type": "service",
  "entity_id": "payment-service",
  "category": "latency",
  "signal": "p95_latency",
  "severity": "high",
  "score": 0.94,
  "baseline": 220,
  "current_value": 4200,
  "detector": "z_score",
  "metadata": {}
}
```

---

## 8. Correlation Engine

Correlation Engine biến nhiều anomaly event thành các nhóm có quan hệ. Đây là thành phần tạo **khác biệt lớn nhất** so với hệ thống alert truyền thống.

### 8.1. Temporal Correlation

```
10:00:01  PostgreSQL latency ↑
10:00:05  payment-service latency ↑
10:00:10  order-service latency ↑
10:00:15  api-gateway 5xx ↑
```

Các event gần nhau về thời gian được đưa vào cùng một **correlation window**.

### 8.2. Topology Correlation

```
API Gateway
    |
    +--> Order Service
    |        |
    |        +--> PostgreSQL
    |
    +--> Payment Service
             |
             +--> PostgreSQL
```

Nếu PostgreSQL là dependency downstream của `payment-service` và anomaly database xuất hiện **trước** anomaly service, mối quan hệ nhân quả có độ tin cậy cao hơn.

### 8.3. Deployment Correlation

```
10:00  Deploy version 2.5
10:02  Error rate ↑
10:03  Pod restart ↑

Possible cause: deployment / configuration change
```

---

## 9. Service Dependency Graph

Graph có thể được xây dựng từ OpenTelemetry spans, Kubernetes service metadata hoặc cấu hình thủ công.

```
Node:
  - service
  - database
  - queue
  - external api

Edge:
  A -> B

Metadata:
  - call count
  - error rate
  - p95 latency
  - dependency type
```

Graph hỗ trợ các thao tác:

- Tìm upstream/downstream của entity bị anomaly.
- Tính blast radius.
- Xác định propagation path.
- Xếp hạng root cause.
- Hiển thị service map cho incident.

---

## 10. Root Cause Analysis Engine

RCA Engine không nên cố gắng kết luận tuyệt đối. Nên trả về danh sách nguyên nhân có **xác suất/confidence**.

### 10.1. Root Cause Scoring

```
RootCauseScore =
    w1 * TemporalScore
  + w2 * TopologyScore
  + w3 * PropagationScore
  + w4 * SeverityScore
  + w5 * DeploymentCorrelation
  + w6 * EvidenceScore
```

Ví dụ kết quả:

```
1. PostgreSQL performance degradation   score: 0.94
2. payment-service saturation           score: 0.46
3. api-gateway issue                    score: 0.18
```

### 10.2. Phân biệt Root Cause và Impact

```
ROOT CAUSE
  PostgreSQL performance degradation

IMPACT
  - payment-service
  - order-service
  - api-gateway

SYMPTOMS
  - DB latency increased
  - p95 latency increased
  - HTTP 5xx increased
```

---

## 11. Incident Engine

Incident Engine chịu trách nhiệm lifecycle của một sự cố và nhận input từ Correlation/RCA Engine.

| Trạng thái | Ý nghĩa |
|---|---|
| `OPEN` | Incident mới được tạo |
| `ACKNOWLEDGED` | Đã có người tiếp nhận |
| `INVESTIGATING` | Đang điều tra |
| `MITIGATED` | Đã giảm tác động |
| `RESOLVED` | Đã khắc phục |
| `CLOSED` | Đóng incident |

Incident object đề xuất:

```json
{
  "incident_id": "INC-1024",
  "title": "PostgreSQL performance degradation",
  "severity": "critical",
  "status": "OPEN",
  "started_at": "...",
  "root_causes": [],
  "impacted_entities": [],
  "anomalies": [],
  "evidence": [],
  "confidence": 0.92
}
```

---

## 12. Notification & Presentation

- **Grafana**: visualization và dashboard.
- **Alertmanager**: routing, grouping, deduplication, silencing.
- **Slack/Telegram**: notification.
- **Incident API/UI**: danh sách incident, timeline và RCA evidence.

> [!WARNING]
> Alertmanager không nên được xem là RCA Engine. Core intelligence nên nằm ở lớp **Correlation + RCA + Incident**.

---

## 13. Luồng xử lý ví dụ

### 13.1. PostgreSQL chậm

```
1. PostgreSQL query latency ↑
2. Database anomaly detected
3. payment-service dependency latency ↑
4. order-service latency ↑
5. api-gateway HTTP 5xx ↑
```

**Correlation Engine:**
- temporal relation: strong
- dependency relation: strong
- propagation direction: PostgreSQL → services → gateway

**RCA:**
- PostgreSQL performance degradation
- confidence: 0.92

**Incident:**
- INC-1024 created

**Notification:**
- One actionable incident instead of four independent alerts

---

## 14. API Architecture đề xuất

| Service | Trách nhiệm |
|---|---|
| Telemetry Ingestion API | Nhận/chuẩn hóa telemetry |
| Feature Service | Tạo feature và baseline |
| Detection Service | Phát hiện anomaly |
| Correlation Service | Nhóm anomaly liên quan |
| Topology Service | Quản lý dependency graph |
| RCA Service | Root cause ranking |
| Incident Service | Incident lifecycle |
| Notification Service | Slack/Telegram/Alertmanager |
| Query API | Dashboard và frontend |

### 14.1. API mẫu

```
POST /api/v1/anomalies
GET  /api/v1/anomalies
GET  /api/v1/incidents
GET  /api/v1/incidents/{id}
POST /api/v1/incidents/{id}/acknowledge
POST /api/v1/incidents/{id}/resolve
GET  /api/v1/topology/services
GET  /api/v1/root-causes/{incidentId}
```

---

## 15. Data Storage đề xuất

| Loại dữ liệu | Storage phù hợp |
|---|---|
| Metrics | Prometheus / VictoriaMetrics |
| Logs | Loki |
| Traces | Tempo / Jaeger |
| Incident metadata | PostgreSQL |
| Correlation graph | PostgreSQL hoặc Graph DB khi cần |
| Feature/baseline | PostgreSQL / ClickHouse |
| Event stream | Kafka/NATS nếu scale lớn |

---

## 16. MVP Roadmap

### Phase 1 – Observability Foundation

1. Deploy Prometheus/VictoriaMetrics.
2. Deploy Loki + Vector/Fluent Bit.
3. Instrument services bằng OpenTelemetry.
4. Chuẩn hóa labels và entity model.

### Phase 2 – Detection

5. Rule Engine.
6. Z-score.
7. Moving average/EWMA.
8. Anomaly event schema.

### Phase 3 – Correlation

9. Time-window correlation.
10. Service dependency graph.
11. Upstream/downstream propagation.
12. Incident grouping.

### Phase 4 – RCA

13. Root cause scoring.
14. Deployment correlation.
15. Blast radius calculation.
16. Evidence aggregation.

### Phase 5 – AI Enhancement

17. Isolation Forest/unsupervised anomaly detection.
18. Forecasting và dynamic baseline.
19. LLM incident summarization.
20. AI-assisted investigation recommendation.

---

## 17. Công nghệ đề xuất

| Layer | Khuyến nghị |
|---|---|
| Container Orchestration | Kubernetes |
| Metrics | Prometheus hoặc VictoriaMetrics |
| Logs | Loki + Vector |
| Tracing | OpenTelemetry + Tempo |
| Backend | Java Spring Boot / Go / Python |
| Streaming | Kafka hoặc NATS khi cần |
| Operational DB | PostgreSQL |
| Cache | Redis |
| Dashboard | Grafana + custom web UI |
| ML | Python, scikit-learn, PyTorch khi cần |

---

## 18. Các nguyên tắc thiết kế quan trọng

- **Không đưa raw telemetry trực tiếp vào ML** nếu chưa chuẩn hóa.
- **Entity identity phải nhất quán** giữa metrics, logs và traces.
- **RCA nên trả confidence score** thay vì khẳng định tuyệt đối.
- **Ưu tiên explainability**: người vận hành phải biết vì sao hệ thống đưa ra kết luận.
- **Tách Detection, Correlation và Incident** thành các concern riêng.
- **Bắt đầu bằng statistical detection** trước khi đầu tư deep learning.
- **Thiết kế event schema versioned** để có thể mở rộng detector.
- **Correlation phải hỗ trợ deduplication và suppression** để tránh tạo incident trùng.

---

## 19. Kết luận

Kiến trúc này hướng tới một nền tảng **AIOps/Intelligent Observability** thay vì một hệ thống monitoring đơn thuần. Giá trị cốt lõi không nằm ở việc thu thập thêm metric hay gửi thêm alert, mà nằm ở việc biến telemetry phân tán thành **Incident có ngữ cảnh**: hệ thống biết điều gì bất thường, những thành phần nào bị ảnh hưởng, quan hệ giữa chúng và nguyên nhân nào có khả năng cao nhất.

```
Traditional Monitoring:
  Metric -> Threshold -> Alert -> Human Investigation

Target Architecture:
  Metrics + Logs + Traces
          -> Feature Engine
          -> Anomaly Detection
          -> Correlation
          -> Root Cause Analysis
          -> Incident
          -> Actionable Notification
```
