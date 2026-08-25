# Phase 3 – Correlation Engine

> Nhóm nhiều anomaly events có quan hệ thành correlation groups, xây dựng Service Dependency Graph, và tạo Incident thay vì gửi alert rời rạc.

| | |
|---|---|
| **Phase** | 3 / 5 |
| **Trạng thái** | Chưa bắt đầu |
| **Phụ thuộc** | Phase 2 hoàn thành (Anomaly Events đang được sinh ra) |
| **Output chính** | Correlation Service nhóm anomalies liên quan, Service Dependency Graph, Incident grouping |

---

## 1. Mục tiêu

- Xây dựng Time-window Correlation: nhóm anomalies xảy ra gần nhau về thời gian.
- Xây dựng Topology Correlation: nhóm anomalies theo dependency graph (upstream/downstream).
- Xây dựng Service Dependency Graph từ OpenTelemetry traces và Kubernetes metadata.
- Triển khai Incident Grouping: gộp correlated anomalies thành Incident.
- Giảm alert fatigue bằng cách gộp nhiều anomaly thành 1 incident có ngữ cảnh.

---

## 2. Kiến trúc Phase 3

```
Anomaly Events (from Phase 2)
         |
         ▼
┌─────────────────────┐
│  Correlation Engine  │
│                     │
│  ┌───────────────┐  │
│  │ Temporal       │  │     ┌──────────────────┐
│  │ Correlator     │◄─┼─────│ Time Window      │
│  └───────┬───────┘  │     │ Configuration    │
│          │          │     └──────────────────┘
│  ┌───────▼───────┐  │
│  │ Topology       │  │     ┌──────────────────┐
│  │ Correlator     │◄─┼─────│ Service          │
│  └───────┬───────┘  │     │ Dependency Graph │
│          │          │     └──────────────────┘
│  ┌───────▼───────┐  │
│  │ Deployment     │  │     ┌──────────────────┐
│  │ Correlator     │◄─┼─────│ Deployment       │
│  └───────┬───────┘  │     │ Events           │
│          │          │     └──────────────────┘
│  ┌───────▼───────┐  │
│  │ Incident       │  │
│  │ Grouper        │  │
│  └───────┬───────┘  │
└──────────┼──────────┘
           │
           ▼
   Correlation Groups
   & Incident Candidates
           │
           ▼
   PostgreSQL + Event Bus
   (→ Phase 4 RCA Engine)
```

---

## 3. Tasks chi tiết

### 3.1. Time-window Correlation

**Mục tiêu**: Nhóm các anomaly events xảy ra trong cùng một khoảng thời gian. Đây là lớp correlation cơ bản nhất.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.1.1 | Thiết kế correlation window | Configurable window size (default: 5 phút), sliding window |
| 3.1.2 | Implement temporal grouping algorithm | Anomalies trong cùng window → cùng correlation group |
| 3.1.3 | Overlap handling | Anomaly nằm ở biên window có thể thuộc nhiều group → merge logic |
| 3.1.4 | Window extension | Nếu anomaly mới xuất hiện sát cuối window → extend window |
| 3.1.5 | Correlation Group model | Tạo data model cho correlation group |
| 3.1.6 | Unit tests | Test window grouping, merge, extension |

**Temporal Correlation algorithm**:

```
Input: Stream of anomaly events sorted by timestamp

Algorithm:
  1. Initialize empty correlation_groups[]
  2. For each new anomaly_event:
     a. Find existing groups where:
        - group.last_event_time + window_size > anomaly.timestamp
        - OR group has entity in same namespace/cluster
     b. If matching group found:
        - Add anomaly to group
        - Update group.last_event_time
        - Extend window if needed
     c. If no matching group:
        - Create new correlation group
        - Start new window
  3. Close groups that have been inactive > window_size * 2

Output: List of CorrelationGroups, each containing related anomalies
```

**Correlation Group schema**:

```json
{
  "correlation_id": "corr-uuid",
  "created_at": "2026-08-24T10:00:01Z",
  "updated_at": "2026-08-24T10:00:15Z",
  "window_start": "2026-08-24T10:00:01Z",
  "window_end": "2026-08-24T10:05:01Z",
  "status": "active",

  "anomalies": [
    { "anomaly_id": "a1", "entity_id": "postgresql", "timestamp": "10:00:01", "category": "latency" },
    { "anomaly_id": "a2", "entity_id": "payment-service", "timestamp": "10:00:05", "category": "latency" },
    { "anomaly_id": "a3", "entity_id": "order-service", "timestamp": "10:00:10", "category": "latency" },
    { "anomaly_id": "a4", "entity_id": "api-gateway", "timestamp": "10:00:15", "category": "error_rate" }
  ],

  "correlation_type": "temporal",
  "entity_count": 4,
  "severity_max": "critical",
  "namespaces": ["production"],
  "cluster": "production-cluster"
}
```

