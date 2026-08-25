# Phase 4 – Root Cause Analysis (RCA)

> Xếp hạng nguyên nhân gốc cho mỗi Incident, tính blast radius và tổng hợp evidence.

| | |
|---|---|
| **Phase** | 4 / 5 |
| **Trạng thái** | Chưa bắt đầu |
| **Phụ thuộc** | Phase 3 hoàn thành (Correlation Groups, Incidents, Service Graph) |
| **Output chính** | RCA Service trả về ranked root causes với confidence score cho mỗi Incident |

---

## 1. Mục tiêu

- Implement Root Cause Scoring: xếp hạng nguyên nhân theo temporal, topology, propagation, severity, deployment.
- Tính Blast Radius: xác định phạm vi ảnh hưởng từ root cause entity.
- Evidence Aggregation: tổng hợp metrics, logs, traces liên quan làm bằng chứng.
- Hoàn thiện Incident Engine lifecycle: acknowledge, investigate, mitigate, resolve, close.
- Notification: gửi incident có ngữ cảnh qua Alertmanager/Slack/Telegram.

---

## 2. Kiến trúc Phase 4

```
Incident (from Phase 3)
         │
         ▼
┌─────────────────────┐
│     RCA Engine       │
│                     │
│  Temporal Score     │──── Anomaly timestamps ordering
│  Topology Score     │──── Service Dependency Graph
│  Propagation Score  │──── Downstream impact count
│  Severity Score     │──── Anomaly severity/score
│  Deployment Score   │──── Deployment correlation
│  Evidence Score     │──── Supporting logs/traces
│         │           │
│  Root Cause Ranker  │
│         │           │
│  Blast Radius Calc  │
│         │           │
│  Evidence Collector │──── Prometheus + Loki + Tempo
└─────────┬───────────┘
          │
          ▼
   Incident Engine (enriched)
          │
   ┌──────┼──────┐
   │      │      │
Grafana  Slack  Telegram
```

---

## 3. Tasks chi tiết

### 3.1. Root Cause Scoring

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.1.1 | Implement TemporalScore | Entity có anomaly sớm nhất → score cao nhất |
| 3.1.2 | Implement TopologyScore | Entity ở sâu nhất trong dependency chain (upstream-most) → score cao |
| 3.1.3 | Implement PropagationScore | Entity có nhiều downstream bị ảnh hưởng → score cao |
| 3.1.4 | Implement SeverityScore | Anomaly severity + anomaly score |
| 3.1.5 | Implement DeploymentCorrelation | Có deployment gần thời điểm anomaly → boost score |
| 3.1.6 | Implement EvidenceScore | Nhiều signal bất thường (metrics + logs + traces) → score cao |
| 3.1.7 | Weighted scoring combiner | `RootCauseScore = Σ(wi * score_i)`, weights configurable |
| 3.1.8 | Unit tests với scenarios | Test PostgreSQL-down scenario, deployment-caused scenario |

**Scoring formula**:

```
RootCauseScore =
    w1 * TemporalScore          # 0.25 — earliest anomaly
  + w2 * TopologyScore          # 0.25 — upstream-most in graph
  + w3 * PropagationScore       # 0.20 — most downstream impact
  + w4 * SeverityScore          # 0.10 — anomaly severity
  + w5 * DeploymentCorrelation  # 0.10 — deployment proximity
  + w6 * EvidenceScore          # 0.10 — cross-signal evidence
```

**Output example**:

```json
{
  "incident_id": "INC-1024",
  "root_causes": [
    {
      "rank": 1,
      "entity_id": "postgresql",
      "entity_type": "database",
      "description": "PostgreSQL performance degradation",
      "score": 0.94,
      "confidence": 0.92,
      "scores_breakdown": {
        "temporal": 1.0,
        "topology": 0.95,
        "propagation": 0.90,
        "severity": 0.85,
        "deployment": 0.0,
        "evidence": 0.80
      },
      "first_anomaly_at": "2026-08-24T10:00:01Z",
      "anomaly_signals": ["query_latency", "connection_pool_usage"]
    },
    {
      "rank": 2,
      "entity_id": "payment-service",
      "score": 0.46,
      "confidence": 0.40,
      "scores_breakdown": { "..." : "..." }
    }
  ]
}
```

