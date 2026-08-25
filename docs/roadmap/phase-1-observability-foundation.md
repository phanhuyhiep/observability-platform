# Phase 1 – Observability Foundation

> Xây dựng nền tảng thu thập và chuẩn hóa dữ liệu telemetry: Metrics, Logs, Traces, Kubernetes Events.

| | |
|---|---|
| **Phase** | 1 / 5 |
| **Trạng thái** | Chưa bắt đầu |
| **Phụ thuộc** | Kubernetes cluster sẵn sàng |
| **Output chính** | Toàn bộ telemetry (metrics, logs, traces) được thu thập, chuẩn hóa và truy vấn được qua Grafana |

---

## 1. Mục tiêu

- Deploy stack Observability hoàn chỉnh trên Kubernetes.
- Thu thập metrics từ tất cả workload và hạ tầng.
- Thu thập và chuẩn hóa logs theo structured format.
- Instrument distributed tracing cho các service.
- Chuẩn hóa Entity Model và label convention xuyên suốt metrics, logs, traces.
- Cung cấp dashboard Grafana tổng quan cho team SRE/DevOps.

---

## 2. Kiến trúc Phase 1

```
Kubernetes Cluster
├── Applications (instrumented with OTel SDK)
│   ├── Metrics endpoint (/metrics)
│   ├── Structured logs (stdout/stderr)
│   └── Traces (OTLP export)
│
├── Prometheus / VictoriaMetrics
│   ├── Service discovery (kubernetes_sd)
│   ├── Scrape targets
│   └── Recording rules & alerting rules (basic)
│
├── Vector / Fluent Bit
│   ├── DaemonSet trên mỗi node
│   ├── Parse & enrich logs
│   └── Forward → Loki
│
├── OpenTelemetry Collector
│   ├── Deployment (gateway mode)
│   ├── Receive OTLP traces + metrics
│   ├── Process (batch, attributes)
│   └── Export → Tempo + Prometheus
│
├── Loki (log storage)
├── Tempo (trace storage)
│
└── Grafana
    ├── Prometheus datasource
    ├── Loki datasource
    ├── Tempo datasource
    └── Dashboards
```

---

## 3. Tasks chi tiết

### 3.1. Deploy Prometheus / VictoriaMetrics

**Mục tiêu**: Thu thập và lưu trữ metrics từ tất cả workload và hạ tầng Kubernetes.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.1.1 | Chọn giữa Prometheus và VictoriaMetrics | Có decision document, ghi rõ lý do chọn |
| 3.1.2 | Viết Helm values / Kustomize manifests | File cấu hình nằm trong `infrastructure/metrics/` |
| 3.1.3 | Cấu hình service discovery | Auto-discover tất cả pod/service có annotation `prometheus.io/scrape: "true"` |
| 3.1.4 | Cấu hình retention & storage | Retention ≥ 15 ngày, persistent volume claim |
| 3.1.5 | Recording rules cho các metric phổ biến | CPU, memory, request rate, error rate, latency percentiles |
| 3.1.6 | Basic alerting rules | Pod restart, OOMKilled, CrashLoopBackOff, node not ready |
| 3.1.7 | Grafana datasource | Prometheus datasource hoạt động, có ít nhất 1 dashboard kiểm chứng |

**Cấu trúc thư mục đề xuất**:

```
infrastructure/
└── metrics/
    ├── README.md
    ├── helm-values.yaml          # hoặc kustomization.yaml
    ├── recording-rules.yaml
    ├── alerting-rules.yaml
    └── dashboards/
        ├── cluster-overview.json
        ├── node-resources.json
        └── pod-resources.json
```

**Metrics cần thu thập**:

| Nhóm | Metric mẫu | Nguồn |
|---|---|---|
| Node | `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` | node-exporter |
| Pod | `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes` | cAdvisor / kubelet |
| Kubernetes | `kube_pod_status_phase`, `kube_pod_container_status_restarts_total` | kube-state-metrics |
| Application | `http_requests_total`, `http_request_duration_seconds` | Application metrics endpoint |
| Database | `pg_stat_activity_count`, `pg_stat_bgwriter_*` | postgres-exporter |

---

### 3.2. Deploy Loki + Vector/Fluent Bit