---

### 3.2. Service Dependency Graph

**Mục tiêu**: Xây dựng và duy trì graph mô tả quan hệ giữa các service, database, queue, external API.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.2.1 | Thiết kế graph data model | Node (entity) + Edge (dependency) + metadata |
| 3.2.2 | Build graph từ OpenTelemetry traces | Phân tích spans → extract caller/callee → tạo edges |
| 3.2.3 | Enrich graph từ Kubernetes metadata | Service → Pod mapping, Service → Deployment mapping |
| 3.2.4 | Manual graph configuration | API/YAML cho manual dependency declaration |
| 3.2.5 | Graph update scheduler | Rebuild graph mỗi 15-30 phút từ recent traces |
| 3.2.6 | Graph query API | `GET /api/v1/topology/services`, upstream/downstream queries |
| 3.2.7 | Graph storage | Lưu vào PostgreSQL (adjacency list) hoặc in-memory |
| 3.2.8 | Graph visualization data | Export format phù hợp cho frontend rendering |

**Graph Node model**:

```json
{
  "node_id": "payment-service",
  "node_type": "service",
  "namespace": "production",
  "cluster": "production-cluster",
  "metadata": {
    "deployment": "payment-service-v2",
    "replicas": 3,
    "version": "2.5.0"
  }
}
```

**Graph Edge model**:

```json
{
  "edge_id": "edge-uuid",
  "source": "payment-service",
  "target": "postgresql",
  "dependency_type": "database",
  "metadata": {
    "call_count_1h": 15000,
    "error_rate_1h": 0.02,
    "p95_latency_1h": 45,
    "protocol": "tcp"
  },
  "discovered_by": "otel_traces",
  "last_seen": "2026-08-24T10:00:00Z"
}
```

**Database schema cho graph**:

```sql
CREATE TABLE service_graph_nodes (
    node_id         VARCHAR(255) PRIMARY KEY,
    node_type       VARCHAR(50) NOT NULL,    -- service, database, queue, external
    namespace       VARCHAR(255),
    cluster         VARCHAR(255),
    metadata        JSONB,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE service_graph_edges (
    edge_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       VARCHAR(255) NOT NULL REFERENCES service_graph_nodes(node_id),
    target_id       VARCHAR(255) NOT NULL REFERENCES service_graph_nodes(node_id),
    dependency_type VARCHAR(50),             -- http, grpc, database, queue, external
    metadata        JSONB,
    discovered_by   VARCHAR(50),             -- otel_traces, k8s_metadata, manual
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_id, target_id, dependency_type)
);

CREATE INDEX idx_edge_source ON service_graph_edges(source_id);
CREATE INDEX idx_edge_target ON service_graph_edges(target_id);
```

**Graph build từ OTel traces**:

```
For each trace:
  For each span in trace:
    caller = span.parent_service (or root if no parent)
    callee = span.service_name

    Upsert node(caller)
    Upsert node(callee)
    Upsert edge(caller → callee):
      - increment call_count
      - update error_rate
      - update p95_latency
      - set last_seen = now()
```

---

### 3.3. Topology Correlation

**Mục tiêu**: Sử dụng dependency graph để xác định quan hệ nhân quả giữa các anomalies.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.3.1 | Upstream/downstream lookup | Cho entity X, tìm tất cả upstream và downstream entities |
| 3.3.2 | Dependency-aware grouping | Nếu anomaly ở entity A và entity B, kiểm tra A→B hoặc B→A tồn tại |
| 3.3.3 | Propagation direction detection | Xác định anomaly lan truyền theo hướng nào (downstream → upstream hay ngược lại) |
| 3.3.4 | Enrich correlation group | Thêm topology context vào correlation group |
| 3.3.5 | Multi-hop correlation | Nếu A→B→C, anomaly ở A và C vẫn được correlate qua B |
| 3.3.6 | Unit tests | Test topology lookup, propagation detection |

**Topology Correlation algorithm**:

```
Input: 
  - Temporal correlation group (list of anomalies)
  - Service dependency graph

Algorithm:
  1. For each pair (anomaly_i, anomaly_j) in group:
     a. Check if entity_i → entity_j exists in graph (direct)
     b. Check if entity_j → entity_i exists in graph (direct)
     c. Check if path(entity_i, entity_j) exists (multi-hop, max depth=3)
  
  2. For connected anomalies:
     a. Determine propagation direction:
        - If anomaly_i.timestamp < anomaly_j.timestamp
          AND entity_i → entity_j (downstream)
          → propagation: entity_i caused entity_j (high confidence)
        - If anomaly_i.timestamp < anomaly_j.timestamp  
          AND entity_j → entity_i (upstream)
          → propagation: entity_j impact visible at entity_i (medium confidence)
     
  3. Assign topology_score to each anomaly:
     - Earliest anomaly in dependency chain → highest score
     - Downstream anomalies → lower score (they are likely impacts)

Output: Enriched correlation group with topology context
```

**Enriched Correlation Group**:

```json
{
  "correlation_id": "corr-uuid",
  "anomalies": [...],
  "topology": {
    "has_dependency_relation": true,
    "propagation_direction": "downstream",
    "propagation_path": [
      "postgresql → payment-service → order-service → api-gateway"
    ],
    "root_entity_candidate": "postgresql",
    "topology_confidence": 0.88
  }
}
```

---

### 3.4. Deployment Correlation

**Mục tiêu**: Phát hiện anomaly có liên quan đến deployment/rollout gần đây.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.4.1 | Deployment event collector | Thu thập events từ Kubernetes (Deployment rollout), ArgoCD, CI/CD webhook |
| 3.4.2 | Deployment event storage | Lưu deployment events vào PostgreSQL |
| 3.4.3 | Time-proximity matching | Nếu anomaly xảy ra trong N phút sau deployment → correlate |
| 3.4.4 | Entity matching | Deployment event phải match entity (cùng service/namespace) |
| 3.4.5 | Enrich correlation group | Thêm deployment context nếu có correlation |

**Deployment Event schema**:

```json
{
  "event_id": "dep-uuid",
  "timestamp": "2026-08-24T10:00:00Z",
  "event_type": "deployment_rollout",
  "entity_type": "deployment",
  "entity_id": "payment-service-v2",
  "namespace": "production",
  "cluster": "production-cluster",
  "details": {
    "previous_version": "2.4.0",
    "new_version": "2.5.0",
    "replicas": 3,
    "strategy": "RollingUpdate",
    "triggered_by": "argocd"
  }
}
```

**Deployment Correlation logic**:

```
correlation_window_after_deploy = 30m  (configurable)

For each anomaly in correlation group:
  Find deployment events where:
    - deployment.namespace == anomaly.namespace
    - deployment.entity matches anomaly.entity (or upstream)
    - deployment.timestamp < anomaly.timestamp
    - anomaly.timestamp - deployment.timestamp < correlation_window

  If match found:
    enrichment = {
      "deployment_correlated": true,
      "deployment_event": event,
      "time_since_deploy": anomaly.timestamp - deployment.timestamp,
      "deployment_confidence": calculate_confidence(time_since_deploy)
    }
```

---

### 3.5. Incident Grouping

**Mục tiêu**: Gộp các correlation groups thành Incident candidates. Một incident đại diện cho 1 sự cố thực tế.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.5.1 | Incident creation logic | Tạo Incident từ correlation group đạt ngưỡng (≥2 anomalies, hoặc 1 critical anomaly) |
| 3.5.2 | Incident merging | Merge incidents nếu chúng share entities hoặc overlap thời gian |
| 3.5.3 | Incident suppression | Không tạo incident mới nếu đã có incident active cho cùng root entity |
| 3.5.4 | Incident severity calculation | `max(anomaly severities)` hoặc weighted calculation |
| 3.5.5 | Incident title generation | Auto-generate title từ root entity + category |
| 3.5.6 | Incident storage | PostgreSQL table |
| 3.5.7 | Incident API (basic) | `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}` |

**Incident creation criteria**:

```
Create Incident if:
  - Correlation group has ≥ 2 anomalies
  - OR single anomaly with severity = "critical"
  - AND no existing active incident covers same entities

Incident severity:
  - If any anomaly is "critical" → incident = "critical"
  - If max anomaly is "high" and count ≥ 3 → incident = "critical"
  - If max anomaly is "high" → incident = "high"
  - Otherwise → incident = "warning"

Incident title generation:
  - If deployment correlated: "[service] anomaly after deployment v{version}"
  - If topology root found: "[root_entity] performance degradation"
  - Otherwise: "Multiple anomalies in [namespace]"
```