---

### 3.2. Blast Radius Calculation

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.2.1 | Graph traversal từ root cause | BFS/DFS từ root entity, đếm downstream entities |
| 3.2.2 | Impact classification | Direct impact (1 hop) vs indirect impact (2+ hops) |
| 3.2.3 | User-facing impact | Map impacted services → user-facing endpoints |
| 3.2.4 | Blast radius API | `GET /api/v1/root-causes/{incidentId}/blast-radius` |

**Output**:

```json
{
  "root_entity": "postgresql",
  "blast_radius": {
    "direct_impact": ["payment-service", "order-service"],
    "indirect_impact": ["api-gateway", "notification-service"],
    "total_impacted": 4,
    "user_facing_services": ["api-gateway"],
    "estimated_user_impact": "high"
  }
}
```

---

### 3.3. Evidence Aggregation

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.3.1 | Metric evidence collector | Query Prometheus cho metric graphs quanh thời điểm anomaly |
| 3.3.2 | Log evidence collector | Query Loki cho error/exception logs liên quan |
| 3.3.3 | Trace evidence collector | Query Tempo cho error traces liên quan |
| 3.3.4 | K8s event evidence | Collect K8s events (OOMKilled, CrashLoopBackOff, etc.) |
| 3.3.5 | Evidence timeline | Sắp xếp evidence theo thời gian |
| 3.3.6 | Evidence API | `GET /api/v1/incidents/{id}/evidence` |

**Evidence schema**:

```json
{
  "incident_id": "INC-1024",
  "evidence": [
    {
      "type": "metric",
      "entity": "postgresql",
      "signal": "query_latency_p95",
      "timestamp": "2026-08-24T10:00:01Z",
      "description": "P95 query latency increased from 45ms to 2100ms",
      "grafana_link": "http://grafana/d/..."
    },
    {
      "type": "log",
      "entity": "payment-service",
      "timestamp": "2026-08-24T10:00:05Z",
      "description": "ConnectionTimeoutException: Failed to connect to PostgreSQL",
      "sample_logs": ["..."]
    },
    {
      "type": "trace",
      "entity": "payment-service",
      "timestamp": "2026-08-24T10:00:06Z",
      "description": "Trace shows 4200ms latency at PostgreSQL span",
      "trace_id": "abc123"
    },
    {
      "type": "k8s_event",
      "entity": "payment-7b8c9d",
      "timestamp": "2026-08-24T10:00:12Z",
      "description": "Pod restart due to liveness probe failure"
    }
  ]
}
```

---

### 3.4. Incident Engine Lifecycle

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.4.1 | Status transitions | OPEN → ACKNOWLEDGED → INVESTIGATING → MITIGATED → RESOLVED → CLOSED |
| 3.4.2 | Acknowledge API | `POST /api/v1/incidents/{id}/acknowledge` |
| 3.4.3 | Resolve API | `POST /api/v1/incidents/{id}/resolve` |
| 3.4.4 | Auto-resolve | Tự resolve nếu tất cả anomalies trở về normal trong N phút |
| 3.4.5 | Incident timeline | Log mọi state change, enrichment, new anomaly addition |
| 3.4.6 | Incident duration tracking | `started_at`, `acknowledged_at`, `resolved_at`, MTTR calculation |

---

### 3.5. Notification Service

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.5.1 | Notification template engine | Template cho Slack, Telegram, Alertmanager |
| 3.5.2 | Slack integration | Webhook → formatted message với incident summary, RCA, evidence links |
| 3.5.3 | Telegram integration | Bot API → formatted message |
| 3.5.4 | Alertmanager integration | Push alert với labels cho routing/grouping |
| 3.5.5 | Notification routing | Route by severity, namespace, service |
| 3.5.6 | Notification dedup | Không gửi lại nếu incident chưa thay đổi |

**Slack message template**:

```
🔴 Incident INC-1024 | CRITICAL

PostgreSQL performance degradation

Root Cause (92% confidence):
  → PostgreSQL query latency increased 45ms → 2100ms

Impact:
  → payment-service, order-service, api-gateway

Timeline:
  10:00:01  DB latency spike
  10:00:05  payment-service latency ↑
  10:00:10  order-service latency ↑
  10:00:15  api-gateway 5xx ↑

[View Incident] [View Grafana] [Acknowledge]
```

---

## 4. Cấu trúc thư mục

```
services/
├── rca-service/
│   ├── src/
│   │   ├── main.py
│   │   ├── scoring/
│   │   │   ├── temporal_scorer.py
│   │   │   ├── topology_scorer.py
│   │   │   ├── propagation_scorer.py
│   │   │   ├── severity_scorer.py
│   │   │   ├── deployment_scorer.py
│   │   │   ├── evidence_scorer.py
│   │   │   └── root_cause_ranker.py
│   │   ├── blast_radius/
│   │   │   └── calculator.py
│   │   ├── evidence/
│   │   │   ├── metric_collector.py
│   │   │   ├── log_collector.py
│   │   │   ├── trace_collector.py
│   │   │   └── k8s_event_collector.py
│   │   └── api/
│   │       ├── routes.py
│   │       └── models.py
│   ├── tests/
│   ├── config/
│   │   └── rca-config.yaml
│   └── Dockerfile

incident-engine/
│   ├── src/
│   │   ├── main.py
│   │   ├── lifecycle/
│   │   │   ├── state_machine.py
│   │   │   ├── auto_resolver.py
│   │   │   └── timeline.py
│   │   ├── notification/
│   │   │   ├── notifier.py
│   │   │   ├── slack.py
│   │   │   ├── telegram.py
│   │   │   ├── alertmanager.py
│   │   │   └── templates/
│   │   │       ├── slack_incident.j2
│   │   │       └── telegram_incident.j2
│   │   └── api/
│   │       ├── routes.py
│   │       └── models.py
│   ├── tests/
│   ├── config/
│   │   └── incident-config.yaml
│   └── Dockerfile
```

---

## 5. API Endpoints

```
# Root Cause Analysis
GET  /api/v1/root-causes/{incidentId}                # Ranked root causes
GET  /api/v1/root-causes/{incidentId}/blast-radius    # Blast radius

# Evidence
GET  /api/v1/incidents/{id}/evidence                  # All evidence
GET  /api/v1/incidents/{id}/timeline                  # Event timeline

# Incident Lifecycle
POST /api/v1/incidents/{id}/acknowledge
POST /api/v1/incidents/{id}/investigate
POST /api/v1/incidents/{id}/mitigate
POST /api/v1/incidents/{id}/resolve
POST /api/v1/incidents/{id}/close
POST /api/v1/incidents/{id}/comment                   # Add comment/note

# Notification
POST /api/v1/notifications/test                       # Test notification channel
GET  /api/v1/notifications/channels                   # List configured channels
```

---

## 6. Deliverables

- [ ] Root Cause Scoring: weighted multi-signal scoring với confidence.
- [ ] Blast Radius Calculator: graph traversal, impact classification.
- [ ] Evidence Aggregator: metric/log/trace/k8s event collection.
- [ ] Incident Lifecycle: full state machine (OPEN → CLOSED).
- [ ] Auto-resolve: tự resolve khi anomalies hết.
- [ ] Notification Service: Slack + Telegram + Alertmanager.
- [ ] REST API: root causes, blast radius, evidence, lifecycle, notifications.
- [ ] Unit tests cho scoring algorithms.
- [ ] Integration test: incident → RCA → notification end-to-end.

---

## 7. Definition of Done

1. ✅ RCA trả về ranked root causes cho mỗi incident với confidence score.
2. ✅ Blast radius hiển thị đúng direct/indirect impact.
3. ✅ Evidence tổng hợp metrics, logs, traces, K8s events.
4. ✅ Incident lifecycle hoạt động đầy đủ.
5. ✅ Notification gửi thành công qua ít nhất 1 kênh (Slack hoặc Telegram).
6. ✅ End-to-end: anomaly → correlation → incident → RCA → notification.