**Mục tiêu**: Thu thập, parse, enrich và lưu trữ logs từ tất cả container trong cluster.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.2.1 | Chọn giữa Vector và Fluent Bit | Decision document |
| 3.2.2 | Deploy Loki (single-binary hoặc microservices mode) | Loki running, nhận logs |
| 3.2.3 | Deploy log collector (DaemonSet) | Collector chạy trên mọi node, thu thập stdout/stderr |
| 3.2.4 | Cấu hình log parsing | JSON logs → structured fields; plain text → regex parse |
| 3.2.5 | Cấu hình log enrichment | Thêm `namespace`, `pod`, `container`, `node`, `service.name` |
| 3.2.6 | Label convention cho Loki | Labels: `namespace`, `service_name`, `level` |
| 3.2.7 | Retention policy | Retention ≥ 7 ngày |
| 3.2.8 | Grafana datasource | Loki datasource hoạt động, có thể query logs |

**Cấu trúc thư mục đề xuất**:

```
infrastructure/
└── logging/
    ├── README.md
    ├── loki/
    │   ├── helm-values.yaml
    │   └── loki-config.yaml
    └── vector/                   # hoặc fluent-bit/
        ├── helm-values.yaml
        └── pipeline.toml         # hoặc fluent-bit.conf
```

**Structured log format chuẩn**:

```json
{
  "timestamp": "2026-08-24T10:00:00.123Z",
  "level": "ERROR",
  "service.name": "payment-service",
  "service.instance.id": "payment-7b8c9d",
  "namespace": "production",
  "pod": "payment-7b8c9d",
  "node": "worker-01",
  "trace_id": "abc123def456",
  "span_id": "span789",
  "error.type": "ConnectionTimeoutException",
  "message": "Failed to connect to PostgreSQL after 3 retries"
}
```

> [!IMPORTANT]
> Application teams cần được cung cấp logging guidelines và library/wrapper để đảm bảo output đúng structured format.

---

### 3.3. Instrument Services bằng OpenTelemetry

**Mục tiêu**: Mỗi service tạo ra trace spans cho tất cả inbound/outbound requests, cho phép xây dựng dependency graph và phân tích latency.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.3.1 | Deploy OpenTelemetry Collector (gateway mode) | Collector running, nhận OTLP |
| 3.3.2 | Cấu hình Collector pipeline | Receivers: OTLP; Processors: batch, attributes, resource; Exporters: Tempo, Prometheus |
| 3.3.3 | Deploy Tempo | Tempo running, lưu traces |
| 3.3.4 | Instrument ít nhất 2-3 service đầu tiên | Service emit spans, trace hiện trong Grafana Tempo |
| 3.3.5 | Propagation context qua HTTP/gRPC headers | `traceparent` header được truyền xuyên suốt call chain |
| 3.3.6 | Auto-instrumentation (nếu dùng Java/Python/Node.js) | OTel agent/SDK inject tự động |
| 3.3.7 | Grafana Tempo datasource | Trace search hoạt động, liên kết Trace ↔ Logs qua `trace_id` |

**Cấu trúc thư mục đề xuất**:

```
infrastructure/
└── tracing/
    ├── README.md
    ├── otel-collector/
    │   ├── helm-values.yaml
    │   └── otel-config.yaml
    └── tempo/
        └── helm-values.yaml
```

**OpenTelemetry Collector config mẫu**:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024
  resource:
    attributes:
      - key: cluster
        value: "production-cluster"
        action: upsert

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
  prometheusremotewrite:
    endpoint: "http://prometheus:9090/api/v1/write"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, resource]
      exporters: [otlp/tempo]
    metrics:
      receivers: [otlp]
      processors: [batch, resource]
      exporters: [prometheusremotewrite]
```

---

### 3.4. Chuẩn hóa Labels & Entity Model

**Mục tiêu**: Đảm bảo metrics, logs và traces sử dụng cùng một bộ label/attribute để có thể correlation chéo giữa các tín hiệu.

| Task | Mô tả | Acceptance Criteria |
|---|---|---|
| 3.4.1 | Định nghĩa Entity Model | Document mô tả hierarchy: Cluster → Namespace → Node → Deployment → Pod → Service |
| 3.4.2 | Định nghĩa Label Convention | Bảng mapping label names giữa metrics, logs, traces |
| 3.4.3 | Cấu hình relabeling trong Prometheus | `service`, `namespace`, `pod` labels nhất quán |
| 3.4.4 | Cấu hình resource attributes trong OTel | `service.name`, `service.namespace`, `k8s.pod.name` |
| 3.4.5 | Cấu hình enrichment trong Vector/Fluent Bit | Log records có đủ entity fields |
| 3.4.6 | Validation test | Query Grafana: cùng 1 service name trả về metrics, logs và traces |

**Label Convention bắt buộc**:

| Semantic | Metrics (Prometheus) | Logs (Loki/structured) | Traces (OTel resource) |
|---|---|---|---|
| Cluster | `cluster` | `cluster` | `k8s.cluster.name` |
| Namespace | `namespace` | `namespace` | `k8s.namespace.name` |
| Node | `node` | `node` | `k8s.node.name` |
| Deployment | `deployment` | `deployment` | `k8s.deployment.name` |
| Pod | `pod` | `pod` | `k8s.pod.name` |
| Service | `service` | `service_name` | `service.name` |
| Instance | `instance` | `service.instance.id` | `service.instance.id` |

**Entity Model diagram**:

```
Cluster: production-cluster
└── Namespace: production
    ├── Node: worker-01
    │   └── Pod: payment-7b8c9d
    │       └── Container: payment
    └── Service: payment-service
        └── Deployment: payment-service-v2
            └── Pod: payment-7b8c9d