**Incident schema (basic, sẽ extend ở Phase 4)**:

```json
{
  "incident_id": "INC-1024",
  "title": "PostgreSQL performance degradation",
  "severity": "critical",
  "status": "OPEN",
  "created_at": "2026-08-24T10:00:20Z",
  "updated_at": "2026-08-24T10:00:20Z",

  "correlation_id": "corr-uuid",
  "anomaly_count": 4,
  "entity_count": 4,
  "impacted_entities": [
    "postgresql",
    "payment-service",
    "order-service",
    "api-gateway"
  ],
  "namespaces": ["production"],
  "cluster": "production-cluster",

  "topology_context": {
    "root_entity_candidate": "postgresql",
    "propagation_path": ["postgresql → payment-service → api-gateway"],
    "topology_confidence": 0.88
  },

  "deployment_context": null,

  "anomalies": ["a1", "a2", "a3", "a4"]
}
```

**Database schema**:

```sql
CREATE TABLE incidents (
    incident_id         VARCHAR(20) PRIMARY KEY,     -- INC-XXXX
    title               TEXT NOT NULL,
    severity            VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'OPEN',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,

    correlation_id      UUID REFERENCES correlation_groups(correlation_id),
    anomaly_count       INT,
    entity_count        INT,
    impacted_entities   JSONB,
    namespaces          JSONB,
    cluster             VARCHAR(255),

    topology_context    JSONB,
    deployment_context  JSONB,

    metadata            JSONB
);

CREATE TABLE incident_anomalies (
    incident_id     VARCHAR(20) REFERENCES incidents(incident_id),
    anomaly_id      UUID REFERENCES anomaly_events(anomaly_id),
    PRIMARY KEY (incident_id, anomaly_id)
);

CREATE TABLE correlation_groups (
    correlation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    correlation_type    VARCHAR(50),
    entity_count        INT,
    severity_max        VARCHAR(20),
    topology_context    JSONB,
    deployment_context  JSONB,
    metadata            JSONB
);

CREATE TABLE correlation_anomalies (
    correlation_id  UUID REFERENCES correlation_groups(correlation_id),
    anomaly_id      UUID REFERENCES anomaly_events(anomaly_id),
    PRIMARY KEY (correlation_id, anomaly_id)
);

CREATE INDEX idx_incident_status ON incidents(status);
CREATE INDEX idx_incident_severity ON incidents(severity);
CREATE INDEX idx_incident_created ON incidents(created_at);
CREATE INDEX idx_correlation_status ON correlation_groups(status);
```

---

## 4. Cấu trúc thư mục tổng thể Phase 3

```
correlation/
├── README.md
├── src/
│   ├── main.py
│   ├── correlators/
│   │   ├── temporal_correlator.py
│   │   ├── topology_correlator.py
│   │   └── deployment_correlator.py
│   ├── graph/
│   │   ├── graph_builder.py           # Build graph từ OTel traces
│   │   ├── graph_storage.py           # PostgreSQL persistence
│   │   ├── graph_query.py             # Upstream/downstream queries
│   │   └── k8s_enricher.py            # Enrich từ K8s metadata
│   ├── incident/
│   │   ├── incident_grouper.py
│   │   ├── incident_merger.py
│   │   └── incident_suppression.py
│   ├── deployment/
│   │   ├── deployment_collector.py    # K8s watch, webhook receiver
│   │   └── deployment_storage.py
│   └── api/
│       ├── routes.py
│       └── models.py
├── tests/
│   ├── test_temporal_correlator.py
│   ├── test_topology_correlator.py
│   ├── test_deployment_correlator.py
│   ├── test_graph_builder.py
│   └── test_incident_grouper.py
├── migrations/
│   ├── 001_create_correlation_groups.sql
│   ├── 002_create_service_graph.sql
│   ├── 003_create_incidents.sql
│   └── 004_create_deployment_events.sql
├── config/
│   └── correlation-config.yaml
├── Dockerfile
└── docker-compose.yaml
```

---

## 5. API Endpoints

```
# Correlation Groups
GET    /api/v1/correlations                      # List correlation groups
GET    /api/v1/correlations/{correlation_id}      # Get correlation detail

# Service Dependency Graph
GET    /api/v1/topology/services                  # Full service graph
GET    /api/v1/topology/services/{service_id}     # Single service with edges
GET    /api/v1/topology/services/{id}/upstream     # Upstream dependencies
GET    /api/v1/topology/services/{id}/downstream   # Downstream dependents
POST   /api/v1/topology/edges                     # Manual edge declaration
DELETE /api/v1/topology/edges/{edge_id}           # Remove manual edge

# Incidents (basic)
GET    /api/v1/incidents                          # List incidents
GET    /api/v1/incidents/{incident_id}            # Get incident detail
GET    /api/v1/incidents/{id}/anomalies           # Get anomalies for incident
GET    /api/v1/incidents/{id}/timeline            # Event timeline for incident

# Deployment Events
POST   /api/v1/deployments                       # Receive deployment event (webhook)
GET    /api/v1/deployments                        # List recent deployments

# Health
GET    /health
GET    /metrics
```

---

## 6. Configuration

```yaml
# correlation-config.yaml
correlation:
  evaluation_interval: "30s"        # How often to evaluate new anomalies

temporal:
  window_size: "5m"                 # Default correlation window
  max_window_extension: "15m"       # Maximum window extension
  min_anomalies_for_group: 2        # Minimum anomalies to form a group

topology:
  graph_rebuild_interval: "15m"     # How often to rebuild graph from traces
  max_hop_depth: 3                  # Maximum hops for multi-hop correlation
  edge_ttl: "24h"                   # Remove edges not seen for this duration

deployment:
  correlation_window: "30m"         # Window after deployment to check for anomalies
  sources:
    - type: "kubernetes"            # Watch K8s Deployment events
      enabled: true
    - type: "webhook"               # Receive CI/CD webhooks
      enabled: true
      endpoint: "/api/v1/deployments"

incident:
  auto_create: true
  min_anomalies: 2                  # Minimum anomalies for auto-create
  critical_auto_create: true        # Auto-create for single critical anomaly
  merge_window: "10m"               # Merge incidents within this window
  suppression_window: "30m"         # Suppress duplicate incidents

storage:
  database_url: "postgresql://..."

tempo:
  url: "http://tempo:3200"
  query_range: "1h"                 # Range to query for graph building
```

---

## 7. Deliverables

- [ ] Temporal Correlator: nhóm anomalies theo time window.
- [ ] Service Dependency Graph: auto-build từ OTel traces + K8s metadata.
- [ ] Graph Query API: upstream/downstream lookup, full graph export.
- [ ] Topology Correlator: enrich correlation groups với dependency context.
- [ ] Deployment Correlator: phát hiện anomaly liên quan deployment.
- [ ] Incident Grouper: tạo Incident từ correlation groups.
- [ ] Incident Merger & Suppression: tránh duplicate incidents.
- [ ] PostgreSQL tables: correlation_groups, service_graph, incidents, deployment_events.
- [ ] REST API: correlations, topology, incidents, deployments.
- [ ] Unit tests cho từng correlator và graph builder.
- [ ] Integration test: anomaly events → correlation → incident.

---

## 8. Rủi ro & Lưu ý

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Graph không chính xác nếu traces không đầy đủ | Cao | Hỗ trợ manual edge declaration, enrich từ K8s metadata |
| Correlation window quá rộng → nhóm sai | Trung bình | Cho phép tuning per namespace/cluster, combine với topology |
| Quá nhiều incidents nếu threshold thấp | Trung bình | Tuning min_anomalies, suppression rules |
| Deployment events bị miss (CI/CD không gửi webhook) | Trung bình | Fallback: watch K8s Deployment events trực tiếp |
| Graph rebuild gây tải Tempo queries | Thấp | Rate limiting, incremental updates thay vì full rebuild |

---

## 9. Definition of Done

Phase 3 hoàn thành khi:

1. ✅ Temporal Correlation nhóm đúng anomalies xảy ra trong cùng time window.
2. ✅ Service Dependency Graph được build tự động từ traces, hiển thị đúng dependencies.
3. ✅ Topology Correlation xác định đúng propagation direction.
4. ✅ Deployment Correlation phát hiện anomaly liên quan rollout.
5. ✅ Incidents được tạo tự động từ correlation groups.
6. ✅ Incident deduplication và suppression hoạt động.
7. ✅ API hoạt động: correlations, topology, incidents.
8. ✅ Integration test: inject anomaly events → verify correlation group → verify incident created.