```

> [!WARNING]
> Nếu label convention không nhất quán từ Phase 1, tất cả các phase sau (Detection, Correlation, RCA) sẽ gặp khó khăn nghiêm trọng khi join data giữa các nguồn.

---

## 4. Grafana Dashboards

Cuối Phase 1, cần có tối thiểu các dashboard sau:

| Dashboard | Nội dung |
|---|---|
| **Cluster Overview** | Node count, pod count, CPU/memory cluster-wide, pod status |
| **Node Resources** | CPU, memory, disk, network per node |
| **Namespace Overview** | Resource usage per namespace, pod count, restart count |
| **Service Golden Signals** | Request rate, error rate, latency (p50/p95/p99) per service |
| **Log Explorer** | Loki log search, filter by service/level/time |
| **Trace Explorer** | Tempo trace search, service map |

---

## 5. Deliverables

- [ ] Prometheus/VictoriaMetrics running với đầy đủ service discovery.
- [ ] Loki + Vector/Fluent Bit running, thu thập logs từ tất cả pods.
- [ ] OpenTelemetry Collector + Tempo running, nhận traces từ ít nhất 2-3 services.
- [ ] Label convention document được team review và đồng thuận.
- [ ] Grafana dashboards: cluster overview, service golden signals, log explorer, trace explorer.
- [ ] Validation: có thể query cùng 1 service trên cả 3 datasource (metrics, logs, traces) bằng cùng service name.

---

## 6. Cấu trúc thư mục tổng thể Phase 1

```
infrastructure/
├── metrics/
│   ├── README.md
│   ├── helm-values.yaml
│   ├── recording-rules.yaml
│   ├── alerting-rules.yaml
│   └── dashboards/
│       ├── cluster-overview.json
│       ├── node-resources.json
│       ├── namespace-overview.json
│       └── service-golden-signals.json
├── logging/
│   ├── README.md
│   ├── loki/
│   │   ├── helm-values.yaml
│   │   └── loki-config.yaml
│   └── vector/
│       ├── helm-values.yaml
│       └── pipeline.toml
├── tracing/
│   ├── README.md
│   ├── otel-collector/
│   │   ├── helm-values.yaml
│   │   └── otel-config.yaml
│   └── tempo/
│       └── helm-values.yaml
└── grafana/
    ├── helm-values.yaml
    └── provisioning/
        ├── datasources.yaml
        └── dashboards.yaml

docs/
└── conventions/
    ├── entity-model.md
    ├── label-convention.md
    └── structured-logging-guide.md
```

---

## 7. Rủi ro & Lưu ý

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Resource overhead khi deploy full stack trên cluster nhỏ | Trung bình | Bắt đầu với single-binary mode (Loki, Tempo), scale sau |
| Application chưa output structured logs | Cao | Cung cấp logging library/wrapper, guide cho dev team |
| Label/attribute không nhất quán giữa teams | Cao | Enforce qua admission webhook hoặc OTel Collector processor |
| Storage tăng nhanh | Trung bình | Cấu hình retention, sampling cho traces |
| OTel SDK chưa hỗ trợ tốt ngôn ngữ đang dùng | Thấp | Fallback sang auto-instrumentation hoặc sidecar proxy |

---

## 8. Definition of Done

Phase 1 hoàn thành khi:

1. ✅ Toàn bộ workload trong cluster đều có metrics được scrape.
2. ✅ Logs từ tất cả pods được thu thập và truy vấn được.
3. ✅ Ít nhất 2-3 services có distributed traces hoạt động.
4. ✅ Entity model và label convention được document hóa và enforce.
5. ✅ Grafana có đầy đủ dashboards: cluster, node, service, logs, traces.
6. ✅ Có thể thực hiện cross-signal query: từ metric anomaly → tìm logs liên quan → xem trace.
